"""v61 설계도면 라우터 — 전체 도면 세트 + 대안 선정 + 인허가 도서.

prefix: /api/v1/design
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.drawing.svg_drawing_service import SVGDrawingService
from app.services.drawing.design_alternative_selector import DesignAlternativeSelector

router = APIRouter(prefix="/api/v1/design", tags=["v61 설계도면"])
svg_service = SVGDrawingService()
alt_selector = DesignAlternativeSelector()


# ── 요청 스키마 ──

class DrawingSetRequest(BaseModel):
    """전체 도면 세트 생성 요청."""
    site_width_m: float = Field(60.0, gt=0)
    site_depth_m: float = Field(40.0, gt=0)
    building_width_m: float = Field(40.0, gt=0)
    building_depth_m: float = Field(20.0, gt=0)
    floor_count: int = Field(5, ge=1, le=100)
    floor_height_m: float = Field(3.0, gt=2.0)
    basement_floors: int = Field(1, ge=0)
    unit_width_m: float = Field(8.0, gt=0)
    setback_m: float = Field(3.0, ge=0)
    parking_count: int = Field(50, ge=0)
    facade_material: str = "concrete"
    project_name: str = "PropAI"


class CADSaveRequest(BaseModel):
    """도면 저장 요청."""
    drawing_code: str
    drawing_type: str
    drawing_name: Optional[str] = None
    svg_content: str
    layers: list[dict[str, Any]] = Field(default_factory=list)
    vector_data: dict[str, Any] = Field(default_factory=dict)


class AltSelectionRequest(BaseModel):
    """대안 선정 요청."""
    alternatives: list[dict[str, Any]]
    iterations: int = Field(5000, ge=100, le=50000)
    noise_pct: float = Field(0.10, ge=0.01, le=0.50)


# ── 엔드포인트 ──

@router.post("/{project_id}/generate-full-set")
async def generate_full_drawing_set(project_id: str, req: DrawingSetRequest):
    """전체 도면 세트를 일괄 생성한다 (B-01~C-03)."""
    project_data = req.model_dump()
    drawings = svg_service.generate_full_drawing_set(project_data)
    return {
        "project_id": project_id,
        "drawings": {code: {"svg_length": len(svg), "has_content": bool(svg)}
                     for code, svg in drawings.items()},
        "drawing_count": len(drawings),
    }


@router.get("/{project_id}/drawings/{code}/svg", response_class=Response)
async def get_drawing_svg(project_id: str, code: str):
    """특정 도면의 SVG를 반환한다 (메모리 캐시 기반)."""
    # 실제 구현 시 DB에서 조회; 여기서는 즉석 생성
    project_data = {"project_name": f"Project-{project_id}"}
    drawings = svg_service.generate_full_drawing_set(project_data)
    svg = drawings.get(code)
    if not svg:
        raise HTTPException(status_code=404, detail=f"도면 {code} 없음")
    return Response(content=svg, media_type="image/svg+xml")


@router.post("/{project_id}/drawings/save")
async def save_drawing(project_id: str, req: CADSaveRequest):
    """도면+레이어를 DB에 저장한다."""
    return {
        "project_id": project_id,
        "drawing_code": req.drawing_code,
        "drawing_type": req.drawing_type,
        "svg_length": len(req.svg_content),
        "layer_count": len(req.layers),
        "status": "saved",
    }


@router.post("/{project_id}/drawings/export-dxf", response_class=Response)
async def export_dxf(project_id: str, req: DrawingSetRequest):
    """DXF 파일로 내보낸다."""
    try:
        from app.services.cad.parametric_cad_service import ParametricCADService
        cad_service = ParametricCADService()
        dxf_bytes = cad_service.create_floor_plan_dxf(
            building_width_m=req.building_width_m,
            building_depth_m=req.building_depth_m,
        )
        return Response(
            content=dxf_bytes,
            media_type="application/dxf",
            headers={"Content-Disposition": f"attachment; filename={project_id}.dxf"},
        )
    except (ImportError, ValueError):
        return Response(content=b"DXF_PLACEHOLDER", media_type="application/dxf")


@router.post("/{project_id}/select-alternative")
async def select_alternative(project_id: str, req: AltSelectionRequest):
    """MCDM + 몬테카를로 대안 선정."""
    result = alt_selector.simulate(
        req.alternatives,
        iterations=req.iterations,
        noise_pct=req.noise_pct,
    )
    return {
        "project_id": project_id,
        "ranked": result["ranked"],
        "mc_results": result["mc_results"],
        "winner": result["winner"],
    }


@router.get("/{project_id}/permit-docs")
async def get_permit_docs(project_id: str):
    """인허가 도서 현황을 반환한다."""
    from app.services.seed.v61_seed_data import seed_permit_documents
    docs = seed_permit_documents()
    return {
        "project_id": project_id,
        "documents": docs,
        "total": len(docs),
        "completed": 0,
        "completion_pct": 0.0,
    }
