"""도면 자동 생성 라우터.

프론트엔드 CAD 컴포넌트가 호출하는 /api/v1/drawing/* 엔드포인트를 제공한다.
app/services/drawing, app/services/cad 서비스를 활용한다.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# ── 서비스 초기화 (lazy import로 의존성 누락 시 graceful 처리) ──

try:
    from app.services.drawing.svg_drawing_service import SVGDrawingService
    from app.services.cad.auto_design_engine import AutoDesignEngineService, SiteInput
    from app.services.cad.parametric_cad_service import ParametricCADService

    svg_service = SVGDrawingService()
    auto_design_engine = AutoDesignEngineService()
    cad_service = ParametricCADService()
    _SERVICES_AVAILABLE = True
except ImportError as _exc:
    logger.warning("도면 서비스 의존성 로드 실패: %s", _exc)
    _SERVICES_AVAILABLE = False


# ── 요청 스키마 ──

class SitePlanRequest(BaseModel):
    site_width_m: float
    site_depth_m: float
    building_width_m: float
    building_depth_m: float
    setback_m: float = 3.0


class FloorPlanRequest(BaseModel):
    total_floor_area_sqm: float
    unit_type: str = "84A"
    core_count: int = 2
    parking_count: int = 50


class ExportDxfRequest(BaseModel):
    building_width_m: float
    building_depth_m: float
    floor_count: int = 1
    floor_height_m: float = 3.0
    unit_width_m: float = 8.0
    corridor_width_m: float = 1.8
    basement_floors: int = 1
    site_width_m: float = 60.0
    site_depth_m: float = 40.0
    setback_m: float = 3.0
    parking_count: int = 50
    drawing_type: str = "floor_plan"


class DesignAlternativesRequest(BaseModel):
    site_area_sqm: float = Field(..., gt=0)
    zone_code: str = "2R"
    building_use: str = "공동주택"
    target_unit_types: list[str] = Field(default=["84A"])
    floor_height_m: float = 3.0
    setback_m: dict[str, float] = Field(
        default={"north": 3.0, "south": 2.0, "east": 1.5, "west": 1.5},
    )
    count: int = Field(3, ge=1, le=5, description="대안 수")


def _check_services() -> None:
    if not _SERVICES_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="도면 서비스를 사용할 수 없습니다 (의존성 누락)",
        )


# ── 엔드포인트 ──

@router.post("/site-plan", response_class=Response)
async def generate_site_plan(req: SitePlanRequest):
    """배치도 SVG를 생성한다."""
    _check_services()
    svg = svg_service.generate_site_plan(
        req.site_width_m, req.site_depth_m,
        req.building_width_m, req.building_depth_m, req.setback_m,
    )
    return Response(content=svg, media_type="image/svg+xml")


@router.post("/floor-plan", response_class=Response)
async def generate_floor_plan(req: FloorPlanRequest):
    """평면도 SVG를 생성한다."""
    _check_services()
    svg = svg_service.generate_floor_plan(
        req.total_floor_area_sqm, req.unit_type,
        req.core_count, req.parking_count,
    )
    return Response(content=svg, media_type="image/svg+xml")


@router.post("/export-dxf", response_class=Response)
async def export_dxf(req: ExportDxfRequest):
    """설계 데이터를 DXF 파일로 내보낸다."""
    _check_services()
    dt = req.drawing_type
    filename = f"{dt}.dxf"

    try:
        if dt == "detailed":
            dxf_bytes = cad_service.create_detailed_floor_plan_dxf(
                building_width_m=req.building_width_m,
                building_depth_m=req.building_depth_m,
                floor_count=req.floor_count,
                unit_width_m=req.unit_width_m,
                corridor_width_m=req.corridor_width_m,
            )
        elif dt == "section":
            dxf_bytes = cad_service.create_section_drawing_dxf(
                building_width_m=req.building_width_m,
                building_depth_m=req.building_depth_m,
                floor_count=req.floor_count,
                floor_height_m=req.floor_height_m,
                basement_floors=req.basement_floors,
            )
        elif dt in ("elevation_front", "elevation_side"):
            view = "front" if dt == "elevation_front" else "side"
            dxf_bytes = cad_service.create_elevation_drawing_dxf(
                building_width_m=req.building_width_m,
                building_depth_m=req.building_depth_m,
                floor_count=req.floor_count,
                floor_height_m=req.floor_height_m,
                view=view,
            )
        elif dt == "site_plan":
            dxf_bytes = cad_service.create_site_plan_dxf(
                site_width_m=req.site_width_m,
                site_depth_m=req.site_depth_m,
                building_width_m=req.building_width_m,
                building_depth_m=req.building_depth_m,
                setback_m=req.setback_m,
                parking_count=req.parking_count,
            )
        else:
            dxf_bytes = cad_service.create_floor_plan_dxf(
                building_width_m=req.building_width_m,
                building_depth_m=req.building_depth_m,
                floor_count=req.floor_count,
                unit_width_m=req.unit_width_m,
                corridor_width_m=req.corridor_width_m,
            )
    except ImportError as e:
        raise HTTPException(status_code=501, detail="DXF 내보내기 기능을 사용할 수 없습니다 (ezdxf 미설치)")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"설계 데이터 오류: {e}")
    except Exception as e:
        logger.error("DXF 생성 중 오류: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="도면 생성 중 오류가 발생했습니다")

    return Response(
        content=dxf_bytes,
        media_type="application/dxf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/design-alternatives")
async def design_alternatives(req: DesignAlternativesRequest):
    """A/B/C 대안을 생성하여 비교한다."""
    _check_services()
    site_input = SiteInput(
        site_area_sqm=req.site_area_sqm,
        zone_code=req.zone_code,
        building_use=req.building_use,
        target_unit_types=req.target_unit_types,
        floor_height_m=req.floor_height_m,
        setback_m=req.setback_m,
    )
    results = auto_design_engine.generate_alternatives(site_input, count=req.count)
    return {
        "alternatives": [
            {
                "design_payload": r.design_payload,
                "summary": r.summary,
                "compliance": r.compliance,
            }
            for r in results
        ],
    }
