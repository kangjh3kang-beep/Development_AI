"""규제 SSOT read API — 엔진 1차출처(국가 용도지역 한도) 노출.

GET /api/v1/reg/zone-limits: national_zone_limits.json(시행령 §84/§85) 전 용도지역 한도+provenance.
플랫폼이 자신의 ZONE_LIMITS를 이 1차출처와 대조(reg-source divergence·P5)하는 read-only 소비원.
인증: analyze와 동일(require_token). 결정론(동일 데이터파일 동일 응답·라이브 발화 없음).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_token
from app.services.legal_calc.zone_limit_provider import all_zone_limits

router = APIRouter(prefix="/api/v1/reg", tags=["reg"])


@router.get("/zone-limits", dependencies=[Depends(require_token)])
def zone_limits() -> dict:
    """전 용도지역 국가 규제 상한(건폐율/용적률) + provenance. 엔진 규제 SSOT(read-only)."""
    return all_zone_limits()
