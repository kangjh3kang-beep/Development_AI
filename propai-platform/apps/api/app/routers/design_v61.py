"""v61 설계도면 라우터 — 전체 도면 세트 + 대안 선정 + 인허가 도서.

prefix: /api/v1/design
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.drawing.design_alternative_selector import DesignAlternativeSelector
from app.services.drawing.svg_drawing_service import SVGDrawingService
from apps.api.database.session import get_db

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
    """도면 저장 요청. 편집된 CAD 좌표(points/lines/surfaces)를 영속화한다."""
    drawing_code: str = "CAD-EDIT"
    drawing_type: str = "평면도"
    drawing_name: Optional[str] = None
    svg_content: str = ""
    layers: list[dict[str, Any]] = Field(default_factory=list)
    vector_data: dict[str, Any] = Field(default_factory=dict)
    # CADEditor 편집 데이터
    points: list[dict[str, Any]] = Field(default_factory=list)
    lines: list[dict[str, Any]] = Field(default_factory=list)
    surfaces: list[dict[str, Any]] = Field(default_factory=list)
    floor_count: Optional[int] = None
    building_height_m: Optional[float] = None


class AltSelectionRequest(BaseModel):
    """대안 선정 요청."""
    alternatives: list[dict[str, Any]]
    iterations: int = Field(5000, ge=100, le=50000)
    noise_pct: float = Field(0.10, ge=0.01, le=0.50)


class BimGenerateRequest(BaseModel):
    """3D BIM 모델 생성 요청.

    매스(building_width/depth, floor_count)를 직접 주거나, 미입력 시
    대지정보(land_area_sqm + zone_code)로 AutoDesignEngine이 자동 산출한다.
    """
    building_width_m: float | None = Field(None, gt=0)
    building_depth_m: float | None = Field(None, gt=0)
    floor_count: int | None = Field(None, ge=1, le=200)
    floor_height_m: float = Field(3.0, gt=2.0)
    # 자동 매스 산출용(매스 미입력 시)
    land_area_sqm: float | None = Field(None, gt=0)
    zone_code: str = "2R"
    project_name: str = "PropAI"


# ── 응답 스키마 ──


class DrawingInfo(BaseModel):
    """개별 도면 정보."""
    svg_length: int
    has_content: bool


class FullDrawingSetResponse(BaseModel):
    """전체 도면 세트 생성 결과."""
    project_id: str
    drawings: dict[str, DrawingInfo]
    drawing_count: int


class DrawingSaveResponse(BaseModel):
    """도면 저장 결과."""
    project_id: str
    drawing_code: str
    drawing_type: str
    svg_length: int
    layer_count: int
    status: str


class AlternativeSelectionResponse(BaseModel):
    """대안 선정 결과."""
    project_id: str
    ranked: list[dict[str, Any]]
    mc_results: list[dict[str, Any]] = Field(default_factory=list)
    winner: dict[str, Any] = Field(default_factory=dict)


class PermitDocsResponse(BaseModel):
    """인허가 도서 현황."""
    project_id: str
    documents: list[dict[str, Any]]
    total: int
    completed: int
    completion_pct: float


# ── 엔드포인트 ──

@router.post("/{project_id}/generate-full-set", response_model=FullDrawingSetResponse)
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


@router.post("/{project_id}/drawings/save", response_model=DrawingSaveResponse)
async def save_drawing(
    project_id: str,
    req: CADSaveRequest,
    db: AsyncSession = Depends(get_db),
):
    """편집된 CAD 도면을 design_versions 테이블에 영속화한다.

    CADEditor가 드래그 편집한 points/lines/surfaces를 design_data_json에 저장.
    프로젝트별 버전 자동 증가. project_id가 UUID가 아니면(데모) 저장 스킵·echo.
    """
    import uuid as _uuid

    from sqlalchemy import select

    # project_id UUID 검증 — 데모/임시 ID면 저장 없이 echo(graceful)
    try:
        pid = _uuid.UUID(project_id)
    except (ValueError, AttributeError):
        return {
            "project_id": project_id, "drawing_code": req.drawing_code,
            "drawing_type": req.drawing_type, "svg_length": len(req.svg_content),
            "layer_count": len(req.layers), "status": "echo(비영속:UUID아님)",
        }

    try:
        from apps.api.database.models.design_version import DesignVersion
        from apps.api.database.models.project import Project

        # tenant_id 조회(프로젝트 소속)
        proj = (await db.execute(select(Project).where(Project.id == pid))).scalar_one_or_none()
        if proj is None:
            return {
                "project_id": project_id, "drawing_code": req.drawing_code,
                "drawing_type": req.drawing_type, "svg_length": len(req.svg_content),
                "layer_count": len(req.layers), "status": "echo(프로젝트없음)",
            }
        tenant_id = proj.tenant_id

        # 현재 최대 버전 +1
        existing = (await db.execute(
            select(DesignVersion).where(DesignVersion.project_id == pid)
            .order_by(DesignVersion.version_number.desc())
        )).scalars().first()
        next_ver = (existing.version_number + 1) if existing else 1

        dv = DesignVersion(
            tenant_id=tenant_id,
            project_id=pid,
            version_number=next_ver,
            design_type="cad_2d",
            floor_count=req.floor_count,
            max_height_m=req.building_height_m,
            design_data_json={
                "drawing_code": req.drawing_code,
                "drawing_type": req.drawing_type,
                "drawing_name": req.drawing_name,
                "points": req.points,
                "lines": req.lines,
                "surfaces": req.surfaces,
                "svg_content": req.svg_content[:50000],  # 과대 SVG 방어
                "layers": req.layers,
                "vector_data": req.vector_data,
            },
            notes=f"CAD 편집 저장 v{next_ver}",
        )
        db.add(dv)
        await db.commit()
        return {
            "project_id": project_id, "drawing_code": req.drawing_code,
            "drawing_type": req.drawing_type, "svg_length": len(req.svg_content),
            "layer_count": len(req.layers), "status": f"saved(v{next_ver})",
        }
    except Exception as e:  # noqa: BLE001
        await db.rollback()
        import structlog

        structlog.get_logger().warning("CAD 저장 실패", error=str(e)[:150])
        raise HTTPException(status_code=500, detail=f"저장 실패: {str(e)[:120]}") from e


@router.get("/{project_id}/drawings/load")
async def load_drawing(project_id: str, db: AsyncSession = Depends(get_db)):
    """저장된 최신 CAD 편집본을 불러온다. 없으면 saved=false."""
    import uuid as _uuid

    from sqlalchemy import select

    try:
        pid = _uuid.UUID(project_id)
    except (ValueError, AttributeError):
        return {"saved": False, "reason": "UUID 아님"}

    try:
        from apps.api.database.models.design_version import DesignVersion

        dv = (await db.execute(
            select(DesignVersion).where(
                DesignVersion.project_id == pid,
                DesignVersion.design_type == "cad_2d",
            ).order_by(DesignVersion.version_number.desc())
        )).scalars().first()
        if dv is None:
            return {"saved": False}
        return {
            "saved": True,
            "version": dv.version_number,
            "data": dv.design_data_json or {},
            "updated_at": str(dv.updated_at) if dv.updated_at else None,
        }
    except Exception as e:  # noqa: BLE001
        import structlog

        structlog.get_logger().warning("CAD 로드 실패", error=str(e)[:150])
        return {"saved": False, "reason": str(e)[:80]}


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


def _enrich_interior(mass: dict[str, Any], building_use: str = "공동주택") -> dict[str, Any]:
    """매스에 실내 요소(코어 위치·복도폭·창호수)를 추가해 3D 디테일을 높인다.

    AutoDesignEngine.compute_core_layout으로 코어/복도를 산출하고, 건물 폭 기준
    창호 개수를 정한다. 실패 시 매스만 반환(graceful).
    """
    try:
        from app.services.cad.auto_design_engine import AutoDesignEngineService

        # compute_core_layout은 total_floor_area_sqm 필요 — 없으면 추정
        if "total_floor_area_sqm" not in mass:
            mass["total_floor_area_sqm"] = (
                mass["building_width_m"] * mass["building_depth_m"] * mass["num_floors"]
            )
        core = AutoDesignEngineService.compute_core_layout(mass, building_use)
        mass["core_positions"] = core.get("core_positions", [])
        mass["corridor_width_m"] = core.get("corridor_width_m", 1.8)
        mass["core_size_m"] = 5.0  # CORE_AREA_SQM=25 → 5×5m
        # 창호: 건물 폭 5m당 1개(최소2·최대8)
        bw = mass.get("building_width_m", 12.0)
        mass["windows_per_side"] = max(2, min(8, int(bw / 5)))
        # 세대 분할: 공동주택 표준 세대폭 ~8m(폭이 좁으면 폭의 절반으로 최소 2분할)
        mass["unit_width_m"] = 8.0 if bw >= 16.0 else max(4.0, bw / 2)
        # 평형별 가변 세대 배치(compute_unit_layout) + 발코니/현관문
        unit_types = ["59A", "84A"] if building_use == "공동주택" else ["일반"]
        ul = AutoDesignEngineService.compute_unit_layout(mass, core, unit_types, building_use)
        # 한 zone(전면)을 채울 평형 시퀀스: count_per_floor만큼 평형 반복
        seq: list[dict[str, Any]] = []
        for u in ul.get("units", []):
            seq.extend([{"type": u["type"], "area_sqm": u["area_sqm"]}] * max(1, u.get("count_per_floor", 1) // 2))
        if seq:
            mass["unit_sequence"] = seq
        mass["balconies"] = building_use == "공동주택"
        mass["unit_doors"] = True
    except Exception:  # noqa: BLE001
        pass
    return mass


def _resolve_mass(req: "BimGenerateRequest") -> dict[str, Any]:
    """요청에서 건축 매스를 확정한다. 매스 직접입력 우선, 없으면 대지정보로 자동산출.

    확정된 매스에 실내 요소(코어·복도·창호)를 _enrich_interior로 보강한다.
    """
    if req.building_width_m and req.building_depth_m and req.floor_count:
        mass = {
            "building_width_m": req.building_width_m,
            "building_depth_m": req.building_depth_m,
            "num_floors": req.floor_count,
            "floor_height_m": req.floor_height_m,
        }
        return _enrich_interior(mass)
    # 자동 산출: AutoDesignEngine(대지면적+용도지역 → 최적 매스)
    if req.land_area_sqm:
        from app.services.cad.auto_design_engine import AutoDesignEngineService, SiteInput

        svc = AutoDesignEngineService()
        site = SiteInput(
            site_area_sqm=req.land_area_sqm,
            zone_code=req.zone_code,
            floor_height_m=req.floor_height_m,
        )
        legal = svc.get_legal_limits(req.zone_code)
        eff = svc.compute_effective_site(site)
        mass = svc.compute_optimal_mass(site, eff, legal)
        return _enrich_interior(mass)
    # 최종 폴백: 합리적 기본값
    mass = {
        "building_width_m": 12.0, "building_depth_m": 9.0,
        "num_floors": req.floor_count or 5, "floor_height_m": req.floor_height_m,
    }
    return _enrich_interior(mass)


@router.post("/{project_id}/bim/generate")
async def generate_bim_model(project_id: str, req: BimGenerateRequest):
    """3D BIM(IFC) 모델을 생성하고 요약 메타 + AI 설계해석을 반환한다."""
    from app.services.bim.ifc_generator_service import build_ifc_from_mass

    mass = _resolve_mass(req)
    ifc_bytes = build_ifc_from_mass(mass, project_name=req.project_name)

    # ── DesignInterpreter(Claude) 설계 AI 해석 — 실패해도 모델은 정상 반환 ──
    ai_interpretation = None
    try:
        from app.services.ai.design_interpreter import DesignInterpreter

        interp = await DesignInterpreter().generate_interpretation({
            **mass,
            "zone_code": req.zone_code,
            "building_use": "공동주택",
        })
        if isinstance(interp, dict) and interp:
            ai_interpretation = interp
    except Exception as e:  # noqa: BLE001
        import structlog

        structlog.get_logger().warning("설계 AI 해석 스킵", error=str(e)[:120])

    return {
        "project_id": project_id,
        "mass": {
            "building_width_m": round(mass["building_width_m"], 2),
            "building_depth_m": round(mass["building_depth_m"], 2),
            "num_floors": int(mass["num_floors"]),
            "floor_height_m": mass.get("floor_height_m", req.floor_height_m),
            "building_height_m": round(int(mass["num_floors"]) * mass.get("floor_height_m", req.floor_height_m), 2),
            "bcr_pct": mass.get("bcr_pct"),
            "far_pct": mass.get("far_pct"),
            "total_units": mass.get("total_units"),
        },
        "ai_interpretation": ai_interpretation,
        "ifc_bytes": len(ifc_bytes),
        "glb_url": f"/api/v1/design/{project_id}/bim/model.glb",
    }


@router.post("/{project_id}/bim/model.glb", response_class=Response)
async def get_bim_glb(project_id: str, req: BimGenerateRequest):
    """3D BIM 모델을 glTF binary(.glb)로 반환한다 — 프론트 useGLTF가 직접 로드."""
    from app.services.bim.ifc_generator_service import build_ifc_from_mass
    from app.services.bim.ifc_to_gltf_service import IfcToGltfService

    mass = _resolve_mass(req)
    try:
        ifc_bytes = build_ifc_from_mass(mass, project_name=req.project_name)
        glb = IfcToGltfService().convert(ifc_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"BIM 모델 생성 실패: {str(e)[:120]}") from e
    return Response(
        content=glb,
        media_type="model/gltf-binary",
        headers={"Content-Disposition": f"inline; filename={project_id}.glb"},
    )


@router.post("/{project_id}/bim/export-ifc", response_class=Response)
async def export_bim_ifc(project_id: str, req: BimGenerateRequest):
    """3D BIM 모델을 IFC4 파일로 내보낸다(BIM 표준 교환)."""
    from app.services.bim.ifc_generator_service import build_ifc_from_mass

    mass = _resolve_mass(req)
    ifc_bytes = build_ifc_from_mass(mass, project_name=req.project_name)
    return Response(
        content=ifc_bytes,
        media_type="application/x-step",
        headers={"Content-Disposition": f"attachment; filename={project_id}.ifc"},
    )


@router.post("/{project_id}/select-alternative", response_model=AlternativeSelectionResponse)
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


@router.get("/{project_id}/permit-docs", response_model=PermitDocsResponse)
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
