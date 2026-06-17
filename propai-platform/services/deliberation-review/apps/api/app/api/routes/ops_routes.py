"""운영 라우트 — GET /api/v1/doctor: 통합 상태(어댑터 live/mock, 키 보유 여부). 키 값 비노출."""
from __future__ import annotations

from fastapi import APIRouter

from app.services.ops.integration_status import integration_status

router = APIRouter(prefix="/api/v1", tags=["ops"])


@router.get("/doctor")
def doctor() -> dict:
    return {"status": "ok", "integrations": integration_status()}
