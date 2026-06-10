"""v61 설계도면 라우터 — 전체 도면 세트 + 대안 선정 + 인허가 도서.

prefix: /api/v1/design
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth.auth_service import get_current_user
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
    # 기준층 평면도를 실제 평형믹스로 분할하기 위한 입력(미전달 시 generic 균등분할)
    building_use: str = "공동주택"
    unit_types: Optional[list[str]] = None
    zone_code: Optional[str] = None


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


class PhotorealRenderRequest(BaseModel):
    """AI 포토리얼 렌더 요청 — 3D 뷰포트 캡처 이미지를 사실적 외관 이미지로 변환.

    image_base64: 3D 화면 캡처(순수 base64 또는 data URI 모두 허용).
    style: 주간|야간|실사(기본 실사).
    strength: 0~1, 구조(깊이/윤곽) 보존 강도(기본 0.6).
    """
    image_base64: str = Field(..., min_length=1)
    style: str = Field("실사")
    strength: float = Field(0.6, ge=0.0, le=1.0)


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
    # 세대 구성(있으면 평면 세대배치·해석에 반영 — "데이터 없음" 해소)
    building_use: str = "공동주택"
    unit_types: list[str] | None = None


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
    """전체 도면 세트를 일괄 생성한다 (B-01~C-03).

    building_use·unit_types가 주어지면 AutoDesignEngine으로 실제 평형믹스(세대배치)를
    산출해 기준층 평면도를 실제 세대 분할로 그린다(미전달 시 generic 균등분할 폴백).
    """
    project_data = req.model_dump()

    # ── 실제 세대믹스 산출 → 기준층 평면도에 주입(데이터 있으면) ──
    try:
        from app.services.cad.auto_design_engine import AutoDesignEngineService

        svc = AutoDesignEngineService()
        _bw = project_data["building_width_m"]
        _bd = project_data["building_depth_m"]
        _nf = project_data["floor_count"]
        mass = {
            "building_width_m": _bw,
            "building_depth_m": _bd,
            "num_floors": _nf,
            "floor_height_m": project_data["floor_height_m"],
            "building_footprint_sqm": _bw * _bd,        # compute_unit_layout 필수 입력
            "total_floor_area_sqm": _bw * _bd * _nf,    # compute_core_layout 필수 입력
        }
        core_layout = svc.compute_core_layout(mass, req.building_use)
        unit_layout = svc.compute_unit_layout(
            mass, core_layout, req.unit_types or ["59A", "84A"], req.building_use,
        )
        project_data["units"] = unit_layout.get("units")
    except Exception:  # noqa: BLE001 — 산출 실패해도 generic 분할로 도면 생성
        pass

    drawings = svg_service.generate_full_drawing_set(project_data)
    return {
        "project_id": project_id,
        "drawings": {code: {"svg_length": len(svg), "has_content": bool(svg)}
                     for code, svg in drawings.items()},
        "drawing_count": len(drawings),
    }


@router.get("/{project_id}/drawings/{code}/svg", response_class=Response)
async def get_drawing_svg(
    project_id: str,
    code: str,
    site_width_m: float = Query(60.0, gt=0),
    site_depth_m: float = Query(40.0, gt=0),
    building_width_m: float = Query(40.0, gt=0),
    building_depth_m: float = Query(20.0, gt=0),
    floor_count: int = Query(5, ge=1, le=200),
    floor_height_m: float = Query(3.0, gt=2.0),
    basement_floors: int = Query(1, ge=0),
    unit_width_m: float = Query(8.0, gt=0),
    setback_m: float = Query(3.0, ge=0),
    parking_count: int = Query(50, ge=0),
    project_name: str = Query("PropAI"),
    building_use: str = Query("공동주택"),
    unit_types: Optional[str] = Query(None, description="쉼표구분 평형(예: 59A,84A)"),
):
    """특정 도면의 SVG를 반환한다.

    선택한 건축개요(부지·건물 치수·층수)를 쿼리로 받아 실제 기하로 도면을 생성한다.
    파라미터 미전달 시 기존 기본값(부지 60×40 / 건물 40×20 / 5층)으로 폴백.
    이로써 동일 기하를 3D BIM과 공유 → CAD↔BIM 정합.
    building_use·unit_types가 오면 기준층 평면도를 실제 평형믹스로 분할한다.
    """
    project_data = {
        "site_width_m": site_width_m, "site_depth_m": site_depth_m,
        "building_width_m": building_width_m, "building_depth_m": building_depth_m,
        "floor_count": floor_count, "floor_height_m": floor_height_m,
        "basement_floors": basement_floors, "unit_width_m": unit_width_m,
        "setback_m": setback_m, "parking_count": parking_count,
        "project_name": project_name,
    }
    # ── 실제 세대믹스 산출 → 기준층 평면도에 주입(GET도 2D·3D 정합 유지) ──
    try:
        from app.services.cad.auto_design_engine import AutoDesignEngineService

        svc = AutoDesignEngineService()
        mass = {
            "building_width_m": building_width_m, "building_depth_m": building_depth_m,
            "num_floors": floor_count, "floor_height_m": floor_height_m,
            "building_footprint_sqm": building_width_m * building_depth_m,
            "total_floor_area_sqm": building_width_m * building_depth_m * floor_count,
        }
        core_layout = svc.compute_core_layout(mass, building_use)
        utypes = [t.strip() for t in unit_types.split(",") if t.strip()] if unit_types else ["59A", "84A"]
        unit_layout = svc.compute_unit_layout(mass, core_layout, utypes, building_use)
        project_data["units"] = unit_layout.get("units")
    except Exception:  # noqa: BLE001 — 산출 실패해도 generic 분할로 도면 생성
        pass

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
        from sqlalchemy import text

        # tenant_id만 raw SQL로 조회(Project ORM은 DB 컬럼과 불일치 위험 — 우회)
        row = (await db.execute(
            text("SELECT tenant_id FROM projects WHERE id = :pid"), {"pid": str(pid)}
        )).first()
        if row is None:
            return {
                "project_id": project_id, "drawing_code": req.drawing_code,
                "drawing_type": req.drawing_type, "svg_length": len(req.svg_content),
                "layer_count": len(req.layers), "status": "echo(프로젝트없음)",
            }
        tenant_id = row[0]

        # 현재 최대 버전 +1 (raw — ORM 컬럼 불일치 우회)
        ver_row = (await db.execute(
            text("SELECT COALESCE(MAX(version_number),0) FROM design_versions "
                 "WHERE project_id = :pid AND design_type = 'cad_2d'"),
            {"pid": str(pid)},
        )).first()
        next_ver = int(ver_row[0]) + 1 if ver_row else 1

        design_json = json.dumps({
            "drawing_code": req.drawing_code,
            "drawing_type": req.drawing_type,
            "drawing_name": req.drawing_name,
            "points": req.points,
            "lines": req.lines,
            "surfaces": req.surfaces,
            "svg_content": req.svg_content[:50000],
            "layers": req.layers,
            "vector_data": req.vector_data,
        }, ensure_ascii=False)

        await db.execute(
            text("""
                INSERT INTO design_versions
                  (id, tenant_id, project_id, version_number, design_type,
                   floor_count, max_height_m, design_data_json, notes,
                   created_at, updated_at)
                VALUES
                  (gen_random_uuid(), :tid, :pid, :ver, 'cad_2d',
                   :fc, :mh, CAST(:dj AS json), :notes, now(), now())
            """),
            {"tid": str(tenant_id), "pid": str(pid), "ver": next_ver,
             "fc": req.floor_count, "mh": req.building_height_m,
             "dj": design_json, "notes": f"CAD 편집 저장 v{next_ver}"},
        )
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

    from sqlalchemy import text

    try:
        pid = _uuid.UUID(project_id)
    except (ValueError, AttributeError):
        return {"saved": False, "reason": "UUID 아님"}

    try:
        row = (await db.execute(
            text("""
                SELECT version_number, design_data_json, updated_at
                FROM design_versions
                WHERE project_id = :pid AND design_type = 'cad_2d'
                ORDER BY version_number DESC LIMIT 1
            """),
            {"pid": str(pid)},
        )).first()
        if row is None:
            return {"saved": False}
        data = row[1]
        if isinstance(data, str):
            data = json.loads(data)
        return {
            "saved": True,
            "version": row[0],
            "data": data or {},
            "updated_at": str(row[2]) if row[2] else None,
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

    # ── 세대배치·코어 산출(엔진) — 해석/평면에 "세대수·평형" 반영(데이터 없음 해소) ──
    units_data: dict = {}
    try:
        from app.services.cad.auto_design_engine import AutoDesignEngineService
        svc = AutoDesignEngineService()
        core_layout = svc.compute_core_layout(mass, req.building_use)
        unit_layout = svc.compute_unit_layout(
            mass, core_layout, req.unit_types or ["59A", "84A"], req.building_use,
        )
        units_data = {
            "core_positions": core_layout.get("core_positions"),
            "corridor_width_m": core_layout.get("corridor_width_m"),
            "units": unit_layout.get("units"),
            "total_units": unit_layout.get("total_units"),
        }
    except Exception:  # noqa: BLE001
        units_data = {}

    # ── DesignInterpreter(Claude) 설계 AI 해석 — 실패해도 모델은 정상 반환 ──
    ai_interpretation = None
    try:
        from app.services.ai.design_interpreter import DesignInterpreter

        interp = await DesignInterpreter().generate_interpretation({
            **mass,
            "zone_code": req.zone_code,
            "building_use": req.building_use,
            **units_data,
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


@router.post("/{project_id}/mass")
async def compute_design_mass(project_id: str, req: BimGenerateRequest):
    """선택한 건축개요로 표준 건축 매스를 산출한다 (LLM 미호출, 경량).

    CAD 2D·3D BIM이 동일한 기하를 공유하도록 하는 단일 출처.
    매스 직접입력 우선 → 대지정보(land_area+zone) AutoDesignEngine → 폴백.
    """
    mass = _resolve_mass(req)
    bw = float(mass["building_width_m"])
    bd = float(mass["building_depth_m"])
    nf = int(mass["num_floors"])
    fh = float(mass.get("floor_height_m", req.floor_height_m))
    setback = 3.0
    return {
        "project_id": project_id,
        "building_width_m": round(bw, 2),
        "building_depth_m": round(bd, 2),
        "num_floors": nf,
        "floor_height_m": fh,
        "building_height_m": round(nf * fh, 2),
        # 도면 프레임용 부지 치수(건물 + 이격거리)
        "site_width_m": round(bw + setback * 2, 2),
        "site_depth_m": round(bd + setback * 2, 2),
        "setback_m": setback,
        "bcr_pct": mass.get("bcr_pct"),
        "far_pct": mass.get("far_pct"),
        "total_units": mass.get("total_units"),
        "unit_width_m": round(float(mass.get("unit_width_m", 8.0)), 2),
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


async def _load_mass_from_design_version(
    design_version_id: str, db: AsyncSession
) -> dict[str, Any] | None:
    """design_versions(UUID) 행에서 저장된 매스를 복원한다(없으면 None).

    floor_count/max_height_m 컬럼 + design_data_json의 매스 필드를 사용해
    _resolve_mass와 동일한 형태(building_width/depth_m, num_floors, floor_height_m)로
    재구성한다. 폭/깊이가 저장돼 있지 않으면(예: cad_2d 편집본) 합리적 기본값으로 보완.
    가짜 데이터 생성 금지 — 조회 실패/무자료 시 None.
    """
    import uuid as _uuid

    from sqlalchemy import text

    try:
        vid = _uuid.UUID(design_version_id)
    except (ValueError, AttributeError):
        return None
    try:
        row = (await db.execute(
            text("""
                SELECT floor_count, max_height_m, design_data_json
                FROM design_versions
                WHERE id = :vid LIMIT 1
            """),
            {"vid": str(vid)},
        )).first()
    except Exception as e:  # noqa: BLE001
        import structlog

        structlog.get_logger().warning("design_version 조회 실패", error=str(e)[:120])
        return None
    if row is None:
        return None

    floor_count, max_height_m, ddj = row[0], row[1], row[2]
    if isinstance(ddj, str):
        try:
            ddj = json.loads(ddj)
        except (ValueError, TypeError):
            ddj = {}
    ddj = ddj or {}

    nf = int(floor_count) if floor_count else int(ddj.get("num_floors") or ddj.get("floor_count") or 5)
    fh = float(ddj.get("floor_height_m") or 3.0)
    if max_height_m and nf:
        fh = round(float(max_height_m) / nf, 3) if nf else fh
    bw = float(ddj.get("building_width_m") or 0) or 12.0
    bd = float(ddj.get("building_depth_m") or 0) or 9.0
    mass = {
        "building_width_m": bw,
        "building_depth_m": bd,
        "num_floors": nf,
        "floor_height_m": fh,
    }
    return _enrich_interior(mass)


@router.get("/{design_version_id}/bim/model.glb", response_class=Response)
async def get_bim_glb_get(
    design_version_id: str,
    db: AsyncSession = Depends(get_db),
    floor_count: int | None = Query(None, ge=1, le=200),
    floor_height_m: float = Query(3.0, gt=2.0),
    building_width_m: float | None = Query(None, gt=0),
    building_depth_m: float | None = Query(None, gt=0),
    land_area_sqm: float | None = Query(None, gt=0),
    zone_code: str = Query("2R"),
    project_name: str = Query("PropAI"),
):
    """3D BIM 모델을 glTF binary(.glb)로 GET 반환한다 — 프론트 GLTFLoader.loadAsync 직접 로드.

    POST 라우트는 보존(회귀 0). 이 GET 라우트가 프론트 BuildingGlb의 기본 로드 경로.
    design_version_id가 UUID면 design_versions 테이블에서 매스를 복원하고, 아니거나
    행이 없으면 쿼리/기본 폴백 매스(_resolve_mass)로 절차생성한다(가짜 금지·정직한 매스).
    ETag/Cache-Control로 동일 매스 재요청을 캐시한다.
    """
    from app.services.bim.ifc_generator_service import build_ifc_from_mass
    from app.services.bim.ifc_to_gltf_service import IfcToGltfService

    mass = await _load_mass_from_design_version(design_version_id, db)
    if mass is None:
        # UUID 아님/행 없음 → 쿼리·기본 폴백 매스로 정직 절차생성
        fallback_req = BimGenerateRequest(
            building_width_m=building_width_m,
            building_depth_m=building_depth_m,
            floor_count=floor_count,
            floor_height_m=floor_height_m,
            land_area_sqm=land_area_sqm,
            zone_code=zone_code,
            project_name=project_name,
        )
        mass = _resolve_mass(fallback_req)

    try:
        ifc_bytes = build_ifc_from_mass(mass, project_name=project_name)
        glb = IfcToGltfService().convert(ifc_bytes)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"BIM 모델 생성 실패: {str(e)[:120]}") from e

    import hashlib

    etag = '"' + hashlib.sha1(glb).hexdigest()[:16] + '"'  # noqa: S324 — 캐시 검증용(비보안)
    return Response(
        content=glb,
        media_type="model/gltf-binary",
        headers={
            "Content-Disposition": f"inline; filename={design_version_id}.glb",
            "ETag": etag,
            "Cache-Control": "public, max-age=300",
        },
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


@router.post("/{project_id}/render-photoreal")
async def render_photoreal(
    project_id: str,
    req: PhotorealRenderRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """3D 뷰포트 이미지를 ControlNet으로 포토리얼 렌더(비파괴 — 원본 3D 불변).

    정직 처리:
    - 렌더 API 키 미설정 → status="no_key"(에러 아님, 200). 가짜 이미지 절대 금지.
    - 외부 호출 실패 → status="error"(사유 안내). 성공 시에만 과금.
    """
    from app.services.billing import billing_service
    from app.services.drawing import photoreal_render_service

    result = await photoreal_render_service.render_photoreal(
        req.image_base64, style=req.style, strength=req.strength
    )

    # 키 미설정/실패는 그대로 정직 반환(과금 없음).
    if result.get("status") != "ok":
        return result

    # 렌더 성공 시에만 사용료 차감(best-effort — 차감 실패해도 결과는 제공, 후불 누적).
    charged = None
    try:
        await billing_service.load_config(db)
        c = await billing_service.charge_service(db, user.id, "photoreal_render")
        charged = c.get("charged_krw")
    except Exception:  # noqa: BLE001
        pass

    return {
        "status": "ok",
        "image_url": result["image_url"],
        "message": "비파괴 렌더(원본 3D 불변)",
        "charged": charged,
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
