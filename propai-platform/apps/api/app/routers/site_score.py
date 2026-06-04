"""PropAI SiteScore 라우터 — 설명가능 학습형 입지 점수(베팅 C)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.site_score.site_score_service import compute_site_score
from app.services.site_score.solar_envelope_service import compute_buildable_envelope

router = APIRouter(prefix="/api/v1/site-score", tags=["입지점수(SiteScore)"])


class SiteScoreRequest(BaseModel):
    context: dict[str, Any]                       # 부지 분석 결과(infrastructure/zone_type/공시지가 등)
    region_baseline: dict[str, float] | None = None  # 지역 평균(상권·실거래·지가) — 자가보정용(선택)


@router.post("")
async def site_score(req: SiteScoreRequest):
    """부지 컨텍스트에서 0~100 입지 점수 + 피처별 기여도(설명가능)를 산출."""
    return compute_site_score(req.context, req.region_baseline)


class EnvelopeRequest(BaseModel):
    land_area_sqm: float
    zone: str = ""
    land_width_m: float | None = None
    land_depth_m: float | None = None
    floor_height_m: float = 3.0
    bcr_limit_pct: float | None = None
    far_limit_pct: float | None = None


@router.post("/envelope")
async def buildable_envelope(req: EnvelopeRequest):
    """한국 정북일조 빌더블 인벨로프 — 건축가능 최대 연면적·층수·일조 손실률."""
    return compute_buildable_envelope(
        land_area_sqm=req.land_area_sqm, zone=req.zone,
        land_width_m=req.land_width_m, land_depth_m=req.land_depth_m,
        floor_height_m=req.floor_height_m,
        bcr_limit_pct=req.bcr_limit_pct, far_limit_pct=req.far_limit_pct,
    )
