"""자가성장 엔진 — 텔레메트리 수집 라우터(설계서 §3.2).

POST /api/v1/growth/events
- 프론트 event-collector 가 5초/20건 배치로 sendBeacon 전송하는 이벤트 수신.
- 인증 선택적(익명 허용). Authorization: Bearer 가 있으면 user_id/tenant_id 추출
  → user_id 는 서버가 HMAC 익명화(capture_service), 원본 미저장.
- event_id(uuid) 멱등(중복 전송은 적재 시 DO NOTHING).
- 동기 INSERT 없음: record_event() 로 큐 push 만(적재는 Celery/폴백).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/growth", tags=["자가성장 텔레메트리"])

# 프론트가 임의로 큰 배열을 보내지 못하게 1회 배치 상한.
_MAX_BATCH = 100

_ALLOWED_TYPES = {
    "page_view", "click", "funnel_step", "api_call", "api_error", "js_error",
    "promise_rejection", "web_vital", "llm_call", "verify_result", "fallback",
    "heal_action",
}


class GrowthEventIn(BaseModel):
    """프론트 collector 가 보내는 단일 이벤트 스키마(익명화 전)."""

    event_id: str | None = Field(default=None, description="클라이언트 멱등키(uuid)")
    event_type: str
    surface: str | None = Field(default="web")
    route: str | None = None
    status_code: int | None = None
    latency_ms: int | None = None
    severity: str | None = None
    service: str | None = None
    session_id: str | None = None
    app_version: str | None = None
    payload: dict | None = None


class GrowthEventBatch(BaseModel):
    events: list[GrowthEventIn] = Field(default_factory=list)


class GrowthIngestResult(BaseModel):
    accepted: int
    rejected: int


def _extract_identity(request: Request) -> tuple[str | None, str | None]:
    """Authorization 헤더(선택적)에서 (user_id, tenant_id) 추출. 없으면 (None, None)."""
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None, None
    try:
        from apps.api.auth.jwt_handler import decode_token

        payload = decode_token(auth.split(" ", 1)[1].strip())
        uid = str(payload.sub) if getattr(payload, "sub", None) else None
        tid = str(payload.tenant_id) if getattr(payload, "tenant_id", None) else None
        return uid, tid
    except Exception:  # noqa: BLE001 — 무효/만료 토큰은 익명 처리.
        return None, None


@router.post("/events", response_model=GrowthIngestResult)
async def ingest_events(batch: GrowthEventBatch, request: Request) -> GrowthIngestResult:
    """프론트 이벤트 배치를 수신해 큐에 적재(논블로킹). 인증 선택·익명 허용."""
    from app.services.growth import capture_service

    user_id, tenant_id = _extract_identity(request)

    accepted = 0
    rejected = 0
    for ev in batch.events[:_MAX_BATCH]:
        if ev.event_type not in _ALLOWED_TYPES:
            rejected += 1
            continue
        try:
            capture_service.record_event(
                ev.event_type,
                {
                    "event_id": ev.event_id,
                    "surface": ev.surface or "web",
                    "route": ev.route,
                    "status_code": ev.status_code,
                    "latency_ms": ev.latency_ms,
                    "severity": ev.severity,
                    "service": ev.service,
                    "session_id": ev.session_id,
                    "app_version": ev.app_version,
                    "payload": ev.payload,
                    "tenant_id": tenant_id,
                    "user_id": user_id,  # capture_service 가 HMAC 익명화 후 폐기
                },
            )
            accepted += 1
        except Exception:  # noqa: BLE001
            rejected += 1
    # 상한 초과분은 거부 카운트에 반영.
    rejected += max(0, len(batch.events) - _MAX_BATCH)
    return GrowthIngestResult(accepted=accepted, rejected=rejected)
