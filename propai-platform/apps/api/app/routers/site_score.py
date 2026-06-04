"""PropAI SiteScore 라우터 — 설명가능 학습형 입지 점수(베팅 C)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.site_score.site_score_service import compute_site_score

router = APIRouter(prefix="/api/v1/site-score", tags=["입지점수(SiteScore)"])


class SiteScoreRequest(BaseModel):
    context: dict[str, Any]                       # 부지 분석 결과(infrastructure/zone_type/공시지가 등)
    region_baseline: dict[str, float] | None = None  # 지역 평균(상권·실거래·지가) — 자가보정용(선택)


@router.post("")
async def site_score(req: SiteScoreRequest):
    """부지 컨텍스트에서 0~100 입지 점수 + 피처별 기여도(설명가능)를 산출."""
    return compute_site_score(req.context, req.region_baseline)
