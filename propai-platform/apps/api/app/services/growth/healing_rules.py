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
# 에스컬레이션 임계: 동일 트리거가 시간당 이 횟수 이상 **캡에 막히면** 효과없음으로 보고 critical 승격.
#
# ★2026-08-27 — 이 상수는 **바뀌지 않았다.** 바뀐 것은 **무엇을 세는가** 다.
#   종전에는 `_guard_counts` 의 **실행수**(heal_action 이벤트)를 셌는데, 그 값은
#   `_cap_exceeded(count, cap)` 가 `count >= cap` 에서 실행을 막으므로 **t_cap 을 넘을 수 없었다**:
#       cache_warm 1 · threshold_relax 2 · stale_reanalysis 3 · circuit_observe 10
#   즉 임계 5 에 닿을 수 있는 것은 `circuit_observe` **하나뿐**이었고, 그 액션은 스스로를
#   "관측 기록(부작용 없음)" 이라 적는다 — **에스컬레이션이 필요 없는 것만 에스컬레이션할 수 있었다.**
#   라이브 실측(2026-08-27): heal_escalation **전 상태 0건**(대조군 fallback_rate 26 · 음성 0),
#   heal-log 472 시간버킷 중 캡 도달 24(5.1%) · **임계 도달 0(0.0%)**.
#   ★상수를 올리거나 내리는 길은 **기각**이다 — 캡을 올리면 `threshold_relax` 가 프로덕션 HTTP
#   타임아웃을 더 곱하고(볼트 2026-08-25 사고), 임계를 내리면 한 번 막힌 것도 에스컬레이션된다.
ESCALATION_THRESHOLD = 5

#: 캡 차단 시도를 남기는 이벤트 타입(heal_action 과 **분리** — 기존 집계·화면·가드에 무영향).
HEAL_BLOCKED_EVENT = "heal_blocked"

#: 차단 시도를 **기록**하는 사유(관측용). 쿨다운은 정상 페이싱이라 넣지 않는다 —
#  `gate()` 가 쿨다운을 캡보다 **먼저** 판정하고 즉시 반환하므로 구조적으로 안 들어온다.
CAP_BLOCK_REASONS = ("global_cap", "trigger_cap")

#: ★에스컬레이션으로 **세는** 사유는 `trigger_cap` **하나뿐**이다(기록 대상보다 좁다).
#
#  ★2026-08-27 독립 적대 리뷰가 잡은 결함: 종전에는 `CAP_BLOCK_REASONS` 전체를 셌는데,
#  시뮬(beat 10분·6시간)로 재 보니 임계에 닿게 해 주는 것이 **전부 `global_cap`** 이었다:
#      cache_warm      n=2 → 계수차단 41건이 **전부 global_cap** · 발화 31
#      threshold_relax n=1 → trigger_cap 15건뿐 · 발화 **0**
#  `global_cap` 은 *"이 트리거의 치유가 무효"* 가 아니라 *"지금 아픈 서비스가 여럿"* 이다.
#  그걸 critical 로 올리면 서사(*"반복 발화했으나 효과가 없어"*)가 **거짓말**이 된다 —
#  전역 예산에 막힌 트리거는 **한 번도 발화한 적이 없다.**
#  → 기록은 둘 다 하되(관측 가치가 있다) **판정은 `trigger_cap` 만** 쓴다.
ESCALATION_COUNT_REASONS = ("trigger_cap",)

#: 캡차단 시도를 세는 창(시간). ★캡·임계 상수를 건드리지 않고 도달 가능성을 만드는 축이다.
#
#  캡은 **시간당** 정의라 `trigger_cap` 차단도 시간당 상한이 있다
#  (`threshold_relax`: 쿨다운 15분·beat 10분 → 시간당 실행 ≤2 · trigger_cap 차단 ≤4).
#  **≤4 < 임계 5** 이므로 1시간 창에서는 여전히 도달 불가다. 창을 3시간으로 두면
#  누적되어 도달 가능해진다(시뮬 실측 ≈2.5건/시 → 3시간 ≈7.5 ≥ 5).
#  ★캡을 올리거나(프로덕션 타임아웃 곱 증가) 임계를 내리는(한 번 막혀도 승격) 길을
#  피하면서 도달 가능성을 얻는 유일한 축이라 이것을 골랐다.
ESCALATION_WINDOW_HOURS = 3

#: 억제 대상 상태 — **아직 사람 손에 있는** 것만. `dismissed`·`acted`·`superseded` 는
#  억제하지 않는다(재발하면 다시 올라와야 한다).
_SUPPRESSING_STATUSES = ("open", "acknowledged")

