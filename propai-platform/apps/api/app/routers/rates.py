"""v61 법정요율 라우터.

prefix: /api/v1/rates
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from app.services.cost.legal_rate_service import LegalRateService

router = APIRouter(prefix="/api/v1/rates", tags=["v61 법정요율"])
rate_service = LegalRateService()


@router.get("/current")
async def get_current_rates():
    """2026년 법정요율 12개 + 국민연금 단계인상 스케줄."""
    return rate_service.get_current_rates()


@router.get("/history")
async def get_rate_history(rate_code: Optional[str] = None):
    """요율 변경 이력."""
    return rate_service.get_rate_history(rate_code)


@router.post("/refresh")
async def refresh_rates():
    """외부 API 요율 갱신 (스텁)."""
    return rate_service.refresh_rates()
