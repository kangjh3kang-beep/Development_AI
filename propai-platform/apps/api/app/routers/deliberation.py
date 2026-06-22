"""심의/설계도면 자동분석 엔진 BFF — 별도 엔진 서비스(services/deliberation-review) 게이트웨이.

플랫폼은 엔진을 직접 import하지 않고(패키지명 `app` 충돌) 서버사이드 HTTP로 호출한다.

★최우선 원칙 — graceful degradation 절대 보장:
  DELIBERATION_ENGINE_URL 미설정 / 엔진 미도달 / 타임아웃 / 4xx·5xx 는 전부
  {status:"degraded", reason:...} 응답으로 변환한다. 절대 500/크래시 금지.
  엔진 미배포 상태의 main을 무파괴로 지키는 핵심 계약.

엔드포인트(prefix /api/v1/deliberation, 인증 필수):
  GET  /health   — 엔진 GET /health 프록시(미도달 시 degraded).
  POST /analyze  — 플랫폼 입력 → 엔진 POST /api/v1/analyze → audit 노드 계약으로 래핑.
                   결과는 (tenant, content_input_hash)로 멱등 재사용·테넌트 결속.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.config import get_settings
from apps.api.integrations.base_client import CircuitBreaker
from apps.api.logging_config import get_logger
from app.services.deliberation import binding_service
from app.services.deliberation._engine_contract import (
    build_input_dump,
    content_input_hash,
    is_deterministic_path,
    prevalidate,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/deliberation", tags=["심의분석 엔진"])

# 엔진 호출 회로차단기(프로세스 로컬). 서버측 장애(연결·5xx·타임아웃)만 카운트해 폭주를 막는다.
_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=75.0, half_open_max=3)


# ── 공통 헬퍼 ──────────────────────────────────────────────────────────


def _tenant(user: CurrentUser) -> str:
    """현재 사용자의 테넌트 id(문자열). 계정격리·멱등의 스코프 키."""
    return str(getattr(user, "tenant_id", "") or "")


def _engine_base() -> str:
    """엔진 base URL(끝 슬래시 제거). 빈 문자열이면 비활성(degraded)."""
    return (get_settings().deliberation_engine_url or "").rstrip("/")


def _engine_headers() -> dict[str, str]:
    """엔진 호출 헤더 — 토큰 설정 시 Bearer 부착."""
    token = get_settings().deliberation_engine_api_token
    return {"Authorization": f"Bearer {token}"} if token else {}


def _timeout():
    """엔진 호출 타임아웃(connect/read 분리)."""
    import httpx

    s = get_settings()
    read = s.deliberation_engine_read_timeout_s
    return httpx.Timeout(
        connect=s.deliberation_engine_connect_timeout_s,
        read=read,
        write=read,
        pool=s.deliberation_engine_connect_timeout_s,
    )


def _degrade(reason: str) -> dict[str, Any]:
    """표준 degraded 응답 — 엔진을 못 쓸 때 모든 경로가 이 모양으로 정직하게 응답한다."""
    return {
        "status": "degraded",
        "reason": reason,
        "findings": [],
        "complianceScore": None,
        "sections": {},
        "run_id": None,
    }


# ── 엔진 호출(단일 choke point) ──────────────────────────────────────────


async def _post_analyze(dump: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """엔진 POST /api/v1/analyze → (data, reason).

    reason 값: ok · engine_unreachable(미설정/연결/5xx) · timeout · engine_rejected(4xx)
    · circuit_open · invalid_response(malformed-200).
    ★예외는 httpx 오류로만 한정 — 내부 버그는 그대로 500 전파(degrade 위장 금지).
    """
    import httpx

    base = _engine_base()
    if not base:
        return None, "engine_unreachable"  # URL 미설정 = 비활성
    if not _breaker.can_execute():
        return None, "circuit_open"  # 연속 장애 → 잠시 호출 차단
    try:
        async with httpx.AsyncClient(timeout=_timeout(), follow_redirects=False) as c:
            r = await c.post(f"{base}/api/v1/analyze", json=dump, headers=_engine_headers())
    except httpx.TimeoutException:
        _breaker.record_failure()
        logger.warning("deliberation_engine_post_timeout")
        return None, "timeout"
    except httpx.HTTPError as exc:  # 연결/전송 오류만 회로 실패 카운트
        _breaker.record_failure()
        logger.warning("deliberation_engine_post_failed", err=str(exc)[:200])
        return None, "engine_unreachable"
    if r.status_code >= 500:
        _breaker.record_failure()
        logger.warning("deliberation_engine_5xx", status=r.status_code)
        return None, "engine_unreachable"
    _breaker.record_success()  # 엔진 도달(<500) → 회복
    if r.status_code != 200:
        logger.warning("deliberation_engine_4xx", status=r.status_code)  # 본문 미기록(PII 보호)
        return None, "engine_rejected"
    try:
        data = r.json()
    except ValueError:
        logger.warning("deliberation_engine_malformed_200")
        return None, "invalid_response"
    return (data, "ok") if isinstance(data, dict) else (None, "invalid_response")


# ── 결과 래핑(엔진 AnalysisResult → audit 노드 계약) ──────────────────────


def _wrap_result(result: dict[str, Any], run_id: str | None) -> dict[str, Any]:
    """엔진 AnalysisResult → 플랫폼 audit 노드 계약(findings·complianceScore·sections).

    엔진 report.sections는 상태별 ReportItem 묶음(CONFIRMED/NEEDS_REVIEW/BLOCKED/DISCRETION_HELD).
    complianceScore = CONFIRMED 비율(0~100). 결과 형태가 예상과 다르면 그대로 통과(가공 실패가
    전체를 깨지 않게 best-effort). 결정론 산출 수치는 변형하지 않는다(표면화 전용).
    """
    report = result.get("report") if isinstance(result, dict) else None
    sections = report.get("sections") if isinstance(report, dict) else None
    sections = sections if isinstance(sections, dict) else {}

    confirmed = len(sections.get("CONFIRMED") or [])
    total = sum(len(v or []) for v in sections.values()) or 0
    compliance_score = round(100.0 * confirmed / total, 1) if total else None

    findings = result.get("findings") if isinstance(result, dict) else None
    findings = findings if isinstance(findings, list) else []

    blocked = len(sections.get("BLOCKED") or [])
    needs_review = len(sections.get("NEEDS_REVIEW") or [])
    final_status = "BLOCKED" if blocked else ("NEEDS_REVIEW" if needs_review else "CONFIRMED")

    return {
        "status": "ok",
        "run_id": run_id or result.get("run_id"),
        "complianceScore": compliance_score,
        "finalStatus": final_status,
        "findings": findings,
        "sections": sections,
        "skipped": result.get("skipped") or [],
        "snapshot_id": result.get("snapshot_id"),
        "input_hash": result.get("input_hash"),
    }


# ── 엔드포인트 ────────────────────────────────────────────────────────────


@router.get("/health")
async def deliberation_health(_user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    """엔진 헬스 프록시. 인증 필수. 미연결/거부 시 degraded(reason 구분, 무음 0)."""
    import httpx

    base = _engine_base()
    if not base:
        return {"status": "degraded", "reason": "engine_unreachable", "engine": None}
    try:
        async with httpx.AsyncClient(timeout=_timeout(), follow_redirects=False) as c:
            r = await c.get(f"{base}/health", headers=_engine_headers())
    except httpx.TimeoutException:
        return {"status": "degraded", "reason": "timeout", "engine": None}
    except httpx.HTTPError as exc:
        logger.warning("deliberation_health_failed", err=str(exc)[:200])
        return {"status": "degraded", "reason": "engine_unreachable", "engine": None}
    if r.status_code >= 500:
        return {"status": "degraded", "reason": "engine_unreachable", "engine": None}
    if r.status_code != 200:
        return {"status": "degraded", "reason": "engine_rejected", "engine": None}
    try:
        body = r.json()
    except ValueError:
        return {"status": "degraded", "reason": "invalid_response", "engine": None}
    return {"status": "ok", "reason": "ok", "engine": body if isinstance(body, dict) else None}


class AnalyzeRequest(BaseModel):
    """플랫폼 → BFF 심의분석 요청. 엔진 AnalysisInput으로 정규화된다(잉여 키 무시·기본값 채움)."""

    payload: dict[str, Any] = Field(default_factory=dict, description="엔진 AnalysisInput 입력")
    project_id: str | None = None


@router.post("/analyze")
async def deliberation_analyze(
    req: AnalyzeRequest = Body(...),
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """심의분석 — 입력 정규화 → 멱등 재사용 확인 → 엔진 호출 → audit 계약 래핑.

    ★엔진 미연결/타임아웃/4xx/5xx는 전부 degraded 응답(크래시 금지).
    멱등: 동일 (tenant, content_input_hash) 결정론 입력은 기존 run을 재사용한다.
    테넌트 결속: 결과를 engine_run_binding에 tenant 스코프로 영속(교차테넌트 read 차단).
    """
    tenant = _tenant(user)

    # 1) 입력 정규화(엔진 기본값 채움) + 최소 선검증(엔진 500 사전 차단).
    dump = build_input_dump(req.payload)
    err = prevalidate(dump)
    if err:
        return {"status": "degraded", "reason": err, "findings": [],
                "complianceScore": None, "sections": {}, "run_id": None}

    cih = content_input_hash(dump)
    snapshot_id = dump.get("snapshot_id")
    deterministic = is_deterministic_path(dump)

    # 2) 멱등 재사용 — 결정론 입력이고 같은 (tenant, content_input_hash)면 기존 결과 반환.
    if deterministic:
        try:
            existing = await binding_service.lookup(
                tenant_id=tenant, content_input_hash=cih, snapshot_id=snapshot_id
            )
        except Exception as exc:  # noqa: BLE001 — DB 장애도 degrade로 흡수(크래시 금지)
            logger.warning("deliberation_lookup_failed", err=str(exc)[:200])
            existing = None
        if existing and isinstance(existing.get("result"), dict):
            return _wrap_result(existing["result"], existing.get("run_id"))

    # 3) 엔진 호출 — 실패는 모두 degraded.
    data, reason = await _post_analyze(dump)
    if reason != "ok" or data is None:
        return _degrade(reason)

    # 4) 결과 영속(테넌트 결속·멱등). 영속 실패는 응답을 막지 않는다(best-effort).
    run_id = str(data.get("run_id") or uuid.uuid4())
    try:
        await binding_service.insert(
            run_id=run_id,
            tenant_id=tenant,
            content_input_hash=cih,
            snapshot_id=snapshot_id,
            input_hash=str(data.get("input_hash") or ""),
            project_id=req.project_id,
            created_by=str(getattr(user, "user_id", "") or "") or None,
            status="completed",
            result=data,
            deterministic=deterministic,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("deliberation_binding_insert_failed", err=str(exc)[:200])

    return _wrap_result(data, run_id)