#: ★`dismissed` 는 **창 안에서만** 억제한다(나이 무관 억제 아님).
#
#  독립 적대 리뷰(2026-08-27)가 내 M-4 논증의 **거울상**을 짚었다. 내가 `acknowledged` 를
#  넣은 근거는 *"`open` 만 보면 사람이 ack 하는 **순간 다음 beat(≤10분)에 같은 critical 이
#  새로 생긴다**"* 였는데, **그 문장이 `dismissed` 에 글자 그대로 성립한다**:
#  `_blocked_count` 는 창(`ESCALATION_WINDOW_HOURS`) 안의 계수 행을 셀 뿐이고
#  **기각은 그 행을 지우지 않는다**(실측: `DELETE FROM platform_events` **0건** ·
#  대조군 다른 `DELETE` 25건으로 조회기 생존 확인). 그래서 기각 직후에도
#  `blocked_prior >= 5` 가 유지돼 **조건이 지속되는 한 최대 3시간 반복**된다.
#
#  ★근본은 **이 기전에 「재발」을 재는 축이 없다**는 것이다 — 창에 남은 잔여를 셀 뿐이라
#  *"같은 에피소드가 계속되는 것"* 과 *"기각 후 재발"* 을 **원리적으로 구별하지 못한다.**
#  `platform_insights` 에 상태변경 시각이 없어(UPDATE 가 `status` 만 쓴다) 새 열 없이
#  가르려면 **창으로 경계**를 짓는 수밖에 없다:
#      · 에피소드 동안(창 안) → 기각이 유지된다(≤10분 부활 없음)
#      · 창이 비워진 뒤의 **진짜 재발** → 다시 올라온다(원래 의도 보존)
#  ★그래서 **억제가 은신처가 되지 않는다** — 창이 지나면 자동으로 열린다(§D-19).
_DISMISSED_SUPPRESS_WITHIN_WINDOW = True

# 외부API "전면장애" 판정: 폴백률(%) 이 이 값 이상이면 threshold_relax 대상.
TOTAL_OUTAGE_FALLBACK_PCT = 50.0


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


def should_escalate(blocked_attempts: int, threshold: int = ESCALATION_THRESHOLD) -> bool:
    """동일 트리거가 시간당 threshold 이상 **캡에 막히면** 에스컬레이션.

    ★인자는 **실행수가 아니라 캡차단 시도수**다(ESCALATION_THRESHOLD 주석 참조).
      실행수는 캡이 천장을 씌우므로 임계에 닿을 수 없었다 — 그것이 이 안전망이
      라이브에서 **한 번도 발화하지 않은** 이유다.

    의미도 이쪽이 더 곧다: *"같은 트리거가 계속 치유를 원하는데 못 하고 있다"* 가
    *"몇 번 실행했다"* 보다 **사람이 봐야 한다**는 신호에 가깝다.
    """
    return blocked_attempts >= threshold


def gate(action_type: str, trigger_key: str, *, now: datetime,
         global_count: int, trigger_count: int, last_ts: datetime | None,
         blocked_count: int = 0) -> dict[str, Any]:
    """단일 후보 액션의 통과/차단을 종합 판정한다(순수 함수, 단위검증 진입점).

    반환: {"allow": bool, "reason": str, "escalate": bool}.
      - 쿨다운 내 → 차단.
      - 전역/트리거 캡 초과 → 차단.
      - 모두 통과 → allow.

    ★`escalate` 는 **`blocked_count`(최근 1시간 캡차단 시도수)** 로만 정해진다.
      기본값 0 이므로 이 인자를 주지 않는 호출부(`feature_flags`)의 동작은 **종전과 같다**.
      `trigger_count`(실행수)는 **더 이상 에스컬레이션 입력이 아니다** — 캡이 천장을
      씌워 임계에 닿을 수 없었기 때문이다(ESCALATION_THRESHOLD 주석).
    """
    cooldown = COOLDOWN_MIN.get(action_type, 15)
    g_cap = GLOBAL_HOURLY_CAP.get(action_type, 5)
    t_cap = PER_TRIGGER_HOURLY_CAP.get(action_type, 2)

    escalate = should_escalate(blocked_count)

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


