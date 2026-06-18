"""중심 엔진 통합 BFF — 심의/설계도면 자동분석 엔진(별도 서비스) 게이트웨이.

플랫폼은 엔진을 직접 import하지 않고(패키지명 `app` 충돌) 서버사이드 HTTP로 호출한다.
Phase 0: `GET /health` — 엔진 `/api/v1/doctor`를 인증 후 프록시하되 **화이트리스트 필드만** 재발행
(api_auth.enabled·*_key_present·master_key·model 등 보안태세 핑거프린트 비노출). 엔진 미연결 시 degraded.
설계: docs/CENTRAL_ENGINE_INTEGRATION_DESIGN.md(§4·§7 Phase0·§5).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError

from app.services.auth.auth_service import get_current_user
from app.services.deliberation import binding_service
from app.services.deliberation._engine_contract import (
    analysis_input_hash,
    build_input_dump,
    content_input_hash,
    is_deterministic_path,
    prevalidate,
)
from app.services.ledger.audit_ledger import append_audit
from apps.api.config import get_settings
from apps.api.integrations.base_client import CircuitBreaker

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/deliberation", tags=["심의분석 엔진"])

# 엔진 호출 circuit-breaker(프로세스 로컬·P1 단일워커 전제; 다중워커 Redis는 후속). 서버측 장애만 카운트.
_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=75.0, half_open_max=3)


async def _fetch_engine_doctor() -> tuple[dict[str, Any] | None, str]:
    """엔진 `/api/v1/doctor` 조회 → (data, reason). reason: ok·timeout·engine_unreachable(미설정/5xx/연결)
    ·engine_rejected(4xx 토큰/계약)·invalid_response(malformed-200). analyze 경로와 동일 구분(정직성).

    별도 함수로 분리해 테스트에서 monkeypatch(엔진 비의존). 외부 fetch는 여기 단일 choke point.
    except는 httpx 오류로 한정 — 내부 프로그래밍 버그는 500으로 전파(degrade 위장 금지).
    """
    import httpx

    s = get_settings()
    base = (s.deliberation_engine_url or "").rstrip("/")
    if not base:
        return None, "engine_unreachable"
    try:
        timeout = httpx.Timeout(
            connect=s.deliberation_engine_connect_timeout_s,
            read=s.deliberation_engine_read_timeout_s,
            write=s.deliberation_engine_read_timeout_s,
            pool=s.deliberation_engine_connect_timeout_s,
        )
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as c:
            r = await c.get(f"{base}/api/v1/doctor", headers=_engine_headers(s))
    except httpx.TimeoutException:
        logger.warning("deliberation_doctor_timeout")
        return None, "timeout"
    except httpx.HTTPError as exc:
        logger.warning("deliberation_doctor_failed", err=str(exc)[:200])
        return None, "engine_unreachable"
    if r.status_code >= 500:
        logger.warning("deliberation_doctor_5xx", status=r.status_code)
        return None, "engine_unreachable"
    if r.status_code != 200:
        logger.warning("deliberation_doctor_4xx", status=r.status_code)  # 토큰 오설정 가시화
        return None, "engine_rejected"
    try:
        data = r.json()
    except ValueError:  # malformed-200 — 엔진 도달했으나 본문 계약위반(POST와 대칭)
        logger.warning("deliberation_doctor_malformed_200")
        return None, "invalid_response"
    return (data, "ok") if isinstance(data, dict) else (None, "invalid_response")


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
    """엔진 헬스(화이트리스트). 인증 필수. 미연결/거부 시 degraded(reason 구분·무음0). 토큰 미설정 경고 표면화."""
    s = get_settings()
    warnings: list[str] = []
    if s.deliberation_engine_url and not s.deliberation_engine_api_token:
        warnings.append("engine_token_missing")  # URL 설정·토큰 미설정 → 무인증 호출(운영자 인지)
    doctor, reason = await _fetch_engine_doctor()
    if doctor is None:
        return {"status": "degraded", "reason": reason, "engine": None, "warnings": warnings}
    return {"status": "ok", "engine": _whitelist_health(doctor), "warnings": warnings}


# ── analyze BFF(§5) ────────────────────────────────────────────────────────────


def _tenant(user: Any) -> str:
    """테넌트 정규화 키(32자 소문자, 하이픈 없음) — 결속(engine_run_binding)·엔진 X-Tenant-Id 격리 일관."""
    tid = getattr(user, "tenant_id", None)
    if isinstance(tid, uuid.UUID):
        return tid.hex
    return str(tid or "").replace("-", "").lower()


def _audit_tenant(user: Any) -> str:
    """감사 체인 키 — 플랫폼 표준(append_audit(tenant_id=str(tenant_id)), 하이픈 UUID)과 동일 표기.
    ⚠️ _tenant(hex)와 분리: 동일 테넌트의 심의 감사가 플랫폼 타 감사와 같은 audit_stream(__audit__/<tenant>)에
    적재돼 단일 verify_audit_chain으로 검증되도록(hex/하이픈 분열 방지). binding 키는 hex 유지(metadata 교차참조)."""
    return str(getattr(user, "tenant_id", "") or "")


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _degrade(reason: str, *, audit_degraded: bool = False,
             audit_skipped: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    """degrade 봉투(HTTP 200·무음0). 합성 결과 미생성(result=null). 내부 URL 비노출(engine_configured bool)."""
    return {"degraded": True, "final_status": "NEEDS_REVIEW", "reason": reason,
            "engine_configured": bool(get_settings().deliberation_engine_url),
            "result": None, "audit_degraded": audit_degraded,
            "audit_skipped": audit_skipped or [], **extra}


async def _record_audit(user: Any, tenant: str, *, action: str, run_id: str | None, input_hash: str,
                        decision: str, http_status: int, fail_closed: bool = True) -> tuple[bool, list[str]]:
    """감사(append_audit). ok/unchanged 통과; quota_exceeded→(audit_degraded, skipped) 표면화(차단X);
    그 외 실패→write는 502 fail-closed(감사 없는 판정 제공 금지), read는 표면화만(fail_closed=False).
    반환=(audit_degraded, audit_skipped)."""
    try:
        r = await append_audit(
            action=action, user_id=str(getattr(user, "id", "")), resource_type="deliberation",
            resource_id=str(run_id or "none"), tenant_id=_audit_tenant(user),  # 플랫폼 표준 체인 키
            metadata={"input_hash": input_hash, "decision": decision, "http_status": http_status,
                      "binding_tenant": tenant},  # 결속 hex 교차참조(체인 키와 분리)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("deliberation_audit_failed", action=action, err=str(exc)[:200])
        if fail_closed:
            raise HTTPException(status_code=502, detail="audit_write_failed") from exc
        return True, ["audit:write_failed"]
    if isinstance(r, dict) and (r.get("ok") is True or r.get("unchanged")):
        return False, []
    if isinstance(r, dict) and r.get("quota_exceeded"):
        logger.warning("deliberation_audit_quota_exceeded", tenant=tenant, action=action)
        # write 경로(fail_closed): 쿼터로 원장 미적재면 감사 없는 권위 판정 제공 금지(write_failed와 위험 동일).
        if fail_closed:
            raise HTTPException(status_code=502, detail="audit_quota_exceeded")
        return True, ["audit:quota_exceeded"]
    logger.warning("deliberation_audit_not_ok", action=action, ret=str(r)[:120])
    if fail_closed:
        raise HTTPException(status_code=502, detail="audit_write_failed")
    return True, ["audit:not_ok"]


def _engine_headers(s: Any, tenant: str | None = None) -> dict[str, str]:
    h: dict[str, str] = {}
    if s.deliberation_engine_api_token:
        h["Authorization"] = f"Bearer {s.deliberation_engine_api_token}"
    if tenant:
        h["X-Tenant-Id"] = tenant  # #8a 심층방어 — 엔진이 organization_id로 적재/소유필터
    return h


def _engine_timeout(s: Any, deterministic: bool = True):
    import httpx
    # 비결정(라이브 네트워크: 지오코딩/VWORLD/임베딩) 경로는 더 긴 async read 타임아웃 — 조기 타임아웃→오탐 차단.
    read = s.deliberation_engine_read_timeout_s if deterministic else s.deliberation_engine_async_read_timeout_s
    return httpx.Timeout(connect=s.deliberation_engine_connect_timeout_s, read=read,
                         write=read, pool=s.deliberation_engine_connect_timeout_s)


async def _engine_post_analyze(dump: dict[str, Any], deterministic: bool = True,
                               *, tenant: str | None = None,
                               breaker: CircuitBreaker | None = None) -> tuple[dict[str, Any] | None, str]:
    """엔진 POST /api/v1/analyze → (data, reason). reason: ok·circuit_open·timeout·engine_unreachable(5xx/연결)
    ·engine_rejected(4xx 계약/매핑, breaker 제외)·invalid_response(malformed-200). 4xx와 미연결 구분(무음0).
    deterministic=False면 async read 타임아웃 적용(라이브 네트워크 경로 조기 타임아웃 방지).
    breaker 주입 시 권위 _breaker 대신 사용(관측/shadow 경로가 운영 회로를 오염시키지 않도록 격리)."""
    import httpx

    bk = breaker or _breaker
    s = get_settings()
    base = (s.deliberation_engine_url or "").rstrip("/")
    if not base:
        return None, "engine_unreachable"
    if not bk.can_execute():
        return None, "circuit_open"
    try:
        async with httpx.AsyncClient(timeout=_engine_timeout(s, deterministic), follow_redirects=False) as c:
            r = await c.post(f"{base}/api/v1/analyze", json=dump, headers=_engine_headers(s, tenant))
    except httpx.TimeoutException:  # 타임아웃 별도 표면화(연결실패와 구분)
        bk.record_failure()
        logger.warning("deliberation_engine_post_timeout")
        return None, "timeout"
    except httpx.HTTPError as exc:  # 연결/전송 오류만 breaker failure(내부 버그는 전파)
        bk.record_failure()
        logger.warning("deliberation_engine_post_failed", err=str(exc)[:200])
        return None, "engine_unreachable"
    if r.status_code >= 500:
        bk.record_failure()
        logger.warning("deliberation_engine_5xx", status=r.status_code)
        return None, "engine_unreachable"
    bk.record_success()  # 엔진 도달(<500) → 회복(4xx/malformed-200도 도달이므로 success·중립)
    if r.status_code != 200:
        logger.warning("deliberation_engine_4xx", status=r.status_code)  # 본문 미기록(테넌트 입력 PII 누출 방지)
        return None, "engine_rejected"  # 계약/매핑 — breaker 제외
    try:
        data = r.json()
    except ValueError:  # malformed-200 = 본문 계약위반(중립) — record_failure 이중기록·오라벨 방지
        logger.warning("deliberation_engine_malformed_200")
        return None, "invalid_response"
    return (data, "ok") if isinstance(data, dict) else (None, "invalid_response")


async def _engine_get_analysis(run_id: str, *, tenant: str | None = None) -> tuple[dict[str, Any] | None, str]:
    """엔진 GET /api/v1/analyze/{run_id} → (data, reason). reason: ok·circuit_open·timeout·not_found(404)
    ·engine_rejected(그 외 4xx)·engine_unreachable(5xx/연결)·invalid_response(malformed). POST와 breaker 대칭."""
    import httpx

    s = get_settings()
    base = (s.deliberation_engine_url or "").rstrip("/")
    if not base:
        return None, "engine_unreachable"
    if not _breaker.can_execute():
        return None, "circuit_open"  # reuse/GET 경로도 폭주 차단(post와 대칭)
    try:
        # run_id URL 인코딩(defense-in-depth) — DB-출처/UUID이나 경로 주입/SSRF 표면 사전 차단.
        async with httpx.AsyncClient(timeout=_engine_timeout(s), follow_redirects=False) as c:
            r = await c.get(f"{base}/api/v1/analyze/{quote(run_id, safe='')}", headers=_engine_headers(s, tenant))
    except httpx.TimeoutException:
        _breaker.record_failure()
        logger.warning("deliberation_engine_get_timeout", run_id=run_id)
        return None, "timeout"
    except httpx.HTTPError as exc:  # 연결/전송 오류만 breaker failure(내부 버그는 전파)
        _breaker.record_failure()
        logger.warning("deliberation_engine_get_failed", run_id=run_id, err=str(exc)[:200])
        return None, "engine_unreachable"
    if r.status_code >= 500:
        _breaker.record_failure()
        logger.warning("deliberation_engine_get_5xx", run_id=run_id, status=r.status_code)
        return None, "engine_unreachable"
    _breaker.record_success()  # 엔진 도달(2xx/4xx) → 회복 카운트
    if r.status_code == 404:
        logger.warning("deliberation_engine_run_missing", run_id=run_id)
        return None, "not_found"
    if r.status_code != 200:
        logger.warning("deliberation_engine_get_4xx", run_id=run_id, status=r.status_code)
        return None, "engine_rejected"
    try:
        data = r.json()
    except ValueError:  # malformed-200 — POST와 대칭(계약위반=invalid_response, 미연결 아님)
        logger.warning("deliberation_engine_get_malformed_200", run_id=run_id)
        return None, "invalid_response"
    return (data, "ok") if isinstance(data, dict) else (None, "invalid_response")


def _get_degrade_reason(greason: str) -> str:
    """엔진 GET reason → degrade reason 매핑(404·4xx·circuit·계약위반 구분 보존, 그외 engine_unreachable)."""
    return {"not_found": "result_missing", "engine_rejected": "engine_rejected",
            "circuit_open": "circuit_open", "invalid_response": "invalid_response",
            "timeout": "timeout"}.get(greason, "engine_unreachable")


async def _engine_post_async(dump: dict[str, Any], *, tenant: str | None = None) -> tuple[dict[str, Any] | None, str]:
    """엔진 POST /api/v1/analyze/async → ({task_id,status,eager,result?}, reason). breaker 대칭.
    비결정/대용량 경로라 async read 타임아웃 적용. eager(broker 없음)면 result 즉시 포함."""
    import httpx

    s = get_settings()
    base = (s.deliberation_engine_url or "").rstrip("/")
    if not base:
        return None, "engine_unreachable"
    if not _breaker.can_execute():
        return None, "circuit_open"
    try:
        async with httpx.AsyncClient(timeout=_engine_timeout(s, deterministic=False), follow_redirects=False) as c:
            r = await c.post(f"{base}/api/v1/analyze/async", json=dump, headers=_engine_headers(s, tenant))
    except httpx.TimeoutException:
        _breaker.record_failure()
        logger.warning("deliberation_async_post_timeout")
        return None, "timeout"
    except httpx.HTTPError as exc:
        _breaker.record_failure()
        logger.warning("deliberation_async_post_failed", err=str(exc)[:200])
        return None, "engine_unreachable"
    if r.status_code >= 500:
        _breaker.record_failure()
        logger.warning("deliberation_async_5xx", status=r.status_code)
        return None, "engine_unreachable"
    _breaker.record_success()
    if r.status_code != 200:
        logger.warning("deliberation_async_4xx", status=r.status_code)
        return None, "engine_rejected"
    try:
        data = r.json()
    except ValueError:
        return None, "invalid_response"
    return (data, "ok") if isinstance(data, dict) and data.get("task_id") else (None, "invalid_response")


async def _engine_get_task(task_id: str, *, tenant: str | None = None) -> tuple[dict[str, Any] | None, str]:
    """엔진 GET /api/v1/analyze/task/{task_id} → ({task_id,status,ready,result}, reason). breaker 대칭."""
    import httpx

    s = get_settings()
    base = (s.deliberation_engine_url or "").rstrip("/")
    if not base:
        return None, "engine_unreachable"
    if not _breaker.can_execute():
        return None, "circuit_open"
    try:
        async with httpx.AsyncClient(timeout=_engine_timeout(s), follow_redirects=False) as c:
            r = await c.get(f"{base}/api/v1/analyze/task/{quote(task_id, safe='')}", headers=_engine_headers(s, tenant))
    except httpx.TimeoutException:
        _breaker.record_failure()
        return None, "timeout"
    except httpx.HTTPError as exc:
        _breaker.record_failure()
        logger.warning("deliberation_task_get_failed", err=str(exc)[:200])
        return None, "engine_unreachable"
    if r.status_code >= 500:
        _breaker.record_failure()
        return None, "engine_unreachable"
    _breaker.record_success()
    if r.status_code == 404:
        return None, "not_found"
    if r.status_code != 200:
        return None, "engine_rejected"
    try:
        data = r.json()
    except ValueError:
        return None, "invalid_response"
    return (data, "ok") if isinstance(data, dict) else (None, "invalid_response")


def _integrity_ok(result: dict[str, Any] | None, expected_ih: str | None) -> bool:
    """엔진 결과 무결성 — dict + report 필수(엔진 AnalysisResult 필수=snapshot_id·input_hash·report) +
    expected_ih 있으면 input_hash parity 일치(엔진 run_id 혼선/덮어쓰기·부분응답 탐지). 위반=공시 금지."""
    if not isinstance(result, dict):
        return False
    if result.get("report") is None:  # 필수 report 결손 → 부분응답(공시 금지)
        return False
    return not (expected_ih and result.get("input_hash") != expected_ih)


@router.post("/analyze")
async def deliberation_analyze(payload: dict = Body(...), user=Depends(get_current_user)) -> dict[str, Any]:
    """심의분석 — 인증·미러 정규화·완전 선검증·(결정론)멱등·엔진 프록시·무결성/테넌트 가드·감사. 엔진 무수정(HTTP)."""
    tenant = _tenant(user)
    try:
        dump = build_input_dump(payload)
    except ValidationError as exc:  # 클라이언트 입력오류만 422 — 미러/덤프 내부 버그는 500으로 전파(위장 금지)
        raise HTTPException(status_code=422, detail="invalid_input") from exc
    err = prevalidate(dump)
    if err:
        raise HTTPException(status_code=422, detail=err)

    cih = content_input_hash(dump)
    ih = analysis_input_hash(dump)
    snapshot = dump.get("snapshot_id")
    deterministic = is_deterministic_path(dump)  # 비결정(VLLM/라이브)은 멱등 캐싱 금지(§3·§9 R7)

    # 멱등 — 결정론 경로만. 기존 결속 시 엔진 재호출 없이 재사용(라이브 조회분은 parity 재검증).
    if deterministic:
        existing = await binding_service.lookup(tenant_id=tenant, content_input_hash=cih, snapshot_id=snapshot)
        if existing is not None:
            run_id = existing["run_id"]
            result = existing.get("result")
            if result is None:
                result, greason = await _engine_get_analysis(run_id, tenant=tenant)
                if result is None:
                    ad, sk = await _record_audit(user, tenant, action="analyze_reuse", run_id=run_id,
                                                 input_hash=ih, decision="degraded", http_status=200)
                    return _degrade(_get_degrade_reason(greason),
                                    audit_degraded=ad, audit_skipped=sk, reused=True, run_id=run_id)
            # 저장 영속본(async writer)·라이브 조회분 모두 parity 재검증 — corrupt/drift blob 무음 disclose 금지.
            if not _integrity_ok(result, existing.get("input_hash")):
                ad, sk = await _record_audit(user, tenant, action="analyze_reuse", run_id=run_id,
                                             input_hash=ih, decision="degraded", http_status=200)
                return _degrade("invalid_response", audit_degraded=ad, audit_skipped=sk,
                                reused=True, run_id=run_id)
            ad, sk = await _record_audit(user, tenant, action="analyze_reuse", run_id=run_id,
                                         input_hash=ih, decision="reuse", http_status=200)
            logger.info("deliberation_analyze", path="reuse", reused=True, deterministic=True,
                        run_id=run_id, cache_hit=True)  # 멱등 적중률 관측
            return {"degraded": False, "reused": True, "deterministic": True, "run_id": run_id,
                    "result": result, "audit_degraded": ad, "audit_skipped": sk}

    res, reason = await _engine_post_analyze(dump, deterministic=deterministic, tenant=tenant)
    if res is None:
        ad, sk = await _record_audit(user, tenant, action="analyze", run_id=None,
                                     input_hash=ih, decision="degraded", http_status=200)
        return _degrade(reason, audit_degraded=ad, audit_skipped=sk, deterministic=deterministic)

    # 무결성 — input_hash parity + run_id 유효(엔진 run_id Optional이라 None 통과 가능). 위반=무음 통과 금지.
    if not _integrity_ok(res, ih) or not _is_uuid(res.get("run_id")):
        # 200이지만 parity/run_id 위반 = 엔진 계약 장애(필드 drift 등). 반복 시 circuit 개방해 무음 지속 차단.
        _breaker.record_failure()
        logger.error("deliberation_integrity_violation", expected_ih=ih,
                     got_ih=str(res.get("input_hash")), run_id=str(res.get("run_id")))
        ad, sk = await _record_audit(user, tenant, action="analyze", run_id=None,
                                     input_hash=ih, decision="degraded", http_status=200)
        return _degrade("invalid_response", audit_degraded=ad, audit_skipped=sk, deterministic=deterministic)

    run_id = str(res["run_id"])
    result = res
    inserted = await binding_service.insert(
        run_id=run_id, tenant_id=tenant, content_input_hash=cih, snapshot_id=snapshot,
        input_hash=ih, source="sync", created_by=str(getattr(user, "id", "")), deterministic=deterministic)
    if deterministic and not inserted:  # 동시성 경합 — 승자 결속을 권위본으로(run_id·result 일관)
        again = await binding_service.lookup(tenant_id=tenant, content_input_hash=cih, snapshot_id=snapshot)
        if again is not None:
            run_id = again["run_id"]
            won = again.get("result")
            wreason = "ok"
            if won is None:
                won, wreason = await _engine_get_analysis(run_id, tenant=tenant)  # 라이브 조회분
            # 승자 result는 patron(loser res)으로 덮지 않는다: parity 재검증(재사용 경로와 대칭), 미해소면 정직 degrade.
            if won is None or not _integrity_ok(won, again.get("input_hash")):
                ad, sk = await _record_audit(user, tenant, action="analyze", run_id=run_id,
                                             input_hash=ih, decision="degraded", http_status=200)
                reason = "invalid_response" if won is not None else _get_degrade_reason(wreason)
                return _degrade(reason, audit_degraded=ad, audit_skipped=sk,
                                reused=True, run_id=run_id, deterministic=deterministic)
            result = won
        else:
            # insert=False인데 멱등키 행이 안 보임(승자 행 삭제 등 비정상) — 미결속 패자 run_id를 권위 공시 금지.
            ad, sk = await _record_audit(user, tenant, action="analyze", run_id=None,
                                         input_hash=ih, decision="degraded", http_status=200)
            return _degrade("invalid_response", audit_degraded=ad, audit_skipped=sk,
                            reused=True, deterministic=deterministic)

    ad, sk = await _record_audit(user, tenant, action="analyze", run_id=run_id,
                                 input_hash=ih, decision="authoritative", http_status=200)
    logger.info("deliberation_analyze", path="authoritative", reused=False,
                deterministic=deterministic, run_id=run_id, cache_hit=False)  # 신규 산출 관측
    return {"degraded": False, "reused": False, "deterministic": deterministic, "run_id": run_id,
            "result": result, "audit_degraded": ad, "audit_skipped": sk}


@router.get("/analyze/{run_id}")
async def deliberation_get_analysis(run_id: str, user=Depends(get_current_user)) -> dict[str, Any]:
    """저장 분석 조회 — **테넌트 소유 검증 후에만** 엔진 결과 반환(교차테넌트 read 차단).

    엔진 get_analysis는 테넌트 무필터이므로 BFF가 engine_run_binding(tenant,run_id) 소유를 게이트한다.
    미존재/타테넌트는 동일 404(존재은닉). read 감사는 표면화(fail_closed=False). 엔진 GET은 외부 비노출 전제.
    """
    tenant = _tenant(user)
    binding = await binding_service.lookup_by_run(tenant_id=tenant, run_id=run_id)
    if binding is None:
        ad, sk = await _record_audit(user, tenant, action="analyze_read", run_id=run_id,
                                     input_hash="", decision="not_found", http_status=404, fail_closed=False)
        # 미존재/타테넌트 동일 404(존재은닉)이되 read-감사 degrade는 폐기하지 않고 표면화(무음0 일관).
        detail: Any = {"error": "not_found", "audit_degraded": ad, "audit_skipped": sk} if ad else "not_found"
        raise HTTPException(status_code=404, detail=detail)
    bih = str(binding.get("input_hash") or "")
    result = binding.get("result")
    if result is None:
        result, greason = await _engine_get_analysis(run_id, tenant=tenant)
        if result is None:
            ad, sk = await _record_audit(user, tenant, action="analyze_read", run_id=run_id,
                                         input_hash=bih, decision="degraded", http_status=200, fail_closed=False)
            return _degrade(_get_degrade_reason(greason),
                            audit_degraded=ad, audit_skipped=sk, run_id=run_id)
    # ★저장 영속본(async writer)·라이브 조회분 모두 parity 재검증(reuse 경로 deliberation.py와 대칭) —
    # corrupt/drift/부분(report 결손) blob을 authoritative로 무음 disclose 금지.
    if not _integrity_ok(result, binding.get("input_hash")):
        ad, sk = await _record_audit(user, tenant, action="analyze_read", run_id=run_id,
                                     input_hash=bih, decision="degraded", http_status=200, fail_closed=False)
        return _degrade("invalid_response", audit_degraded=ad, audit_skipped=sk, run_id=run_id)
    ad, sk = await _record_audit(user, tenant, action="analyze_read", run_id=run_id,
                                 input_hash=bih, decision="disclosed",
                                 http_status=200, fail_closed=False)
    return {"degraded": False, "run_id": run_id, "result": result,
            "audit_degraded": ad, "audit_skipped": sk}


# ── 비동기 경로(§9 R-async) — 대용량 도면/라이브 LLM: 동기 타임아웃 병목 해소 ───────────────────


@router.post("/analyze/async")
async def deliberation_analyze_async(payload: dict = Body(...), user=Depends(get_current_user)) -> dict[str, Any]:
    """비동기 심의분석 — 인증·선검증·엔진 task 큐잉·platform run_id 결속(source=async)·감사. 폴링은
    GET /analyze/task/{run_id}. eager(broker 미가동)면 결과 즉시 영속·반환. 엔진은 async 결과 미영속→BFF가 보관."""
    tenant = _tenant(user)
    try:
        dump = build_input_dump(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="invalid_input") from exc
    err = prevalidate(dump)
    if err:
        raise HTTPException(status_code=422, detail=err)
    ih = analysis_input_hash(dump)
    cih = content_input_hash(dump)
    snapshot = dump.get("snapshot_id")

    data, reason = await _engine_post_async(dump, tenant=tenant)
    if data is None:
        ad, sk = await _record_audit(user, tenant, action="analyze_async", run_id=None,
                                     input_hash=ih, decision="degraded", http_status=200)
        return _degrade(reason, audit_degraded=ad, audit_skipped=sk)

    run_id = str(uuid.uuid4())  # 플랫폼 발급(엔진 async는 run_id 미부여) — 결속·폴링 키
    task_id = str(data.get("task_id"))
    eager_result = data.get("result")  # eager면 AnalysisResult dict 즉시 포함
    if eager_result is not None:
        if not _integrity_ok(eager_result, ih):
            _breaker.record_failure()
            logger.error("deliberation_async_integrity_violation", expected_ih=ih)
            ad, sk = await _record_audit(user, tenant, action="analyze_async", run_id=None,
                                         input_hash=ih, decision="degraded", http_status=200)
            return _degrade("invalid_response", audit_degraded=ad, audit_skipped=sk)
        await binding_service.insert(
            run_id=run_id, tenant_id=tenant, content_input_hash=cih, snapshot_id=snapshot,
            input_hash=ih, source="async", engine_task_id=task_id, status="DONE", result=eager_result,
            created_by=str(getattr(user, "id", "")), deterministic=False)
        ad, sk = await _record_audit(user, tenant, action="analyze_async", run_id=run_id,
                                     input_hash=ih, decision="authoritative", http_status=200)
        logger.info("deliberation_analyze_async", path="eager", run_id=run_id)
        return {"degraded": False, "async": True, "status": "DONE", "run_id": run_id,
                "result": eager_result, "audit_degraded": ad, "audit_skipped": sk}

    # 진정 비동기(broker+worker) — 접수만 결속. 폴링으로 결과 수령.
    await binding_service.insert(
        run_id=run_id, tenant_id=tenant, content_input_hash=cih, snapshot_id=snapshot,
        input_hash=ih, source="async", engine_task_id=task_id, status=str(data.get("status") or "PENDING"),
        result=None, created_by=str(getattr(user, "id", "")), deterministic=False)
    ad, sk = await _record_audit(user, tenant, action="analyze_async", run_id=run_id,
                                 input_hash=ih, decision="accepted", http_status=200)
    logger.info("deliberation_analyze_async", path="queued", run_id=run_id)
    return {"degraded": False, "async": True, "status": "PENDING", "run_id": run_id,
            "result": None, "audit_degraded": ad, "audit_skipped": sk}


@router.get("/analyze/task/{run_id}")
async def deliberation_analyze_task(run_id: str, user=Depends(get_current_user)) -> dict[str, Any]:
    """비동기 폴링 — 테넌트 소유검증(source=async) 후 영속본 또는 엔진 task 프록시. SUCCESS 시 BFF 영속·반환.
    정직 degrade: engine_task_failed/async_result_lost/async_timeout/invalid_response."""
    tenant = _tenant(user)
    binding = await binding_service.lookup_by_run(tenant_id=tenant, run_id=run_id)
    if binding is None or binding.get("source") != "async":
        ad, sk = await _record_audit(user, tenant, action="analyze_async_poll", run_id=run_id,
                                     input_hash="", decision="not_found", http_status=404, fail_closed=False)
        detail: Any = {"error": "not_found", "audit_degraded": ad, "audit_skipped": sk} if ad else "not_found"
        raise HTTPException(status_code=404, detail=detail)
    bih = str(binding.get("input_hash") or "")

    stored = binding.get("result")  # eager 또는 이전 폴링 SUCCESS로 영속됨
    if stored is not None:
        if not _integrity_ok(stored, binding.get("input_hash")):
            ad, sk = await _record_audit(user, tenant, action="analyze_async_poll", run_id=run_id,
                                         input_hash=bih, decision="degraded", http_status=200, fail_closed=False)
            return _degrade("invalid_response", audit_degraded=ad, audit_skipped=sk, run_id=run_id)
        ad, sk = await _record_audit(user, tenant, action="analyze_async_poll", run_id=run_id,
                                     input_hash=bih, decision="disclosed", http_status=200, fail_closed=False)
        return {"degraded": False, "async": True, "status": "DONE", "run_id": run_id,
                "result": stored, "audit_degraded": ad, "audit_skipped": sk}

    data, reason = await _engine_get_task(str(binding.get("engine_task_id") or ""), tenant=tenant)
    if data is None:
        ad, sk = await _record_audit(user, tenant, action="analyze_async_poll", run_id=run_id,
                                     input_hash=bih, decision="degraded", http_status=200, fail_closed=False)
        return _degrade(_get_degrade_reason(reason), audit_degraded=ad, audit_skipped=sk, run_id=run_id)

    status = str(data.get("status") or "").upper()
    if status in ("FAILURE", "REVOKED"):
        ad, sk = await _record_audit(user, tenant, action="analyze_async_poll", run_id=run_id,
                                     input_hash=bih, decision="degraded", http_status=200, fail_closed=False)
        return _degrade("engine_task_failed", audit_degraded=ad, audit_skipped=sk, run_id=run_id)
    if data.get("ready"):
        result = data.get("result")
        if result is None:  # SUCCESS인데 결과 유실(backend TTL 등)
            ad, sk = await _record_audit(user, tenant, action="analyze_async_poll", run_id=run_id,
                                         input_hash=bih, decision="degraded", http_status=200, fail_closed=False)
            return _degrade("async_result_lost", audit_degraded=ad, audit_skipped=sk, run_id=run_id)
        if not _integrity_ok(result, binding.get("input_hash")):
            _breaker.record_failure()
            ad, sk = await _record_audit(user, tenant, action="analyze_async_poll", run_id=run_id,
                                         input_hash=bih, decision="degraded", http_status=200, fail_closed=False)
            return _degrade("invalid_response", audit_degraded=ad, audit_skipped=sk, run_id=run_id)
        await binding_service.update_result(tenant_id=tenant, run_id=run_id, result=result, status="DONE")
        ad, sk = await _record_audit(user, tenant, action="analyze_async_poll", run_id=run_id,
                                     input_hash=bih, decision="authoritative", http_status=200)
        logger.info("deliberation_analyze_async", path="resolved", run_id=run_id)
        return {"degraded": False, "async": True, "status": "DONE", "run_id": run_id,
                "result": result, "audit_degraded": ad, "audit_skipped": sk}

    # 미완 — 경과시간 상한 초과면 async_timeout(정직), 아니면 PENDING(재폴링 유도).
    created = binding.get("created_at")
    if isinstance(created, datetime):
        ref = created if created.tzinfo else created.replace(tzinfo=UTC)
        if (datetime.now(UTC) - ref).total_seconds() > get_settings().deliberation_async_result_timeout_s:
            ad, sk = await _record_audit(user, tenant, action="analyze_async_poll", run_id=run_id,
                                         input_hash=bih, decision="degraded", http_status=200, fail_closed=False)
            return _degrade("async_timeout", audit_degraded=ad, audit_skipped=sk, run_id=run_id)
    ad, sk = await _record_audit(user, tenant, action="analyze_async_poll", run_id=run_id,
                                 input_hash=bih, decision="pending", http_status=200, fail_closed=False)
    return {"degraded": False, "async": True, "status": status or "PENDING", "run_id": run_id,
            "result": None, "audit_degraded": ad, "audit_skipped": sk}
