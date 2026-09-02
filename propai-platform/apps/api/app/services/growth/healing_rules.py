"""자가성장 엔진 Phase 3 — L0 자가치유 룰 엔진(설계서 §6.1).

open 인사이트(platform_insights) + 최근 이벤트(platform_events)를 보고 어떤 heal
액션을 수행할지 결정한다. 결정만 하고 실행은 heal_actions.execute() 에 위임한다.

4룰(설계 §6.1):
  - cache_warm        : service 폴백률 급등 + 캐시미스↑ → 캐시워밍 잡(시간당 1회 캡).
  - threshold_relax   : 외부API 전면장애 감지 → rate-limit/timeout 임계 일시상향(TTL 30분).
  - stale_reanalysis  : 원장 verify_chain broken/staleness → 재분석 제안 큐잉(자동실행 금지).
  - circuit_observe   : CircuitBreaker OPEN/폴백 관측·이벤트화·heal-log 기록만.

무한루프 가드(메타가드 = "healer 를 위한 circuit breaker"):
  (a) 시간당 실행횟수 캡  — 액션타입별 GLOBAL_HOURLY_CAP, 동일 트리거 PER_TRIGGER_HOURLY_CAP.
  (b) 동일 트리거 쿨다운  — COOLDOWN_MIN 내 같은 (action_type, trigger_key) 재발화 차단.
  (c) 에스컬레이션      — 조치 후에도 효과 없이 동일 트리거가 캡을 초과하면 critical
                          인사이트로 승격(사람 알림). 이상은 self-loop 차단의 3중 안전망.

가드 판정은 stdlib 만으로 단위검증 가능하도록 순수 함수(_within_cooldown/_cap_exceeded/
should_escalate)로 분리한다(DB 무의존). DB 카운트 조회는 별도 async 함수.
best-effort: 어떤 예외도 heal 태스크를 죽이지 않는다.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.growth import heal_actions

logger = logging.getLogger(__name__)

# ── 가드 임계(설계 §6.1: 횟수캡·쿨다운·에스컬레이션) ──────────────────────────
# 액션타입별 시간당 전역 실행 캡(전체 트리거 합산).
GLOBAL_HOURLY_CAP = {
    heal_actions.ACTION_CACHE_WARM: 1,        # 캐시워밍 빈도 캡(시간당 1회) — 설계 명시.
    heal_actions.ACTION_THRESHOLD_RELAX: 4,   # 임계완화 시간당 최대 4회.
    heal_actions.ACTION_STALE_REANALYSIS: 20, # 제안 큐잉(저위험)은 다소 여유.
    heal_actions.ACTION_CIRCUIT_OBSERVE: 60,  # 관측 기록(부작용 없음)은 넉넉히.
}
# 동일 트리거(action_type, trigger_key) 시간당 캡(스팸 방지).
PER_TRIGGER_HOURLY_CAP = {
    heal_actions.ACTION_CACHE_WARM: 1,
    heal_actions.ACTION_THRESHOLD_RELAX: 2,
    heal_actions.ACTION_STALE_REANALYSIS: 3,
    heal_actions.ACTION_CIRCUIT_OBSERVE: 10,
}
# 동일 트리거 쿨다운(분) — 직전 실행 후 이 시간 내 재발화 차단.
COOLDOWN_MIN = {
    heal_actions.ACTION_CACHE_WARM: 60,
    heal_actions.ACTION_THRESHOLD_RELAX: 15,
    heal_actions.ACTION_STALE_REANALYSIS: 30,
    heal_actions.ACTION_CIRCUIT_OBSERVE: 1,
}
# 에스컬레이션 임계: 동일 트리거가 시간당 이 횟수 이상 발화하면 효과없음으로 보고 critical 승격.
ESCALATION_THRESHOLD = 5

# 외부API "전면장애" 판정: 폴백률(%) 이 이 값 이상이면 threshold_relax 대상.
TOTAL_OUTAGE_FALLBACK_PCT = 50.0

#: `_candidate_actions` 가 **실제로 분기를 가진** 인사이트 타입.
#
#  ★이 목록은 **선언이고, 선언은 스스로 옳음을 보증하지 않는다.** 그래서 락이 `ast` 로
#  `_candidate_actions` 안의 `itype == "..."` 비교를 전부 뽑아 이 상수와 **정확히 일치**하는지
#  본다. 분기를 추가하고 여기 안 적으면(또는 그 반대면) 빨개진다 —
#  **선언과 생산자가 어긋나는 것**이 이 저장소가 반복해서 데인 형태다.
HANDLED_INSIGHT_TYPES = ("fallback_rate", "stale_reanalysis")


# ════════════════════════════════════════════════════════════════════════════
# 순수 가드 함수군 (DB 무의존 — inline 단위검증 대상)
# ════════════════════════════════════════════════════════════════════════════

def _within_cooldown(last_ts: datetime | None, now: datetime, cooldown_min: int) -> bool:
    """직전 실행(last_ts)이 쿨다운 윈도우 내면 True(= 차단). last 없으면 False."""
    if last_ts is None:
        return False
    if last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=UTC)
    return (now - last_ts) < timedelta(minutes=cooldown_min)


def _cap_exceeded(recent_count: int, cap: int) -> bool:
    """최근 1시간 실행수(recent_count)가 캡 이상이면 True(= 차단)."""
    return recent_count >= cap


def should_escalate(per_trigger_hourly: int, threshold: int = ESCALATION_THRESHOLD) -> bool:
    """동일 트리거가 시간당 threshold 이상 반복 → 효과없음으로 보고 에스컬레이션."""
    return per_trigger_hourly >= threshold


def gate(action_type: str, trigger_key: str, *, now: datetime,
         global_count: int, trigger_count: int, last_ts: datetime | None) -> dict[str, Any]:
    """단일 후보 액션의 통과/차단을 종합 판정한다(순수 함수, 단위검증 진입점).

    반환: {"allow": bool, "reason": str, "escalate": bool}.
      - 쿨다운 내 → 차단.
      - 전역/트리거 캡 초과 → 차단(+ 트리거 캡 초과 시 에스컬레이션 검토).
      - 모두 통과 → allow.
    """
    cooldown = COOLDOWN_MIN.get(action_type, 15)
    g_cap = GLOBAL_HOURLY_CAP.get(action_type, 5)
    t_cap = PER_TRIGGER_HOURLY_CAP.get(action_type, 2)

    escalate = should_escalate(trigger_count)

    if _within_cooldown(last_ts, now, cooldown):
        return {"allow": False, "reason": "cooldown", "escalate": escalate}
    if _cap_exceeded(global_count, g_cap):
        return {"allow": False, "reason": "global_cap", "escalate": escalate}
    if _cap_exceeded(trigger_count, t_cap):
        return {"allow": False, "reason": "trigger_cap", "escalate": escalate}
    return {"allow": True, "reason": "ok", "escalate": False}


# ════════════════════════════════════════════════════════════════════════════
# DB 카운트(가드 입력) — platform_events(heal_action) 기반(워커 간 공유 상태)
# ════════════════════════════════════════════════════════════════════════════

async def _guard_counts(db, action_type: str, trigger_key: str,
                        now: datetime) -> tuple[int, int, datetime | None]:
    """최근 1시간 (전역 실행수, 동일 트리거 실행수, 직전 트리거 실행시각) 조회.

    heal_action 이벤트의 payload->params->trigger_key 로 동일 트리거를 식별한다.
    DB 기반이라 프로세스/워커 간 공유 상태로 동작(in-memory 카운터의 워커별
    불일치 문제 회피).
    """
    from sqlalchemy import text

    since = now - timedelta(hours=1)
    g = (await db.execute(text(
        "SELECT COUNT(*) FROM platform_events "
        "WHERE event_type='heal_action' "
        "  AND payload->>'action_type' = :at AND created_at >= :since"
    ), {"at": action_type, "since": since})).scalar() or 0

    trow = (await db.execute(text(
        "SELECT COUNT(*), MAX(created_at) FROM platform_events "
        "WHERE event_type='heal_action' "
        "  AND payload->>'action_type' = :at "
        "  AND payload->'params'->>'trigger_key' = :tk "
        "  AND created_at >= :since"
    ), {"at": action_type, "tk": trigger_key, "since": since})).fetchone()
    t_count = int(trow[0] or 0) if trow else 0
    last_ts = trow[1] if trow else None
    return int(g), t_count, last_ts


# ════════════════════════════════════════════════════════════════════════════
# 룰 평가 → 후보 액션 결정
# ════════════════════════════════════════════════════════════════════════════

async def _candidate_actions(db, now: datetime) -> list[dict[str, Any]]:
    """open 인사이트 + 최근 이벤트를 보고 heal 후보 액션을 도출한다.

    각 후보에 trigger_key(쿨다운/캡의 동일성 식별자)를 params 에 박아둔다.
    """
    from sqlalchemy import text

    candidates: list[dict[str, Any]] = []

    # ── open 인사이트 기반 ────────────────────────────────────────────────
    # ★**타입으로도 좁힌다.** 종전에는 `recommended_action` 으로만 걸러서 아래 `for` 루프에
    #   **분기가 없는 타입까지 `LIMIT 200` 슬롯을 먹었다.**
    #   실측(2026-08-27): open 인사이트의 **97.2%** 가 `latency_baseline`(76.2%) +
    #   `latency_regression`(21.0%) 이고, `latency_regression` 은 `recommended_action='heal'`
    #   을 내는데(`analyzer.py:846`) 이 함수에 분기가 **없다**.
    #   ★`'none'` 도 종전 WHERE 를 통과하므로 **사유로는 못 막고 타입으로만 막힌다.**
    #   잡음이 슬롯을 채우면 진짜 후보가 200 밖으로 밀리는데, 한 배치의 `created_at` 이
    #   **하나**라 어느 200 이 남는지가 **임의**가 된다 — 조용한 기아다.
    # ★`ORDER BY` 에 `id` 타이브레이커를 넣는다. 형제 `insight_retention._build_select` 가
    #   이미 `created_at DESC, id DESC` 로 하고 있었다 — **옳은 패턴이 옆에 있었다.**
    rows = (await db.execute(text(
        "SELECT id, insight_type, severity, metrics_json FROM platform_insights "
        "WHERE status='open' AND recommended_action IN ('heal','none','correct') "
        "  AND insight_type = ANY(:handled) "
        "  AND created_at >= :since "
        "ORDER BY created_at DESC, id DESC LIMIT 200"
    ), {"since": now - timedelta(hours=2),
        "handled": list(HANDLED_INSIGHT_TYPES)})).fetchall()

    for r in rows:
        _ins_id, itype, severity, metrics = r[0], r[1], r[2], r[3]
        m = metrics if isinstance(metrics, dict) else {}
        service = m.get("service") or m.get("key")

        if itype == "fallback_rate":
            pct = float(m.get("fallback_pct") or 0.0)
            tkey = f"fallback_rate:{service}"
            if pct >= TOTAL_OUTAGE_FALLBACK_PCT:
                # 전면장애 → 임계 일시완화.
                candidates.append({
                    "type": heal_actions.ACTION_THRESHOLD_RELAX,
                    "service": service, "severity": severity or "critical",
                    "params": {"trigger_key": tkey, "fallback_pct": pct,
                               "setting_key": f"relax.{service}" if service else "relax.global",
                               "insight_id": str(_ins_id)},
                })
            else:
                # 부분 급등 → 캐시워밍(시간당 1회 캡).
                candidates.append({
                    "type": heal_actions.ACTION_CACHE_WARM,
                    "service": service, "severity": severity or "warn",
                    "params": {"trigger_key": tkey, "fallback_pct": pct,
                               "insight_id": str(_ins_id)},
                })

        elif itype == "stale_reanalysis":
            # 이미 큐잉된 제안은 재큐잉 방지(트리거키로 쿨다운).
            candidates.append({
                "type": heal_actions.ACTION_STALE_REANALYSIS,
                "service": service, "severity": severity or "warn",
                "params": {"trigger_key": f"stale:{_ins_id}", "insight_id": str(_ins_id),
                           **{k: v for k, v in m.items() if k != "service"}},
            })

    # ── 원장 변조탐지(verify_chain broken) 이벤트 기반 → stale_reanalysis 제안 ──
    broken = (await db.execute(text(
        "SELECT service, payload FROM platform_events "
        "WHERE event_type='fallback' AND severity='critical' "
        "  AND payload->>'kind' = 'ledger_broken' AND created_at >= :since "
        "ORDER BY created_at DESC LIMIT 50"
    ), {"since": now - timedelta(hours=1)})).fetchall()
    for r in broken:
        candidates.append({
            "type": heal_actions.ACTION_STALE_REANALYSIS,
            "service": r[0], "severity": "critical",
            "params": {"trigger_key": "ledger_broken", "kind": "ledger_broken"},
        })

    # ── circuit OPEN/폴백 이벤트 관측(이벤트화·기록만) ────────────────────
    circ = (await db.execute(text(
        "SELECT service, COUNT(*) FROM platform_events "
        "WHERE event_type='fallback' AND created_at >= :since "
        "  AND service IS NOT NULL "
        "GROUP BY service"
    ), {"since": now - timedelta(minutes=10)})).fetchall()
    for r in circ:
        service, cnt = r[0], int(r[1] or 0)
        candidates.append({
            "type": heal_actions.ACTION_CIRCUIT_OBSERVE,
            "service": service, "severity": "info",
            "params": {"trigger_key": f"circuit:{service}", "fallback_count": cnt},
        })

    return candidates


async def mark_insight_acted(db, action: dict[str, Any], result: dict[str, Any]) -> int:
    """실행된 heal 이 겨냥한 인사이트를 `acted` 로 닫는다. 닫힌 행 수를 반환.

    ★왜 이 자리인가: `heal_actions.execute` 는 반환 지점이 다섯이다. 그 안에 닫기를
    손으로 붙이면 **반드시 하나를 빠뜨리고 그 하나가 곧 안 닫히는 경로**가 된다.
    호출부의 **단일 길목**(성공 판정 직후)에서 한 번만 닫는다.

    ★`open` 만 닫는다 — 사람이 이미 판단한 `acknowledged`·`dismissed` 는 건드리지 않는다.
    ★best-effort: 닫기 실패가 치유 태스크를 죽이지 않는다(치유는 이미 일어났다).
    """
    from sqlalchemy import text

    ins_id = (action.get("params") or {}).get("insight_id")
    if not ins_id or not result.get("executed"):
        return 0
    try:
        row = (await db.execute(text(
            "UPDATE platform_insights SET status = 'acted' "
            "WHERE id = CAST(:id AS uuid) AND status = 'open' "
            "RETURNING id"
        ), {"id": str(ins_id)})).fetchone()
        await db.commit()
        return 1 if row is not None else 0
    except Exception as e:  # noqa: BLE001 — 치유 자체는 성공했다.
        logger.warning("insight acted 전이 실패(%s): %s", ins_id, str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return 0


async def _escalate(db, action_type: str, trigger_key: str) -> None:
    """효과없는 반복 조치 → critical 인사이트로 승격(사람 알림). best-effort."""
    import json

    from sqlalchemy import text

    try:
        await db.execute(text(
            "INSERT INTO platform_insights "
            "(insight_type, metrics_json, severity, narrative, recommended_action, status) "
            "VALUES ('heal_escalation', CAST(:m AS jsonb), 'critical', :narr, "
            " 'propose_pr', 'open')"
        ), {
            "m": json.dumps({"action_type": action_type, "trigger_key": trigger_key,
                             "reason": "auto_heal_ineffective"}, ensure_ascii=False),
            "narr": (f"자동치유 무효: {action_type}({trigger_key}) 가 반복 발화했으나 "
                     f"효과가 없어 에스컬레이션합니다. 사람 점검 필요."),
        })
        await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("heal 에스컬레이션 실패: %s", str(e)[:160])
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass


async def evaluate(db, *, now: datetime | None = None) -> dict[str, Any]:
    """1회 heal 평가 사이클: 후보 도출 → 가드 통과분만 실행 → 결과 요약 반환.

    반환: {"candidates", "executed", "blocked", "escalated", "actions": [...]}.
    best-effort: 어떤 예외도 사이클을 죽이지 않는다.
    """
    now = now or datetime.now(UTC)
    summary = {"candidates": 0, "executed": 0, "closed": 0, "blocked": 0,
               "escalated": 0, "actions": []}
    try:
        candidates = await _candidate_actions(db, now)
    except Exception as e:  # noqa: BLE001
        logger.warning("heal 후보 도출 실패: %s", str(e)[:160])
        return summary

    summary["candidates"] = len(candidates)
    # 동일 (type, trigger_key) 후보는 1회만 평가(중복 제거).
    seen: set[tuple[str, str]] = set()

    for cand in candidates:
        atype = cand["type"]
        tkey = (cand.get("params") or {}).get("trigger_key") or atype
        dedup = (atype, tkey)
        if dedup in seen:
            continue
        seen.add(dedup)

        try:
            g_count, t_count, last_ts = await _guard_counts(db, atype, tkey, now)
        except Exception as e:  # noqa: BLE001
            logger.warning("heal 가드 카운트 실패(%s): %s", atype, str(e)[:120])
            continue

        decision = gate(atype, tkey, now=now, global_count=g_count,
                        trigger_count=t_count, last_ts=last_ts)

        if decision["escalate"]:
            await _escalate(db, atype, tkey)
            summary["escalated"] += 1

        if not decision["allow"]:
            summary["blocked"] += 1
            summary["actions"].append({"type": atype, "trigger_key": tkey,
                                       "executed": False, "reason": decision["reason"]})
            continue

        result = await heal_actions.execute(db, cand)
        if result.get("executed"):
            summary["executed"] += 1
            # ★피드백 고리를 닫는다 — 종전엔 여기서 끊겼다.
            #   자가치유는 실행되고 params 에 insight_id 까지 싣는데, 그 인사이트는
            #   영원히 `open` 이었다(라이브 실측 2026-08-27: heal 액션 520건 · `acted` 0건).
            #   ★상태값 `acted` 와 프론트 라벨 "조치됨" 은 **이미 있었다** — 쓰는 코드만 없었다.
            summary["closed"] += await mark_insight_acted(db, cand, result)
        summary["actions"].append({"type": atype, "trigger_key": tkey,
                                   "executed": bool(result.get("executed")),
                                   "action_id": result.get("action_id"),
                                   "reason": "ok"})
    return summary


__all__ = [
    "evaluate", "gate", "mark_insight_acted",
    # 순수 가드 함수(단위검증 공개).
    "_within_cooldown", "_cap_exceeded", "should_escalate",
    "GLOBAL_HOURLY_CAP", "PER_TRIGGER_HOURLY_CAP", "COOLDOWN_MIN",
    "ESCALATION_THRESHOLD", "TOTAL_OUTAGE_FALLBACK_PCT", "HANDLED_INSIGHT_TYPES",
]
