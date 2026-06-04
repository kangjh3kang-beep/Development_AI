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
    land_area_sqm: float = 0
    zone: str = ""
    land_width_m: float | None = None
    land_depth_m: float | None = None
    floor_height_m: float = 3.0
    bcr_limit_pct: float | None = None
    far_limit_pct: float | None = None
    pnu: str | None = None                 # 주면 VWorld 실측 폴리곤으로 치수 정밀화
    geometry: dict | None = None           # 직접 GeoJSON geometry 입력(선택)


@router.post("/envelope")
async def buildable_envelope(req: EnvelopeRequest):
    """한국 정북일조 빌더블 인벨로프 — 건축가능 최대 연면적·층수·일조 손실률.

    PNU(또는 geometry) 제공 시 VWorld 실측 필지 폴리곤으로 남북깊이·동서폭·면적을
    정밀 도출(√면적 정사각 근사 대체). 부정형 필지도 실측 반영.
    """
    from app.services.site_score.solar_envelope_service import dims_from_polygon

    width, depth, area = req.land_width_m, req.land_depth_m, req.land_area_sqm
    geom_source = "입력값/근사"
    geometry = req.geometry

    road_side = None
    if req.pnu and geometry is None:
        try:
            from app.services.external_api.vworld_service import VWorldService
            vw = VWorldService()
            parcel = await vw.get_parcel_by_pnu(req.pnu)
            geometry = (parcel or {}).get("geometry")
            lc = await vw.get_land_characteristics(req.pnu)
            if lc:
                road_side = lc.get("road_side") or None  # 접도 유형(광대로/중로/세로 등)
        except Exception:  # noqa: BLE001
            geometry = None

    if geometry is not None:
        dims = dims_from_polygon(geometry)
        if dims:
            width, depth = dims["width_m"], dims["depth_m"]
            if not area or area <= 0:
                area = dims["area_sqm"]
            geom_source = f"VWorld 실측 폴리곤(부정형도 {round(dims['irregularity']*100,1)}%)"

    if not area or area <= 0:
        return {"error": "대지면적 또는 PNU/geometry가 필요합니다."}

    result = compute_buildable_envelope(
        land_area_sqm=area, zone=req.zone,
        land_width_m=width, land_depth_m=depth,
        floor_height_m=req.floor_height_m,
        bcr_limit_pct=req.bcr_limit_pct, far_limit_pct=req.far_limit_pct,
    )
    result["geometry_source"] = geom_source
    if road_side:
        result["road_side"] = road_side   # 접도 유형(가로구역 최고높이·개발여건 참고)
    return result
