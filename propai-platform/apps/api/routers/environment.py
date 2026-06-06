"""Flagship C-2 — 환경분석(일조·조망·스카이라인) 라우터.

POST /api/v1/environment/analyze: 주소/PNU → 좌표·필지·주변건물 →
  일조(태양궤적·일조시간·정북사선)·조망(개방도)·스카이라인(높이맥락).
산정 로직은 app/services/environment/environment_service.py에 있으며 본 라우터는 얇게 위임한다.
정밀 일조분석/측량이 아닌 약식 계산(참고용) — 정직성 비협상(badges 명시).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class DesignParams(BaseModel):
    """대상 건물 제원 — height_m 우선, 없으면 floors×floor_height_m."""

    floors: int | None = None
    height_m: float | None = None
    floor_height_m: float | None = None


class EnvironmentAnalyzeRequest(BaseModel):
    """환경분석 요청 — address/pnu 중 최소 1개 필수."""

    address: str | None = None
    pnu: str | None = None
    design_params: DesignParams | None = None
    season: str = "winter"  # winter(동지·기본)|summer(하지)|equinox(춘분)


@router.post("/analyze", summary="환경분석 — 일조(일조시간·정북사선)·조망(개방도)·스카이라인")
async def analyze(req: EnvironmentAnalyzeRequest) -> dict:
    """주소/PNU 기준 좌표·필지·주변 건물로 일조·조망·스카이라인을 약식 정량 분석한다.

    - solar: 위도·날짜·시각별 천문식 태양 고도/방위(3D 궤적), 동지 9~15시 약식 일조시간,
      주거지역 정북 일조사선(건축법 제61조) 이격 검토.
    - view: 건물 상부 8방위 개방도 점수(0~100)·가림율·양호 조망 방향.
    - skyline: 대상 높이 vs 주변 평균/최고 → 돌출/조화/매몰.

    정밀 일조분석/측량 아님(참고용) — badges에 약식 근거 명시.
    """
    if not (req.address and req.address.strip()) and not (req.pnu and req.pnu.strip()):
        raise HTTPException(status_code=422, detail="address 또는 pnu 중 하나는 필수입니다.")

    from app.services.environment.environment_service import analyze_environment

    dp = req.design_params.model_dump(exclude_none=True) if req.design_params else None
    return await analyze_environment(
        address=(req.address or "").strip() or None,
        pnu=(req.pnu or "").strip() or None,
        design_params=dp,
        season=req.season or "winter",
    )