async def _record_blocked(db, action_type: str, trigger_key: str, reason: str,
                          now: datetime) -> None:
    """캡에 막힌 **시도**를 남긴다 — 에스컬레이션이 셀 수 있는 유일한 흔적.

    ★왜 필요한가: 차단된 후보는 `execute()` 앞에서 빠지므로 `heal_action` 이벤트가
      생기지 않는다. 그래서 종전에는 **막힐수록 카운터가 조용해졌다**(캡에서 얼어붙음).
    ★`reason` 을 **싣는다** — 안 실으면 배포 후에도 "global 이었나 trigger 였나"를
      사후에 가를 수 없다(독립 리뷰 지적). 판정은 `trigger_cap` 만 쓰지만
      `global_cap` 도 기록해 전역 예산 포화를 관측 가능하게 둔다.
    ★멱등키: 형제(`heal_actions._record`·`feature_flags`)와 **같은 패턴**으로
      `event_id` + `ON CONFLICT DO NOTHING` 을 쓴다. beat 중복 발화·태스크 재전달이
      있으면 카운터가 **배로 세어 임계에 절반 시간에 닿기** 때문이다.
      키는 (타입·트리거·분) 이라 같은 분의 중복만 접는다.

    best-effort: 기록 실패가 치유 사이클을 죽이지 않는다.

    ★변이 감사 기록(2026-08-27): 이 함수와 `_blocked_count` 의 `logger.warning` **문구**는
      변이에 생존한다. **구멍이 아니다** — 문구는 계약이 아니라 표현이라, 단언하면
      다듬을 때마다 깨지는 취약한 락이 된다(§G-30). 대신 이 두 함수의 **계약**
      (표·열·JSON 경로·창 경계·이벤트 타입 구분·사유 필터)은 전부 잠갔다:
      `tests/test_heal_escalation_reachable.py` 참조.
      ★남은 생존은 **서사(narrative) 문구**와 `logger.warning` 문구 6건뿐이고, 둘 다
      계약이 아니라 표현이라 단언하지 않는다(다듬을 때마다 깨지는 취약한 락이 된다).
    """
    import json
    import uuid

    from sqlalchemy import text

    eid = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"heal_blocked:{action_type}:{trigger_key}:{now.strftime('%Y-%m-%dT%H:%M')}"))
    try:
        await db.execute(text(
            "INSERT INTO platform_events (event_id, event_type, payload) "
            "VALUES (CAST(:eid AS uuid), :et, CAST(:p AS jsonb)) "
            "ON CONFLICT (event_id) DO NOTHING"
        ), {"eid": eid, "et": HEAL_BLOCKED_EVENT,
            "p": json.dumps({"action_type": action_type, "reason": reason,
                             "params": {"trigger_key": trigger_key}},
                            ensure_ascii=False)})
        await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("heal 차단기록 실패(%s): %s", action_type, str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()


async def _blocked_count(db, action_type: str, trigger_key: str, now: datetime) -> int:
    """최근 `ESCALATION_WINDOW_HOURS` 시간 동안 이 트리거가 **`trigger_cap` 에 막힌 횟수**.

    ★`global_cap` 차단은 **세지 않는다**(기록은 된다) — 그건 전역 예산 경합이지
      이 트리거의 치유가 무효라는 뜻이 아니다.

    실패하면 0 을 돌려준다 — 조회 실패가 **없던 에스컬레이션을 만들지 않게** 한다
    (거짓 critical 은 그 자체로 결함이다).
    """
    from sqlalchemy import text

    since = now - timedelta(hours=ESCALATION_WINDOW_HOURS)
    try:
        return int((await db.execute(text(
            "SELECT COUNT(*) FROM platform_events "
            "WHERE event_type = :et "
            "  AND payload->>'action_type' = :at "
            "  AND payload->'params'->>'trigger_key' = :tk "
            "  AND payload->>'reason' = ANY(:reasons) "
            "  AND created_at >= :since"
        ), {"et": HEAL_BLOCKED_EVENT, "at": action_type,
            "tk": trigger_key, "reasons": list(ESCALATION_COUNT_REASONS),
            "since": since})).scalar() or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("heal 차단수 조회 실패(%s): %s", action_type, str(e)[:160])
        return 0


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
    rows = (await db.execute(text(
        "SELECT id, insight_type, severity, metrics_json FROM platform_insights "
        "WHERE status='open' AND recommended_action IN ('heal','none','correct') "
        "  AND created_at >= :since "
        "ORDER BY created_at DESC LIMIT 200"
    ), {"since": now - timedelta(hours=2)})).fetchall()

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


async def _escalate(db, action_type: str, trigger_key: str, now: datetime) -> bool:
    """효과없는 반복 조치 → critical 인사이트로 승격(사람 알림). best-effort.

    반환: **새로 만들었으면 True**, 억제됐거나 실패했으면 False.

    ★축 단위 중복 억제: 같은 `(action_type, trigger_key)` 에 **아직 사람 손에 있는**
      `heal_escalation` 이 있으면 새로 만들지 않는다. 억제가 없으면 한 트리거가 화면을
      채운다 — 드라이런에서 캡 도달 24건 중 **18건이 한 트리거**였다.

    ★억제 대상 상태는 `open` **과 `acknowledged` 둘 다**다(`_SUPPRESSING_STATUSES`).
      독립 리뷰 지적: `acknowledged` 는 *"봤고 조치 중"* 이라 관리자 전이에 실재하는데
      (`routers/growth.py` 의 `_ACK_STATUSES`·`allowed_from`), `open` 만 보면 사람이
      ack 하는 **순간 다음 beat(≤10분)에 같은 critical 이 새로 생긴다.**
      그러면 이 타입에서 `acknowledged` 가 **쓸 수 없는 상태**가 되고,
      설계가 가르려던 두 상태(`acknowledged` = 조치 중 / `dismissed` = 기각)가 붕괴한다.

    ★`dismissed`·`acted`·`superseded` 는 **억제하지 않는다** — 사람이 기각한 뒤 문제가
      **재발하면 다시 올라와야** 하기 때문이다. 억제가 은신처가 되면 안 된다(§D-19).
    """
    import json

    from sqlalchemy import text

    try:
        dup = (await db.execute(text(
            "SELECT 1 FROM platform_insights "
            "WHERE insight_type = 'heal_escalation' "
            "  AND metrics_json->>'action_type' = :at "
            "  AND metrics_json->>'trigger_key' = :tk "
            "  AND ( status = ANY(:statuses) "
            "     OR (status = 'dismissed' AND created_at >= :since) ) "
            "LIMIT 1"
        ), {"statuses": list(_SUPPRESSING_STATUSES),
            "since": now - timedelta(hours=ESCALATION_WINDOW_HOURS),
            "at": action_type, "tk": trigger_key})).fetchone()
        if dup is not None:
            return False
        await db.execute(text(
            "INSERT INTO platform_insights "
            "(insight_type, metrics_json, severity, narrative, recommended_action, status) "
            "VALUES ('heal_escalation', CAST(:m AS jsonb), 'critical', :narr, "
            " 'propose_pr', 'open')"
        ), {
            "m": json.dumps({"action_type": action_type, "trigger_key": trigger_key,
                             "reason": "auto_heal_ineffective"}, ensure_ascii=False),
            # ★서사는 `trigger_cap` 의 실제 의미만 말한다. 종전 문구 *"반복 발화했으나"* 는
            #   `global_cap` 으로 막힌 트리거(한 번도 발화한 적 없다)에도 붙어 **거짓**이었다.
            "narr": (f"자동치유가 반복해서 한도에 막혔습니다: {action_type}({trigger_key}) 가 "
                     f"최근 {ESCALATION_WINDOW_HOURS}시간 동안 시간당 한도(trigger_cap)에 "
                     f"{ESCALATION_THRESHOLD}회 이상 막혀 조치가 나가지 못했습니다. "
                     f"자동치유로 해소되지 않는 상태이므로 사람 점검이 필요합니다."),
        })
        await db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("heal 에스컬레이션 실패: %s", str(e)[:160])
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False


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

        # ★에스컬레이션 입력은 **캡차단 시도수**다(실행수 아님 — ESCALATION_THRESHOLD 주석).
        #   여기서 세는 것은 **직전까지의 이력**이고, 이번 사이클의 차단은 아래에서 기록해
        #   다음 사이클이 센다. 그래서 임계 5 는 "이미 5회 막혔는데 또 막힌다"를 뜻한다.
        blocked_prior = await _blocked_count(db, atype, tkey, now)

        decision = gate(atype, tkey, now=now, global_count=g_count,
                        trigger_count=t_count, last_ts=last_ts,
                        blocked_count=blocked_prior)

        if not decision["allow"]:
            # 캡에 막힌 시도만 남긴다 — 쿨다운은 정상 페이싱이라 기록하지 않는다.
            # ★사유를 함께 싣는다: 기록은 global/trigger 둘 다, **판정은 trigger 만**.
            if decision["reason"] in CAP_BLOCK_REASONS:
                await _record_blocked(db, atype, tkey, decision["reason"], now)
            if decision["escalate"] and await _escalate(db, atype, tkey, now):
                summary["escalated"] += 1
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
    "ESCALATION_THRESHOLD", "TOTAL_OUTAGE_FALLBACK_PCT",
    "HEAL_BLOCKED_EVENT", "CAP_BLOCK_REASONS",
    "ESCALATION_COUNT_REASONS", "ESCALATION_WINDOW_HOURS",
    "_SUPPRESSING_STATUSES", "_DISMISSED_SUPPRESS_WITHIN_WINDOW",
]
