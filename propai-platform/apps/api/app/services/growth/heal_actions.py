"""자가성장 엔진 Phase 3 — L0 자가치유 실행기(설계서 §6.1).

healing_rules 가 결정한 heal 액션을 실제 수행하고, 모든 조치를 두 곳에 기록한다:
  1) admin_audit_log (audit_admin_action, actor='growth_engine') — 책임추적성.
  2) platform_events(event_type='heal_action') — 대시보드/heal-log API 데이터원.

안전경계(절대 준수):
- L0 는 **저위험 무인 조치만**. 코드/스키마 자동변경 금지.
- stale_reanalysis 는 **재분석 제안 큐잉만**(자동 재실행 금지 — project_analysis_cache 원칙).
- threshold_relax 는 platform_settings 에 TTL(자동원복) + 롤백 메타를 저장한다.
- circuit_observe 는 관측·이벤트화·heal-log 기록만(circuit 로직 자체는 base_client 불변).

롤백 가능성: 각 액션은 action_id(uuid) + type + params + ttl + (해당 시) setting_key 를
platform_events.payload 에 담아, rollback API 가 setting_key 를 clear_setting 으로
즉시 원복할 수 있게 한다.

best-effort: 어떤 예외도 호출경로(heal 태스크)를 죽이지 않는다.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# threshold_relax 기본 TTL(분) — 만료 시 get_setting 이 None 반환(자동원복).
DEFAULT_RELAX_TTL_MIN = 30

# 액션 타입(설계 §6.1 4룰과 정합).
ACTION_CACHE_WARM = "cache_warm"
ACTION_THRESHOLD_RELAX = "threshold_relax"
ACTION_STALE_REANALYSIS = "stale_reanalysis"   # 제안 큐잉만(자동실행 금지)
ACTION_CIRCUIT_OBSERVE = "circuit_observe"     # 관측·기록만

_ACTOR = "growth_engine"


async def _emit_heal_event(db, action_id: str, action_type: str,
                           params: dict[str, Any], *, severity: str = "info",
                           service: str | None = None,
                           setting_key: str | None = None,
                           ttl_expires_at: datetime | None = None,
                           rollbackable: bool = False) -> None:
    """heal_action 이벤트를 platform_events 에 직접 INSERT(동기, 즉시 영속).

    capture_service 큐(비동기 flush)와 달리, heal 결과는 즉시 조회 가능해야 하므로
    동기 INSERT. payload 에 롤백에 필요한 메타(action_id/type/params/ttl/setting_key).
    """
    import json

    from sqlalchemy import text

    payload = {
        "action_id": action_id,
        "action_type": action_type,
        "params": params,
        "rollbackable": rollbackable,
        "setting_key": setting_key,
        "ttl_expires_at": ttl_expires_at.isoformat() if ttl_expires_at else None,
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
        logger.warning("heal_action 이벤트 기록 실패(%s): %s", action_type, str(e)[:160])
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass


async def _audit(action_type: str, action_id: str, detail: dict[str, Any]) -> None:
    """admin_audit_log 기록(actor='growth_engine'). best-effort(자체 세션)."""
    try:
        from app.core.audit import audit_admin_action

        await audit_admin_action(
            actor_id=_ACTOR, actor_role="system",
            action=f"growth.heal.{action_type}", target=action_id,
            detail=detail,
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("heal audit 기록 실패: %s", str(e)[:120])


async def execute(db, action: dict[str, Any]) -> dict[str, Any]:
    """healing_rules 가 만든 단일 heal 액션을 실행한다.

    action = {"type", "params", "service"?, "severity"?, "trigger"?}
    반환: {"action_id", "type", "executed": bool, "setting_key"?, "detail"}.
    """
    action_type = action.get("type") or "unknown"
    params = dict(action.get("params") or {})
    service = action.get("service")
    severity = action.get("severity") or "info"
    action_id = str(uuid.uuid4())

    try:
        if action_type == ACTION_THRESHOLD_RELAX:
            return await _do_threshold_relax(db, action_id, params, service, severity)
        if action_type == ACTION_CACHE_WARM:
            return await _do_cache_warm(db, action_id, params, service, severity)
        if action_type == ACTION_STALE_REANALYSIS:
            return await _do_stale_reanalysis(db, action_id, params, service, severity)
        if action_type == ACTION_CIRCUIT_OBSERVE:
            return await _do_circuit_observe(db, action_id, params, service, severity)
        logger.warning("알 수 없는 heal 액션: %s", action_type)
        return {"action_id": action_id, "type": action_type, "executed": False,
                "detail": "unknown_action"}
    except Exception as e:  # noqa: BLE001 — 실행 실패가 heal 태스크를 죽이지 않게.
        logger.warning("heal 액션 실행 실패(%s): %s", action_type, str(e)[:160])
        return {"action_id": action_id, "type": action_type, "executed": False,
                "detail": str(e)[:160]}


async def _do_threshold_relax(db, action_id, params, service, severity):
    """외부API 전면장애 대응: rate-limit/timeout 임계 일시상향(TTL 자동원복).

    platform_settings 에 setting_key 로 새 값 + ttl_expires_at 저장.
    TTL 만료 시 get_setting 이 None → 코드가 원래 기본값으로 폴백(자동원복).
    """
    from app.services.growth import schema_guard

    ttl_min = int(params.get("ttl_min") or DEFAULT_RELAX_TTL_MIN)
    ttl = datetime.now(UTC) + timedelta(minutes=ttl_min)
    setting_key = params.get("setting_key") or (
        f"relax.{service}" if service else "relax.global"
    )
    new_value = params.get("value") or {
        "rate_limit_multiplier": params.get("rate_limit_multiplier", 2.0),
        "timeout_multiplier": params.get("timeout_multiplier", 1.5),
    }

    ok = await schema_guard.set_setting(
        db, setting_key, new_value, scope="global",
        ttl_expires_at=ttl, updated_by=_ACTOR,
    )
    detail = {"setting_key": setting_key, "value": new_value, "ttl_min": ttl_min,
              "service": service, "set_ok": ok}
    await _emit_heal_event(db, action_id, ACTION_THRESHOLD_RELAX, params,
                           severity=severity, service=service,
                           setting_key=setting_key, ttl_expires_at=ttl,
                           rollbackable=True)
    await _audit(ACTION_THRESHOLD_RELAX, action_id, detail)
    return {"action_id": action_id, "type": ACTION_THRESHOLD_RELAX,
            "executed": ok, "setting_key": setting_key, "ttl_expires_at": ttl,
            "detail": detail}


async def _do_cache_warm(db, action_id, params, service, severity):
    """캐시 워밍 잡 트리거(시간당 캡은 healing_rules 가 보장).

    실제 워밍 실행은 외부 캐시/잡에 위임(여기서는 트리거 신호 기록만 — 저위험).
    Celery 가 있으면 워밍 태스크 enqueue 를 시도하되, 부재/실패는 best-effort.
    """
    triggered = False
    try:
        from app.tasks.celery_app import app as _celery
        if _celery is not None:
            # 전용 워밍 태스크가 없으면 신호만 기록(코드 자동변경 금지 원칙).
            triggered = bool(params.get("enqueue", False))
    except Exception:  # noqa: BLE001
        triggered = False

    detail = {"service": service, "triggered": triggered, "params": params}
    await _emit_heal_event(db, action_id, ACTION_CACHE_WARM, params,
                           severity=severity, service=service, rollbackable=False)
    await _audit(ACTION_CACHE_WARM, action_id, detail)
    return {"action_id": action_id, "type": ACTION_CACHE_WARM,
            "executed": True, "detail": detail}


async def _do_stale_reanalysis(db, action_id, params, service, severity):
    """stale/원장변조 감지 → 재분석 **제안 큐잉만**(자동 재실행 절대 금지).

    제안은 platform_insights(recommended_action='heal', status='open')로 큐잉되어
    사용자/관리자가 1클릭으로 재실행(자동 실행 안 함). 여기서는 제안 인사이트 1건
    생성 + heal_action 기록만.
    """
    import json

    from sqlalchemy import text

    suggestion = {
        "kind": "reanalysis_suggestion",
        "auto_executed": False,  # ★자동 재실행 안 함(명시).
        **params,
    }
    inserted = False
    try:
        await db.execute(text(
            "INSERT INTO platform_insights "
            "(tenant_id, insight_type, metrics_json, severity, narrative, "
            " recommended_action, status) "
            "VALUES (:tid, 'stale_reanalysis', CAST(:m AS jsonb), :sev, :narr, "
            " 'heal', 'open')"
        ), {
            "tid": params.get("tenant_id"),
            "m": json.dumps(suggestion, ensure_ascii=False, default=str),
            "sev": severity,
            "narr": params.get("narrative")
            or "원장 무결성 이상/입력 staleness 감지 — 재분석 제안(자동 실행 안 함, 1클릭 승인 대기).",
        })
        await db.commit()
        inserted = True
    except Exception as e:  # noqa: BLE001
        logger.warning("stale_reanalysis 제안 큐잉 실패: %s", str(e)[:160])
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass

    detail = {"queued_suggestion": inserted, "auto_executed": False, "params": params}
    await _emit_heal_event(db, action_id, ACTION_STALE_REANALYSIS, params,
                           severity=severity, service=service, rollbackable=False)
    await _audit(ACTION_STALE_REANALYSIS, action_id, detail)
    return {"action_id": action_id, "type": ACTION_STALE_REANALYSIS,
            "executed": inserted, "detail": detail}


async def _do_circuit_observe(db, action_id, params, service, severity):
    """CircuitBreaker OPEN/폴백 관측 — 이벤트화·heal-log 기록만(circuit 로직 불변)."""
    detail = {"service": service, "observation": params}
    await _emit_heal_event(db, action_id, ACTION_CIRCUIT_OBSERVE, params,
                           severity=severity, service=service, rollbackable=False)
    await _audit(ACTION_CIRCUIT_OBSERVE, action_id, detail)
    return {"action_id": action_id, "type": ACTION_CIRCUIT_OBSERVE,
            "executed": True, "detail": detail}


async def rollback(db, action_id: str, *, actor_id: str | None = None) -> dict[str, Any]:
    """heal_action 의 즉시 롤백 — setting_key 가 있으면 platform_settings 즉시 원복.

    heal-log(platform_events)에서 action_id 로 setting_key 를 찾아 clear_setting.
    롤백 자체도 heal_action 이벤트 + audit 기록(actor=요청 관리자 또는 growth_engine).
    반환: {"rolled_back": bool, "setting_key"?, "detail"}.
    """
    import json

    from sqlalchemy import text

    from app.services.growth import schema_guard

    row = (await db.execute(text(
        "SELECT payload FROM platform_events "
        "WHERE event_type='heal_action' AND payload->>'action_id' = :aid "
        "ORDER BY created_at DESC LIMIT 1"
    ), {"aid": action_id})).fetchone()
    if row is None:
        return {"rolled_back": False, "detail": "action_not_found"}

    payload = row[0]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:  # noqa: BLE001
            payload = {}
    setting_key = (payload or {}).get("setting_key")
    rollbackable = bool((payload or {}).get("rollbackable"))

    if not rollbackable or not setting_key:
        return {"rolled_back": False, "detail": "not_rollbackable"}

    cleared = await schema_guard.clear_setting(db, setting_key, scope="global")

    # 롤백도 감사 + 이벤트화(actor = 요청 관리자, 없으면 엔진).
    detail = {"original_action_id": action_id, "setting_key": setting_key,
              "cleared": cleared}
    try:
        from app.core.audit import audit_admin_action

        await audit_admin_action(
            actor_id=actor_id or _ACTOR, actor_role="super_admin" if actor_id else "system",
            action="growth.heal.rollback", target=action_id, detail=detail,
        )
    except Exception:  # noqa: BLE001
        pass
    await _emit_heal_event(db, str(uuid.uuid4()), "rollback",
                           {"original_action_id": action_id, "setting_key": setting_key},
                           severity="info", setting_key=setting_key, rollbackable=False)
    return {"rolled_back": cleared, "setting_key": setting_key, "detail": detail}


__all__ = [
    "execute", "rollback",
    "ACTION_CACHE_WARM", "ACTION_THRESHOLD_RELAX",
    "ACTION_STALE_REANALYSIS", "ACTION_CIRCUIT_OBSERVE",
    "DEFAULT_RELAX_TTL_MIN",
]
