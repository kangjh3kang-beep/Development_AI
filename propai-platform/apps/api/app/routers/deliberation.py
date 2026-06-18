"""중심 엔진 통합 BFF — 심의/설계도면 자동분석 엔진(별도 서비스) 게이트웨이.

플랫폼은 엔진을 직접 import하지 않고(패키지명 `app` 충돌) 서버사이드 HTTP로 호출한다.
Phase 0: `GET /health` — 엔진 `/api/v1/doctor`를 인증 후 프록시하되 **화이트리스트 필드만** 재발행
(api_auth.enabled·*_key_present·master_key·model 등 보안태세 핑거프린트 비노출). 엔진 미연결 시 degraded.
설계: docs/CENTRAL_ENGINE_INTEGRATION_DESIGN.md(§4·§7 Phase0·§5).
"""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException

from app.services.auth.auth_service import get_current_user
from app.services.deliberation import binding_service
from app.services.deliberation._engine_contract import (
    analysis_input_hash,
    build_input_dump,
    content_input_hash,
)
from app.services.ledger.audit_ledger import append_audit
from apps.api.config import get_settings
from apps.api.integrations.base_client import CircuitBreaker

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/deliberation", tags=["심의분석 엔진"])

# 엔진 호출 circuit-breaker(프로세스 로컬·P1 단일워커 전제; 다중워커 Redis는 후속). 서버측 장애만 카운트.
_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=75.0, half_open_max=3)


async def _fetch_engine_doctor() -> dict[str, Any] | None:
    """엔진 `/api/v1/doctor` 조회. 미설정/실패/타임아웃 시 None(무음 단정 금지 — 호출측이 degraded 표면화).

    별도 함수로 분리해 테스트에서 monkeypatch(엔진 비의존). 외부 fetch는 여기 단일 choke point.
    """
    s = get_settings()
    base = (s.deliberation_engine_url or "").rstrip("/")
    if not base:
        return None
    try:
        import httpx

        headers = {}
        if s.deliberation_engine_api_token:
            headers["Authorization"] = f"Bearer {s.deliberation_engine_api_token}"
        timeout = httpx.Timeout(
            connect=s.deliberation_engine_connect_timeout_s,
            read=s.deliberation_engine_read_timeout_s,
            write=s.deliberation_engine_read_timeout_s,
            pool=s.deliberation_engine_connect_timeout_s,
        )
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as c:
            r = await c.get(f"{base}/api/v1/doctor", headers=headers)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else None
    except Exception:
        return None


def _whitelist_health(doctor: dict[str, Any]) -> dict[str, Any]:
    """엔진 doctor에서 **안전한 상태 필드만** 추출(핑거프린트 차단). 미지 구조는 .get으로 방어(크래시 0).

    노출: database.configured · sheet_classifier.live · jurisdiction.live · embedder.semantic.
    비노출: api_auth·*_key_present·master_key·model·mode·candidate_count 등 일체.
    """
    def _nested(key: str, sub: str) -> Any:
        node = doctor.get(key)
        return node.get(sub) if isinstance(node, dict) else None

    return {
        "database_configured": _nested("database", "configured"),
        "sheet_classifier_live": _nested("sheet_classifier", "live"),
        "jurisdiction_live": _nested("jurisdiction", "live"),
        "embedder_semantic": _nested("embedder", "semantic"),
    }


@router.get("/health")
async def deliberation_health(_user=Depends(get_current_user)) -> dict[str, Any]:
    """엔진 헬스(화이트리스트). 인증 필수. 미연결 시 degraded(무음0)."""
    doctor = await _fetch_engine_doctor()
    if doctor is None:
        return {"status": "degraded", "reason": "engine_unreachable", "engine": None}
    return {"status": "ok", "engine": _whitelist_health(doctor)}


# ── analyze BFF(§5) ────────────────────────────────────────────────────────────


def _tenant(user: Any) -> str:
    """테넌트 정규화 키(32자 소문자, 하이픈 없음) — 결속·격리 일관."""
    tid = getattr(user, "tenant_id", None)
    if isinstance(tid, uuid.UUID):
        return tid.hex
    return str(tid or "").replace("-", "").lower()


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _prevalidate(dump: dict[str, Any]) -> None:
    """엔진 KeyError→500 회피 — 필수 키 결손을 BFF에서 422로 선차단(무음0)."""
    for i, r in enumerate(dump.get("rules") or []):
        if not isinstance(r, dict) or "rule" not in r:
            raise HTTPException(status_code=422, detail=f"invalid_input:rules[{i}].rule_missing")
    for i, t in enumerate(dump.get("calc_targets") or []):
        if not isinstance(t, dict) or "target" not in t:
            raise HTTPException(status_code=422, detail=f"invalid_input:calc_targets[{i}].target_missing")
    for i, cf in enumerate(dump.get("cross_facts") or []):
        if not isinstance(cf, dict) or "fact_key" not in cf:
            raise HTTPException(status_code=422, detail=f"invalid_input:cross_facts[{i}].fact_key_missing")


def _degrade(reason: str) -> dict[str, Any]:
    """degrade 봉투(HTTP 200·무음0). 합성 결과 미생성(result=null)."""
    return {"degraded": True, "final_status": "NEEDS_REVIEW", "reason": reason,
            "engine_url": (get_settings().deliberation_engine_url or None),
            "result": None, "audit_degraded": False}


