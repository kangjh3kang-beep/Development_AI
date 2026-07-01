"""자가성장 엔진 Phase 4 — L1 자가수정(설계서 §6.2).

데이터 기반 **저위험 자동수정**만 수행한다. 모든 변경은 platform_settings 에
기록(즉시 롤백 가능 = clear_setting) + admin_audit_log(actor='growth_engine').

L1 자동수정 4종(설계 §6.2):
  1) 임계값 자동보정(threshold_autotune)
     - error_cluster/fallback 임계를 baseline 분포(직전 인사이트)로 재계산.
     - ★변경폭 상한 ±20%/회(CHANGE_CAP_PCT). 한 번에 큰 점프 금지.
     - platform_settings('threshold.<name>') 에 저장. analyzer 가 best-effort 참조 가능.
  2) 피처플래그 토글(feature_toggle)
     - 특정 기능 오류율 급등 시 자동 비활성(degrade gracefully).
     - ★사전등록 화이트리스트(AUTO_TOGGLEABLE) 기능만. critical 기능(CRITICAL_FEATURES) 제외.
     - platform_settings('feature.<name>') = {"enabled": false, ...}.
  3) 프롬프트 A/B 자동채택(prompt_ab_adopt)
     - service별 A/B 버전 중 품질↑(verify pass + feedback up) 버전을 채택 기록.
     - ★사전등록 후보군(PROMPT_AB_CANDIDATES) 내에서만 선택(임의 버전 생성 금지).
     - platform_settings('prompt.<service>') = {"version": "<chosen>", ...}.

안전경계(절대 준수):
- 무인 자동이되 **저위험만 + 화이트리스트/후보군 내에서만 + 즉시 롤백 + 감사**.
- 임의 값 생성 금지(후보군 내 선택·상한 내 조정만).
- 가드(쿨다운·시간당 캡)는 healing_rules 의 platform_events(heal_action) 기반 가드를
  재사용한다(워커 간 공유 상태). L1 조치도 heal_action 이벤트로 기록 → 동일 가드 적용.

판정·계산 로직은 stdlib 만으로 단위검증 가능하도록 순수 함수로 분리한다
(clamp_change/_pick_better_version/_should_disable — DB·LLM 무의존).
best-effort: 어떤 예외도 호출경로(L1 태스크)를 죽이지 않는다.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.growth import healing_rules

logger = logging.getLogger(__name__)

_ACTOR = "growth_engine"

# ── L1 액션 타입(heal_action 이벤트로 기록 → 가드 재사용) ─────────────────────
ACTION_THRESHOLD_AUTOTUNE = "threshold_autotune"
ACTION_FEATURE_TOGGLE = "feature_toggle"
ACTION_PROMPT_AB_ADOPT = "prompt_ab_adopt"

# ── 안전장치 상수(설계 §6.2) ────────────────────────────────────────────────
# 임계 자동보정 1회 변경폭 상한(±20%). 한 번에 큰 점프 금지.
CHANGE_CAP_PCT = 20.0

# 자동 토글 가능한 기능 화이트리스트(이 목록의 기능만 자동 비활성 가능).
AUTO_TOGGLEABLE = {
    "llm_narrative",       # 분석 narrative LLM 보조(끄면 규칙 narrative 폴백).
    "regional_benchmark",  # 지역시세 벤치마크 근거 주입(끄면 미부착).
    "redis_cache",         # 인터프리터 L2 Redis 캐시(끄면 L1만).
}
# critical 기능 — 절대 자동 토글 금지(서비스 핵심). 화이트리스트에 있어도 보호.
CRITICAL_FEATURES = {
    "auth", "billing", "rbac", "ledger", "verifier", "payment", "secrets",
}

# 피처 자동 비활성 트리거: 해당 기능/서비스 오류율(%)이 이 값 이상.
FEATURE_DISABLE_ERROR_PCT = 40.0
FEATURE_MIN_SAMPLES = 10

# 프롬프트 A/B 사전등록 후보군(service → 허용 버전 목록). 이 안에서만 채택.
PROMPT_AB_CANDIDATES: dict[str, list[str]] = {
    # 기본은 base_interpreter._PROMPT_VERSION 과 동일한 'v2'. 후보 등록은 Phase 5 가 확장.
    # 예: "market": ["v2", "v3"]. 후보가 없으면 자동채택 비대상(기본 버전 유지).
}
# A/B 채택 최소 표본(verify+feedback 합). 너무 적으면 채택 보류.
PROMPT_AB_MIN_SAMPLES = 20


# ════════════════════════════════════════════════════════════════════════════
# 순수 함수군 (DB/LLM 무의존 — inline 단위검증 대상)
# ════════════════════════════════════════════════════════════════════════════

def clamp_change(current: float, proposed: float, cap_pct: float = CHANGE_CAP_PCT) -> float:
    """proposed 가 current 대비 ±cap_pct%를 넘으면 상한값으로 잘라 반환한다.

    current 가 0/음수면(기준 없음) proposed 를 그대로 통과(상한 비교 불가).
    예: current=20, proposed=40, cap=20% → 24 로 클램프(상향 20%).
        current=20, proposed=10, cap=20% → 16 으로 클램프(하향 20%).
    """
    if current <= 0:
        return proposed
    upper = current * (1.0 + cap_pct / 100.0)
    lower = current * (1.0 - cap_pct / 100.0)
    if proposed > upper:
        return round(upper, 4)
    if proposed < lower:
        return round(lower, 4)
    return round(proposed, 4)


def _should_disable(error_pct: float, samples: int) -> bool:
    """기능 오류율이 임계 이상이고 표본이 충분하면 자동 비활성 대상."""
    if samples < FEATURE_MIN_SAMPLES:
        return False
    return error_pct >= FEATURE_DISABLE_ERROR_PCT


def is_auto_toggleable(feature: str) -> bool:
    """기능이 자동 토글 가능한가? 화이트리스트 ∈ AND critical 기능 ∉."""
    if feature in CRITICAL_FEATURES:
        return False
    return feature in AUTO_TOGGLEABLE


def _pick_better_version(
    service: str, stats: dict[str, dict[str, Any]]
) -> tuple[str | None, dict[str, Any]]:
    """service 의 버전별 품질통계에서 더 나은 버전을 후보군 내에서 고른다.

    stats = {version: {"pass": int, "fail": int, "up": int, "down": int, "samples": int}}
    품질 점수 = pass율 + up율(높을수록 좋음). 후보군(PROMPT_AB_CANDIDATES[service]) 에
    속한 버전만 비교 대상. 표본 부족·후보 없음·동률이면 (None, meta).
    """
    allowed = set(PROMPT_AB_CANDIDATES.get(service) or [])
    if not allowed:
        return None, {"reason": "no_candidates"}

    scored: list[tuple[str, float, int]] = []
    for ver, s in stats.items():
        if ver not in allowed:
            continue
        samples = int(s.get("samples") or 0)
        if samples < PROMPT_AB_MIN_SAMPLES:
            continue
        vtotal = int(s.get("pass", 0)) + int(s.get("fail", 0))
        ftotal = int(s.get("up", 0)) + int(s.get("down", 0))
        pass_rate = (s.get("pass", 0) / vtotal) if vtotal else 0.0
        up_rate = (s.get("up", 0) / ftotal) if ftotal else 0.0
        scored.append((ver, round(pass_rate + up_rate, 4), samples))

    if len(scored) < 2:
        return None, {"reason": "insufficient_versions", "scored": scored}
    scored.sort(key=lambda x: x[1], reverse=True)
    best, best_score, _ = scored[0]
    _, second_score, _ = scored[1]
    if best_score <= second_score:  # 동률은 채택 보류(결정론·안정성).
        return None, {"reason": "tie", "scored": scored}
    return best, {"reason": "ok", "chosen": best, "scored": scored}


# ════════════════════════════════════════════════════════════════════════════
# L1 조치 실행기 — platform_settings 기록 + heal_action 이벤트 + 감사
# ════════════════════════════════════════════════════════════════════════════

async def _emit_l1_event(db, action_id: str, action_type: str, trigger_key: str,
                         setting_key: str, params: dict[str, Any], *,
                         severity: str = "info", service: str | None = None) -> None:
    """L1 조치를 heal_action 이벤트로 기록(가드 카운트·heal-log·롤백 메타 공유).

    rollbackable=True + setting_key 를 담아 기존 heal_actions.rollback API 가
    그대로 동작한다(별도 롤백 경로 불필요). 동기 INSERT(즉시 조회 가능).
    """
    import json

    from sqlalchemy import text

    payload = {
        "action_id": action_id,
        "action_type": action_type,
        "params": {"trigger_key": trigger_key, **params},
        "rollbackable": True,
        "setting_key": setting_key,
        "ttl_expires_at": None,
        "actor": _ACTOR,
    }
    try:
        await db.execute(text(
            "INSERT INTO platform_events "
            "(event_id, event_type, surface, severity, service, payload, created_at) "
            "VALUES (:eid, 'heal_action', 'worker', :sev, :svc, "
            " CAST(:pl AS jsonb), now()) "
            "ON CONFLICT (event_id) DO NOTHING"
        ), {
            "eid": action_id, "sev": severity, "svc": service,
            "pl": json.dumps(payload, ensure_ascii=False, default=str),
        })
        await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("L1 이벤트 기록 실패(%s): %s", action_type, str(e)[:160])
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass


async def _audit(action_type: str, action_id: str, detail: dict[str, Any]) -> None:
    """admin_audit_log 기록(actor='growth_engine'). best-effort."""
    try:
        from app.core.audit import audit_admin_action

        await audit_admin_action(
            actor_id=_ACTOR, actor_role="system",
            action=f"growth.correct.{action_type}", target=action_id,
            detail=detail,
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("L1 audit 실패: %s", str(e)[:120])


async def apply_threshold_autotune(
    db, name: str, current: float, proposed: float, *,
    trigger_key: str | None = None, severity: str = "info",
) -> dict[str, Any]:
    """임계값 자동보정 — ±20% 상한 클램프 후 platform_settings('threshold.<name>') 저장.

    반환: {"action_id","applied","setting_key","old","new","clamped"}.
    """
    from app.services.growth import schema_guard

    action_id = str(uuid.uuid4())
    clamped = clamp_change(current, proposed, CHANGE_CAP_PCT)
    setting_key = f"threshold.{name}"
    value = {"value": clamped, "previous": current, "proposed": proposed,
             "cap_pct": CHANGE_CAP_PCT}
    ok = await schema_guard.set_setting(db, setting_key, value, scope="global",
                                        updated_by=_ACTOR)
    tkey = trigger_key or f"threshold:{name}"
    await _emit_l1_event(db, action_id, ACTION_THRESHOLD_AUTOTUNE, tkey, setting_key,
                         {"name": name, "old": current, "new": clamped},
                         severity=severity)
    await _audit(ACTION_THRESHOLD_AUTOTUNE, action_id,
                 {"setting_key": setting_key, "old": current, "new": clamped,
                  "proposed": proposed, "set_ok": ok})
    return {"action_id": action_id, "applied": ok, "setting_key": setting_key,
            "old": current, "new": clamped,
            "clamped": clamped != round(proposed, 4)}


async def apply_feature_toggle(
    db, feature: str, *, enabled: bool, error_pct: float | None = None,
    trigger_key: str | None = None, severity: str = "warn",
) -> dict[str, Any]:
    """피처플래그 토글 — 화이트리스트 기능만, critical 제외. platform_settings 저장.

    반환: {"action_id","applied","setting_key","feature","enabled","reason"}.
    """
    from app.services.growth import schema_guard

    action_id = str(uuid.uuid4())
    if not is_auto_toggleable(feature):
        # ★화이트리스트 밖/critical 기능은 자동 토글 거부(안전경계).
        return {"action_id": action_id, "applied": False, "feature": feature,
                "enabled": enabled, "reason": "not_auto_toggleable"}

    setting_key = f"feature.{feature}"
    value = {"enabled": enabled, "auto": True, "error_pct": error_pct}
    ok = await schema_guard.set_setting(db, setting_key, value, scope="global",
                                        updated_by=_ACTOR)
    tkey = trigger_key or f"feature:{feature}"
    await _emit_l1_event(db, action_id, ACTION_FEATURE_TOGGLE, tkey, setting_key,
                         {"feature": feature, "enabled": enabled, "error_pct": error_pct},
                         severity=severity)
    await _audit(ACTION_FEATURE_TOGGLE, action_id,
                 {"setting_key": setting_key, "feature": feature,
                  "enabled": enabled, "error_pct": error_pct, "set_ok": ok})
    return {"action_id": action_id, "applied": ok, "setting_key": setting_key,
            "feature": feature, "enabled": enabled, "reason": "ok"}


async def apply_prompt_ab(
    db, service: str, version: str, *, stats_meta: dict[str, Any] | None = None,
    trigger_key: str | None = None,
) -> dict[str, Any]:
    """프롬프트 A/B 자동채택 — 후보군 내 버전만 platform_settings('prompt.<service>') 기록.

    반환: {"action_id","applied","setting_key","service","version","reason"}.
    """
    from app.services.growth import schema_guard

    action_id = str(uuid.uuid4())
    allowed = set(PROMPT_AB_CANDIDATES.get(service) or [])
    if version not in allowed:
        # ★사전등록 후보군 밖 버전은 채택 거부(임의 값 생성 금지).
        return {"action_id": action_id, "applied": False, "service": service,
                "version": version, "reason": "not_in_candidates"}

    setting_key = f"prompt.{service}"
    value = {"version": version, "auto": True, "stats": stats_meta or {}}
    ok = await schema_guard.set_setting(db, setting_key, value, scope="global",
                                        updated_by=_ACTOR)
    tkey = trigger_key or f"prompt:{service}"
    await _emit_l1_event(db, action_id, ACTION_PROMPT_AB_ADOPT, tkey, setting_key,
                         {"service": service, "version": version})
    await _audit(ACTION_PROMPT_AB_ADOPT, action_id,
                 {"setting_key": setting_key, "service": service,
                  "version": version, "stats": stats_meta or {}, "set_ok": ok})
    return {"action_id": action_id, "applied": ok, "setting_key": setting_key,
            "service": service, "version": version, "reason": "ok"}


# ════════════════════════════════════════════════════════════════════════════
# L1 평가 사이클 — open 인사이트/이벤트를 보고 L1 후보를 도출·가드통과분만 실행
# ════════════════════════════════════════════════════════════════════════════

async def _ab_stats(db, w_hours: int = 24) -> dict[str, dict[str, dict[str, Any]]]:
    """service × prompt_version 별 품질통계 집계(verify pass/fail + feedback up/down).

    ★M-2 해소: 과거엔 llm_call payload.ok(=pass)/samples 만 채우고 up/down/fail 이
    항상 0 이라 _pick_better_version 점수가 실데이터를 반영하지 못했다. 이제:
      - llm_call.prompt_version 으로 service×version 의 samples(+ ok 기반 pass) 집계.
      - ai_feedback(up/down) 을 service 단위로 집계해 그 service 의 **모든 version**에
        귀속(피드백은 버전 라벨이 없으므로 동일 service 의 후보 버전들에 공통 반영).
      - verify_result(fail) 을 service 단위로 집계해 동일 방식으로 fail 에 귀속.
    버전 라벨이 없는 환경에서는 빈 dict → A/B 채택 비대상(기본 버전 유지). best-effort.
    """
    from sqlalchemy import text

    out: dict[str, dict[str, dict[str, Any]]] = {}
    since = datetime.now(UTC) - timedelta(hours=w_hours)

    def _ver_slot(svc: str, ver: str) -> dict[str, Any]:
        return out.setdefault(svc, {}).setdefault(
            ver, {"pass": 0, "fail": 0, "up": 0, "down": 0, "samples": 0}
        )

    # (1) llm_call: service×version 의 samples + pass(ok=true) — 버전별 1차 신호.
    try:
        rows = (await db.execute(text(
            "SELECT service, payload->>'prompt_version' AS ver, "
            "  SUM(CASE WHEN severity='info' AND payload->>'ok'='true' THEN 1 ELSE 0 END) AS ok, "
            "  COUNT(*) AS total "
            "FROM platform_events "
            "WHERE event_type='llm_call' AND service IS NOT NULL "
            "  AND payload->>'prompt_version' IS NOT NULL AND created_at >= :since "
            "GROUP BY service, payload->>'prompt_version'"
        ), {"since": since})).fetchall()
        for r in rows:
            d = _ver_slot(r[0], r[1])
            d["pass"] += int(r[2] or 0)
            d["samples"] += int(r[3] or 0)
    except Exception as e:  # noqa: BLE001
        logger.debug("ab_stats llm_call 집계 실패: %s", str(e)[:120])

    # (2) ai_feedback: service 단위 up/down → 그 service 의 모든 version 에 귀속.
    try:
        fb = (await db.execute(text(
            "SELECT service, "
            "  SUM(CASE WHEN verdict='up' THEN 1 ELSE 0 END) AS up, "
            "  SUM(CASE WHEN verdict='down' THEN 1 ELSE 0 END) AS down "
            "FROM ai_feedback "
            "WHERE service IS NOT NULL AND created_at >= :since "
            "GROUP BY service"
        ), {"since": since})).fetchall()
        for r in fb:
            svc = r[0]
            vers = out.get(svc)
            if not vers:
                continue  # 버전 라벨 없는 service 는 A/B 비대상(스킵).
            for d in vers.values():
                d["up"] += int(r[1] or 0)
                d["down"] += int(r[2] or 0)
    except Exception as e:  # noqa: BLE001
        logger.debug("ab_stats feedback 집계 실패: %s", str(e)[:120])

    # (3) verify_result: service 단위 fail → 그 service 의 모든 version 에 귀속.
    try:
        vr = (await db.execute(text(
            "SELECT service, "
            "  SUM(CASE WHEN severity='fail' OR payload->>'verdict'='fail' "
            "           THEN 1 ELSE 0 END) AS fail "
            "FROM platform_events "
            "WHERE event_type='verify_result' AND service IS NOT NULL "
            "  AND created_at >= :since "
            "GROUP BY service"
        ), {"since": since})).fetchall()
        for r in vr:
            svc = r[0]
            vers = out.get(svc)
            if not vers:
                continue
            for d in vers.values():
                d["fail"] += int(r[1] or 0)
    except Exception as e:  # noqa: BLE001
        logger.debug("ab_stats verify 집계 실패: %s", str(e)[:120])

    return out


async def evaluate(db, *, now: datetime | None = None) -> dict[str, Any]:
    """1회 L1 자가수정 사이클: 후보 도출 → 가드 통과분만 실행 → 요약 반환.

    가드(쿨다운·시간당 캡)는 healing_rules.gate + _guard_counts(platform_events
    heal_action 기반)를 재사용한다(L1 조치도 heal_action 이벤트로 기록되므로 동일
    카운트 대상). best-effort: 어떤 예외도 사이클을 죽이지 않는다.

    반환: {"candidates","applied","blocked","actions":[...]}.
    """
    from sqlalchemy import text

    now = now or datetime.now(UTC)
    summary: dict[str, Any] = {"candidates": 0, "applied": 0, "blocked": 0, "actions": []}

    candidates: list[dict[str, Any]] = []
    try:
        # ── (1) 임계 자동보정: fallback_rate 인사이트의 baseline 분포로 재계산 ──
        # 최근 fallback_rate 인사이트들의 fallback_pct 평균을 baseline 으로 보고,
        # 현재 임계(FALLBACK_WARN_PCT)를 ±20% 내에서 그 분포 쪽으로 수렴.
        from app.services.growth import analyzer
        frows = (await db.execute(text(
            "SELECT (metrics_json->>'fallback_pct')::float "
            "FROM platform_insights "
            "WHERE insight_type='fallback_rate' AND created_at >= :since "
            "  AND metrics_json->>'fallback_pct' IS NOT NULL"
        ), {"since": now - timedelta(days=7)})).fetchall()
        pcts = [float(r[0]) for r in frows if r[0] is not None]
        if len(pcts) >= 5:
            baseline = sum(pcts) / len(pcts)
            # 제안 임계 = baseline 의 1.5배(정상범위 위) — 단, 현재값 대비 ±20% 클램프는 실행기가.
            proposed = round(baseline * 1.5, 2)
            candidates.append({
                "kind": ACTION_THRESHOLD_AUTOTUNE,
                "name": "fallback_warn_pct",
                "current": analyzer.FALLBACK_WARN_PCT,
                "proposed": proposed,
                "trigger_key": "threshold:fallback_warn_pct",
            })

        # ── (2) 피처 토글: quality_drop/error_cluster 가 critical 이면 보조기능 비활성 제안 ──
        qrows = (await db.execute(text(
            "SELECT metrics_json FROM platform_insights "
            "WHERE insight_type='quality_drop' AND severity IN ('warn','critical') "
            "  AND status='open' AND created_at >= :since LIMIT 50"
        ), {"since": now - timedelta(hours=6)})).fetchall()
        for r in qrows:
            m = r[0] if isinstance(r[0], dict) else {}
            ftotal = int(m.get("feedback_total") or 0)
            vtotal = int(m.get("verify_total") or 0)
            down_pct = float(m.get("down_pct") or 0.0)
            # 품질 급락 시 보조기능(llm_narrative)만 자동 비활성(저위험·degrade gracefully).
            if down_pct >= FEATURE_DISABLE_ERROR_PCT and (ftotal + vtotal) >= FEATURE_MIN_SAMPLES:
                candidates.append({
                    "kind": ACTION_FEATURE_TOGGLE,
                    "feature": "llm_narrative", "enabled": False,
                    "error_pct": down_pct,
                    "trigger_key": "feature:llm_narrative",
                })

        # ── (3) 프롬프트 A/B 자동채택: 후보군 있는 service 만(없으면 스킵) ──
        if PROMPT_AB_CANDIDATES:
            stats = await _ab_stats(db)
            for service, vstats in stats.items():
                best, meta = _pick_better_version(service, vstats)
                if best:
                    candidates.append({
                        "kind": ACTION_PROMPT_AB_ADOPT,
                        "service": service, "version": best, "stats_meta": meta,
                        "trigger_key": f"prompt:{service}",
                    })
    except Exception as e:  # noqa: BLE001
        logger.warning("L1 후보 도출 실패: %s", str(e)[:160])
        return summary

    summary["candidates"] = len(candidates)
    seen: set[tuple[str, str]] = set()

    for cand in candidates:
        kind = cand["kind"]
        tkey = cand.get("trigger_key") or kind
        dedup = (kind, tkey)
        if dedup in seen:
            continue
        seen.add(dedup)

        # 가드: healing_rules 의 캡/쿨다운 재사용(heal_action 이벤트 카운트 기반).
        try:
            g_count, t_count, last_ts = await healing_rules._guard_counts(db, kind, tkey, now)
        except Exception as e:  # noqa: BLE001
            logger.warning("L1 가드 카운트 실패(%s): %s", kind, str(e)[:120])
            continue
        decision = healing_rules.gate(kind, tkey, now=now, global_count=g_count,
                                      trigger_count=t_count, last_ts=last_ts)
        if not decision["allow"]:
            summary["blocked"] += 1
            summary["actions"].append({"kind": kind, "trigger_key": tkey,
                                       "applied": False, "reason": decision["reason"]})
            continue

        if kind == ACTION_THRESHOLD_AUTOTUNE:
            res = await apply_threshold_autotune(
                db, cand["name"], float(cand["current"]), float(cand["proposed"]),
                trigger_key=tkey,
            )
        elif kind == ACTION_FEATURE_TOGGLE:
            res = await apply_feature_toggle(
                db, cand["feature"], enabled=cand["enabled"],
                error_pct=cand.get("error_pct"), trigger_key=tkey,
            )
        elif kind == ACTION_PROMPT_AB_ADOPT:
            res = await apply_prompt_ab(
                db, cand["service"], cand["version"],
                stats_meta=cand.get("stats_meta"), trigger_key=tkey,
            )
        else:
            continue

        if res.get("applied"):
            summary["applied"] += 1
        summary["actions"].append({"kind": kind, "trigger_key": tkey,
                                   "applied": bool(res.get("applied")),
                                   "action_id": res.get("action_id"),
                                   "reason": res.get("reason", "ok")})
    return summary


# 가드 타입별 캡/쿨다운 등록(healing_rules 사전을 L1 액션 타입으로 확장).
# healing_rules.gate 는 미등록 타입에 기본값(g_cap=5, t_cap=2, cooldown=15)을 쓰므로
# L1 액션도 안전한 기본 가드 하에 동작한다. 명시 등록으로 의도를 드러낸다.
for _at, _gcap, _tcap, _cd in (
    (ACTION_THRESHOLD_AUTOTUNE, 2, 1, 60),
    (ACTION_FEATURE_TOGGLE, 4, 2, 30),
    (ACTION_PROMPT_AB_ADOPT, 2, 1, 360),
):
    healing_rules.GLOBAL_HOURLY_CAP.setdefault(_at, _gcap)
    healing_rules.PER_TRIGGER_HOURLY_CAP.setdefault(_at, _tcap)
    healing_rules.COOLDOWN_MIN.setdefault(_at, _cd)


__all__ = [
    "evaluate",
    "apply_threshold_autotune", "apply_feature_toggle", "apply_prompt_ab",
    # 순수 함수(단위검증 공개).
    "clamp_change", "is_auto_toggleable", "_pick_better_version", "_should_disable",
    # 상수.
    "CHANGE_CAP_PCT", "AUTO_TOGGLEABLE", "CRITICAL_FEATURES",
    "PROMPT_AB_CANDIDATES", "PROMPT_AB_MIN_SAMPLES",
    "ACTION_THRESHOLD_AUTOTUNE", "ACTION_FEATURE_TOGGLE", "ACTION_PROMPT_AB_ADOPT",
]