async def _record_audit(user: Any, tenant: str, *, action: str, run_id: str | None,
                        input_hash: str, decision: str, http_status: int) -> bool:
    """모든 요청 감사(append_audit). ok/unchanged 통과, quota_exceeded→audit_degraded(차단X),
    그 외 실패→502 fail-closed(감사 없는 판정 제공 금지). 반환=audit_degraded."""
    try:
        r = await append_audit(
            action=action, user_id=str(getattr(user, "id", "")), resource_type="deliberation",
            resource_id=str(run_id or "none"), tenant_id=tenant,
            metadata={"input_hash": input_hash, "decision": decision, "http_status": http_status},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="audit_write_failed") from exc
    if not isinstance(r, dict):
        return False
    if r.get("ok") is True or r.get("unchanged"):
        return False
    if r.get("quota_exceeded"):
        return True  # 감사 한도 — 분석은 제공하되 표면화
    raise HTTPException(status_code=502, detail="audit_write_failed")


async def _engine_post_analyze(dump: dict[str, Any]) -> dict[str, Any] | None:
    """엔진 POST /api/v1/analyze. 서버측 장애(5xx/타임아웃/circuit OPEN)→None(degrade). 4xx→None(breaker 제외)."""
    s = get_settings()
    base = (s.deliberation_engine_url or "").rstrip("/")
    if not base or not _breaker.can_execute():
        return None
    try:
        import httpx

        headers = {}
        if s.deliberation_engine_api_token:
            headers["Authorization"] = f"Bearer {s.deliberation_engine_api_token}"
        timeout = httpx.Timeout(
            connect=s.deliberation_engine_connect_timeout_s, read=s.deliberation_engine_read_timeout_s,
            write=s.deliberation_engine_read_timeout_s, pool=s.deliberation_engine_connect_timeout_s)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as c:
            r = await c.post(f"{base}/api/v1/analyze", json=dump, headers=headers)
        if r.status_code >= 500:
            _breaker.record_failure()
            return None
        _breaker.record_success()
        if r.status_code != 200:
            return None  # 4xx(매핑오류 등) — breaker 제외, degrade로 표면화
        data = r.json()
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        _breaker.record_failure()
        return None


async def _engine_get_analysis(run_id: str) -> dict[str, Any] | None:
    """엔진 GET /api/v1/analyze/{run_id}(저장 결과 조회). 실패 시 None."""
    s = get_settings()
    base = (s.deliberation_engine_url or "").rstrip("/")
    if not base:
        return None
    try:
        import httpx

        headers = {}
        if s.deliberation_engine_api_token:
            headers["Authorization"] = f"Bearer {s.deliberation_engine_api_token}"
        timeout = httpx.Timeout(connect=s.deliberation_engine_connect_timeout_s,
                                read=s.deliberation_engine_read_timeout_s,
                                write=s.deliberation_engine_read_timeout_s,
                                pool=s.deliberation_engine_connect_timeout_s)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as c:
            r = await c.get(f"{base}/api/v1/analyze/{run_id}", headers=headers)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


@router.post("/analyze")
async def deliberation_analyze(payload: dict = Body(...), user=Depends(get_current_user)) -> dict[str, Any]:
    """심의분석 — 인증·미러 정규화·멱등 결속·엔진 프록시·무결성/테넌트 가드·감사. 엔진 무수정(HTTP)."""
    tenant = _tenant(user)
    try:
        dump = build_input_dump(payload)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — pydantic ValidationError 등
        raise HTTPException(status_code=422, detail="invalid_input") from exc
    _prevalidate(dump)

    cih = content_input_hash(dump)
    ih = analysis_input_hash(dump)
    snapshot = dump.get("snapshot_id")

    # 멱등 — 동일 입력 재호출 차단(엔진 재호출 없이 기존 결과 재사용).
    existing = await binding_service.lookup(tenant_id=tenant, content_input_hash=cih, snapshot_id=snapshot)
    if existing is not None:
        run_id = existing["run_id"]
        result = existing.get("result") or await _engine_get_analysis(run_id)
        audit_degraded = await _record_audit(user, tenant, action="analyze_reuse", run_id=run_id,
                                              input_hash=ih, decision="reuse", http_status=200)
        return {"degraded": False, "reused": True, "run_id": run_id,
                "result": result, "audit_degraded": audit_degraded}

    res = await _engine_post_analyze(dump)
    if res is None:
        await _record_audit(user, tenant, action="analyze", run_id=None,
                            input_hash=ih, decision="degraded", http_status=200)
        return _degrade("engine_unreachable")

    # 무결성 — input_hash parity + run_id 유효(엔진 run_id Optional이라 None 통과 가능). 위반=무음 통과 금지.
    if res.get("input_hash") != ih or not _is_uuid(res.get("run_id")):
        await _record_audit(user, tenant, action="analyze", run_id=None,
                            input_hash=ih, decision="degraded", http_status=200)
        return _degrade("invalid_response")

    run_id = str(res["run_id"])
    inserted = await binding_service.insert(
        run_id=run_id, tenant_id=tenant, content_input_hash=cih, snapshot_id=snapshot,
        input_hash=ih, source="sync", created_by=str(getattr(user, "id", "")))
    if not inserted:  # 동시성 경합 — 기존 결속 재사용
        again = await binding_service.lookup(tenant_id=tenant, content_input_hash=cih, snapshot_id=snapshot)
        if again is not None:
            run_id = again["run_id"]

    audit_degraded = await _record_audit(user, tenant, action="analyze", run_id=run_id,
                                         input_hash=ih, decision="authoritative", http_status=200)
    return {"degraded": False, "reused": False, "run_id": run_id,
            "result": res, "audit_degraded": audit_degraded}
