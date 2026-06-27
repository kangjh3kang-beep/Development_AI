"""v61 설계도면 라우터 — 전체 도면 세트 + 대안 선정 + 인허가 도서.

prefix: /api/v1/design
"""

from __future__ import annotations

import copy
import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth.auth_service import get_current_user, get_current_user_optional
from app.services.cad import design_run_cache  # 설계 매스 input_hash 멱등 캐시(시간절감)
from app.services.cad.design_contract import build_mass_contract  # C2R 계약 부착 공용 헬퍼
from app.services.cad.provenance import compute_input_hash  # 결정적 입력 지문(int/float·키순서 정규화)
from app.services.drawing.design_alternative_selector import DesignAlternativeSelector
from app.services.drawing.svg_drawing_service import SVGDrawingService
from apps.api.database.session import get_db

router = APIRouter(prefix="/api/v1/design", tags=["v61 설계도면"])
svg_service = SVGDrawingService()
alt_selector = DesignAlternativeSelector()


async def _assert_project_owned(project_id: str, db: AsyncSession, user: Any) -> Optional[str]:
    """project_id의 tenant 소유권을 검사한다(v2_feasibility 인증 패턴 준용).

    반환:
    - project_id가 UUID가 아니면(데모/임시 ID) None — 소유권 검사 생략(graceful echo 경로).
    - UUID이고 프로젝트가 존재하면 그 tenant_id(str). user.tenant_id와 불일치면 403.
    - UUID이나 프로젝트 행이 없으면 None — 호출부가 "프로젝트없음" graceful 처리.

    가짜 통과 금지: 소유 tenant가 분명히 다르면 403으로 거부한다.
    """
    import uuid as _uuid

    from sqlalchemy import text

    try:
        pid = _uuid.UUID(project_id)
    except (ValueError, AttributeError):
        return None  # 비UUID — 소유권 검사 불가(데모 경로)

    row = (await db.execute(
        text("SELECT tenant_id FROM projects WHERE id = :pid"), {"pid": str(pid)}
    )).first()
    if row is None:
        return None  # 프로젝트 없음 — 호출부가 정직 처리
    owner_tenant = str(row[0]) if row[0] is not None else None
    if owner_tenant is not None and str(getattr(user, "tenant_id", "")) != owner_tenant:
        raise HTTPException(status_code=403, detail="해당 프로젝트에 대한 권한이 없습니다")
    return owner_tenant


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
    # DXF 내보내기 도면종류 — 평면(floor_plan)/상세(detail)/단면(section)/입면(elevation)/배치(site).
    # 미전달 시 floor_plan(기존 동작 보존 — 하위호환).
    drawing_type: str = "floor_plan"


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
    # CAD2.0 셰이프(polygon/rect/polyline/line/circle/label) — 전달 시에만
    # design_data_json에 기록(빈 배열 미기록 → 기존 저장 JSON 불변, 하위호환).
    shapes: list[dict[str, Any]] = Field(default_factory=list)
    floor_count: Optional[int] = None
    building_height_m: Optional[float] = None
    # 편집본 매스치수(폴리곤 bbox 역산값) — _load_mass_from_design_version이 GLB/해석에 소비.
    # 미전달 시 None(저장 JSON에 미기록 → 로드 시 합리적 기본값 폴백, 하위호환).
    building_width_m: Optional[float] = None
    building_depth_m: Optional[float] = None
    floor_height_m: Optional[float] = None


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
    # DesignAlternativeSelector.simulate가 dict({iterations, noise_pct, win_rates})를 반환 →
    # list가 아닌 dict로 교정(빈 대안 시 selector가 []를 줄 수 있어 기본값은 dict).
    mc_results: dict[str, Any] = Field(default_factory=dict)
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


def _parse_mix_param(mix: Optional[str], floor_count: int) -> Optional[list[dict[str, Any]]]:
    """P4 슬라이더 명시 세대믹스 파싱: 'type:area:total' 쉼표구분 → units 리스트.

    예) '59A:59:20,84A:84:20' → [{type,area_sqm,count_per_floor,total_count}, ...]
    형식 오류 시 None(자동 산출로 폴백).
    """
    if not mix:
        return None
    nf = max(1, floor_count)
    units: list[dict[str, Any]] = []
    try:
        for seg in mix.split(","):
            seg = seg.strip()
            if not seg:
                continue
            parts = seg.split(":")
            if len(parts) != 3:
                continue
            t, area_s, total_s = parts
            area = float(area_s)
            total = int(float(total_s))
            if area <= 0 or total <= 0:
                continue
            units.append({
                "type": t.strip(),
                "area_sqm": round(area, 1),
                "count_per_floor": max(1, round(total / nf)),
                "total_count": total,
            })
    except (ValueError, TypeError):
        return None
    return units or None


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
    mix: Optional[str] = Query(None, description="세대믹스 명시(P4 슬라이더): 'type:area:total' 쉼표구분(예: 59A:59:20,84A:84:20)"),
):
    """특정 도면의 SVG를 반환한다.

    선택한 건축개요(부지·건물 치수·층수)를 쿼리로 받아 실제 기하로 도면을 생성한다.
    파라미터 미전달 시 기존 기본값(부지 60×40 / 건물 40×20 / 5층)으로 폴백.
    이로써 동일 기하를 3D BIM과 공유 → CAD↔BIM 정합.
    mix가 오면 그 명시 세대믹스로, 없고 building_use·unit_types가 오면 자동 산출로 평면 분할한다.
    """
    project_data: dict[str, Any] = {
        "site_width_m": site_width_m, "site_depth_m": site_depth_m,
        "building_width_m": building_width_m, "building_depth_m": building_depth_m,
        "floor_count": floor_count, "floor_height_m": floor_height_m,
        "basement_floors": basement_floors, "unit_width_m": unit_width_m,
        "setback_m": setback_m, "parking_count": parking_count,
        "project_name": project_name,
    }
    # ── 세대믹스 → 기준층 평면도 주입 ── mix(P4 슬라이더 명시) 우선, 없으면 자동 산출 ──
    explicit_units = _parse_mix_param(mix, floor_count)
    if explicit_units:
        project_data["units"] = explicit_units
    else:
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


# ── P4: 세대믹스 시뮬레이터(비율 슬라이더 → 평면 세대 재배치 + 약식 수지 실시간) ──

_PYEONG_TO_SQM = 3.305785


class UnitMixEntry(BaseModel):
    """평형별 입력: 타입명·전용면적(㎡)·비율(%)."""
    type: str
    area_sqm: float = Field(gt=0)
    ratio_pct: float = Field(ge=0)


class UnitMixSimulateRequest(BaseModel):
    """세대믹스 시뮬레이션 요청. 외부 API 호출 없는 자체완결 고속 계산(슬라이더용)."""
    building_width_m: float = Field(gt=0)
    building_depth_m: float = Field(gt=0)
    floor_count: int = Field(ge=1, le=200)
    building_use: str = "공동주택"
    efficiency_pct: float = Field(75.0, gt=0, le=100)   # 전용률(연면적 대비 분양가능면적)
    mix: list[UnitMixEntry]
    land_area_sqm: Optional[float] = None
    sale_price_per_pyeong_won: Optional[float] = None    # 원/평(F1 시세 전달 권장)
    official_price_per_sqm: Optional[float] = None        # 공시지가 원/㎡(토지비)
    price_multiplier: float = 1.2                          # 감정가 배율
    build_cost_per_sqm: Optional[int] = None              # 직접공사비 단가 원/㎡(override)
    # 편집본 건축면적(㎡) — 전달 시 폭×깊이 대신 이 값으로 연면적·전용면적 산정(CAD 편집 정합).
    # 미전달 시 building_width_m×building_depth_m(기존 동작, 하위호환).
    footprint_sqm: Optional[float] = Field(None, gt=0)


def _use_to_building_type(use: str) -> str:
    """한글 용도 → 공사비/단가 building_type 키."""
    s = use or ""
    if "오피스텔" in s:
        return "officetel"
    if "상가" in s or "근린" in s or "판매" in s:
        return "commercial"
    if "업무" in s or "오피스" in s:
        return "office"
    if "단독" in s or "다세대" in s or "타운" in s:
        return "townhouse"
    return "apartment"


@router.post("/{project_id}/unit-mix/simulate")
async def simulate_unit_mix(project_id: str, req: UnitMixSimulateRequest):
    """세대믹스 비율(슬라이더)로 평형별 세대수·분양수입·약식 ROI를 실시간 산출한다.

    - 평면 재배치용 units(타입·전용면적·층당/총세대수)를 비율대로 직접 배분(GET svg에 그대로 전달 가능).
    - 분양수입 = Σ 세대수 × 전용평 × 분양가(원/평). 분양가 미전달 시 기본값(시장가 미연동 표기).
    - 약식 ROI = (수입 - 토지비 - 직접공사비 - 간접비)/총사업비. 정밀 수지는 투자수익성(ROI) 메뉴.
    """
    from app.services.feasibility.construction_cost_engine import (
        DEFAULT_INDIRECT_RATIOS,
        calculate_direct_cost,
    )

    # 건축면적: 편집본 footprint_sqm 전달 시 우선(CAD 편집 정합), 미전달 시 폭×깊이(하위호환).
    footprint = req.footprint_sqm if req.footprint_sqm else req.building_width_m * req.building_depth_m
    gfa = footprint * req.floor_count
    sellable = gfa * (req.efficiency_pct / 100.0)

    # 비율 정규화(합계 0이면 균등)
    total_ratio = sum(max(0.0, e.ratio_pct) for e in req.mix)
    entries = req.mix or []
    if total_ratio <= 0 and entries:
        for e in entries:
            e.ratio_pct = 100.0 / len(entries)
        total_ratio = 100.0

    units: list[dict[str, Any]] = []
    revenue_won = 0
    nf = max(1, req.floor_count)
    price = req.sale_price_per_pyeong_won
    price_source = "전달 시세(원/평)" if price and price > 0 else "기본값(시장가 미연동)"
    if not price or price <= 0:
        price = 20_000_000.0  # 2,000만원/평 보수적 기본값(반드시 F1 시세로 대체 권장)

    for e in entries:
        if e.area_sqm <= 0 or total_ratio <= 0:
            continue
        alloc_area = sellable * (e.ratio_pct / total_ratio)
        total_count = int(alloc_area // e.area_sqm)
        if total_count <= 0:
            continue
        per_floor = max(1, round(total_count / nf))
        area_pyeong = e.area_sqm / _PYEONG_TO_SQM
        unit_rev = int(total_count * area_pyeong * price)
        revenue_won += unit_rev
        units.append({
            "type": e.type,
            "area_sqm": round(e.area_sqm, 1),
            "count_per_floor": per_floor,
            "total_count": total_count,
            "area_pyeong": round(area_pyeong, 1),
            "ratio_pct": round(e.ratio_pct / total_ratio * 100, 1),
            "revenue_won": unit_rev,
        })

    total_units = sum(u["total_count"] for u in units)
    used_area = sum(u["total_count"] * u["area_sqm"] for u in units)

    # 공사비(직접) + 간접비
    btype = _use_to_building_type(req.building_use)
    direct = calculate_direct_cost(
        total_gfa_sqm=gfa, building_type=btype,
        unit_cost_per_sqm=req.build_cost_per_sqm,
    )
    build_cost_won = int(direct["total_direct_cost_won"])
    indirect_ratio = sum(DEFAULT_INDIRECT_RATIOS.values())  # 설계·감리·예비·일반관리 합
    indirect_cost_won = int(build_cost_won * indirect_ratio)

    # 토지비(공시지가×배율, 입력 시에만)
    land_cost_won = 0
    if req.official_price_per_sqm and req.land_area_sqm:
        land_cost_won = int(req.official_price_per_sqm * req.land_area_sqm * req.price_multiplier)

    total_cost_won = land_cost_won + build_cost_won + indirect_cost_won
    profit_won = revenue_won - total_cost_won
    roi_pct = round(profit_won / total_cost_won * 100, 1) if total_cost_won > 0 else 0.0

    return {
        "units": units,
        "total_units": total_units,
        "gfa_sqm": round(gfa, 1),
        "sellable_area_sqm": round(sellable, 1),
        "used_area_sqm": round(used_area, 1),
        "revenue_won": revenue_won,
        "land_cost_won": land_cost_won,
        "build_cost_won": build_cost_won,
        "indirect_cost_won": indirect_cost_won,
        "total_cost_won": total_cost_won,
        "profit_won": profit_won,
        "roi_pct": roi_pct,
        "sale_price_per_pyeong_won": int(price),
        "price_source": price_source,
        "build_unit_cost_per_sqm": direct["unit_cost_per_sqm"],
        "note": "약식 실시간 추정 — 정밀 수지는 투자수익성(ROI) 메뉴에서 산출",
    }


@router.post("/{project_id}/drawings/save", response_model=DrawingSaveResponse)
async def save_drawing(
    project_id: str,
    req: CADSaveRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """편집된 CAD 도면을 design_versions 테이블에 영속화한다.

    CADEditor가 드래그 편집한 points/lines/surfaces를 design_data_json에 저장.
    프로젝트별 버전 자동 증가. project_id가 UUID가 아니면(데모) 저장 스킵·echo.
    인증 필수(무인증 401) + 프로젝트 tenant 소유권 검사(불일치 403).
    """
    import uuid as _uuid

    # 소유권 검사(비UUID/프로젝트없음 → None, graceful echo로 진행 / 타 tenant → 403)
    await _assert_project_owned(project_id, db, user)

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

        design_payload: dict[str, Any] = {
            "drawing_code": req.drawing_code,
            "drawing_type": req.drawing_type,
            "drawing_name": req.drawing_name,
            "points": req.points,
            "lines": req.lines,
            "surfaces": req.surfaces,
            "svg_content": req.svg_content[:50000],
            "layers": req.layers,
            "vector_data": req.vector_data,
        }
        # CAD2.0 shapes(전달 시에만 기록 — 빈 배열 미기록, 기존 저장 JSON 불변).
        if req.shapes:
            design_payload["shapes"] = req.shapes
        # 편집본 매스치수(전달 시에만 기록) — _load_mass_from_design_version이 GLB/해석에 소비.
        if req.building_width_m is not None:
            design_payload["building_width_m"] = req.building_width_m
        if req.building_depth_m is not None:
            design_payload["building_depth_m"] = req.building_depth_m
        if req.floor_height_m is not None:
            design_payload["floor_height_m"] = req.floor_height_m
        design_json = json.dumps(design_payload, ensure_ascii=False)

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
async def load_drawing(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """저장된 최신 CAD 편집본을 불러온다. 없으면 saved=false.

    인증 필수(무인증 401) + 프로젝트 tenant 소유권 검사(불일치 403).
    """
    import uuid as _uuid

    from sqlalchemy import text

    # 소유권 검사(타 tenant → 403; 비UUID/프로젝트없음은 아래 graceful 분기로 진행)
    await _assert_project_owned(project_id, db, user)

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
    """DXF 파일로 내보낸다.

    drawing_type으로 도면종류를 분기한다(평면/상세/단면/입면/배치 5종).
    미전달/미상 시 floor_plan(기본 평면도 — 하위호환).
    """
    try:
        from app.services.cad.parametric_cad_service import ParametricCADService
        cad_service = ParametricCADService()
        dtype = (req.drawing_type or "floor_plan").strip().lower()

        if dtype == "detail":
            dxf_bytes = cad_service.create_detailed_floor_plan_dxf(
                building_width_m=req.building_width_m,
                building_depth_m=req.building_depth_m,
                floor_count=req.floor_count,
                unit_width_m=req.unit_width_m,
            )
        elif dtype == "section":
            dxf_bytes = cad_service.create_section_drawing_dxf(
                building_width_m=req.building_width_m,
                building_depth_m=req.building_depth_m,
                floor_count=req.floor_count,
                floor_height_m=req.floor_height_m,
                basement_floors=req.basement_floors,
            )
        elif dtype == "elevation":
            dxf_bytes = cad_service.create_elevation_drawing_dxf(
                building_width_m=req.building_width_m,
                building_depth_m=req.building_depth_m,
                floor_count=req.floor_count,
                floor_height_m=req.floor_height_m,
                unit_width_m=req.unit_width_m,
            )
        elif dtype == "site":
            dxf_bytes = cad_service.create_site_plan_dxf(
                site_width_m=req.site_width_m,
                site_depth_m=req.site_depth_m,
                building_width_m=req.building_width_m,
                building_depth_m=req.building_depth_m,
                parking_count=req.parking_count,
            )
        else:  # floor_plan(기본) — 하위호환
            dxf_bytes = cad_service.create_floor_plan_dxf(
                building_width_m=req.building_width_m,
                building_depth_m=req.building_depth_m,
                floor_count=req.floor_count,
                unit_width_m=req.unit_width_m,
            )
        return Response(
            content=dxf_bytes,
            media_type="application/dxf",
            headers={"Content-Disposition": f"attachment; filename={project_id}_{dtype}.dxf"},
        )
    except (ImportError, ValueError):
        return Response(content=b"DXF_PLACEHOLDER", media_type="application/dxf")


@router.get("/{project_id}/drawings/export-edited-dxf", response_class=Response)
async def export_edited_dxf(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """저장된 CAD 편집본(points/surfaces/scale)을 정식 DXF로 내보낸다(WP-04 직변환).

    저장된 design_data_json의 points·surfaces·vector_data["scale"]를
    ParametricCADService.create_dxf_from_edited_points에 넘겨 편집본 그대로의
    DXF(닫힌 LWPOLYLINE + 정식 DIMENSION)를 반환한다.
    CAD2.0 shapes가 저장돼 있으면 shapes 모드(전체 셰이프 직변환)로 내보낸다.

    정직 처리: 저장본이 없으면 404(가짜 도면 생성 금지). 인증 필수(401) + 소유권(403).
    """
    import uuid as _uuid

    from sqlalchemy import text

    # 소유권 검사(타 tenant → 403)
    await _assert_project_owned(project_id, db, user)

    try:
        pid = _uuid.UUID(project_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="저장된 편집본 없음(UUID 아님)")

    row = (await db.execute(
        text("""
            SELECT design_data_json
            FROM design_versions
            WHERE project_id = :pid AND design_type = 'cad_2d'
            ORDER BY version_number DESC LIMIT 1
        """),
        {"pid": str(pid)},
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="저장된 편집본 없음")

    data = row[0]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            data = {}
    data = data or {}

    points = data.get("points") or []
    surfaces = data.get("surfaces") or []
    # CAD2.0 shapes가 저장돼 있으면 shapes 모드(전체 셰이프 변환) — 없으면 기존 points 직변환.
    shapes = data.get("shapes") or []
    if not points and not shapes:
        raise HTTPException(status_code=404, detail="저장된 편집 좌표 없음")

    # CADEditor 저장 계약: vector_data["scale"] = px/m(기본 10). 직변환 서비스에 전달.
    vector_data = data.get("vector_data") or {}
    try:
        scale = float(vector_data.get("scale") or 10.0)
    except (ValueError, TypeError):
        scale = 10.0
    if scale <= 0:
        scale = 10.0

    from app.services.cad.parametric_cad_service import ParametricCADService

    try:
        dxf_bytes = ParametricCADService().create_dxf_from_edited_points(
            points=points, surfaces=surfaces, scale_px_per_m=scale,
            shapes=shapes or None,
        )
    except ValueError as e:
        # 점 3개 미만 등 폴리곤 구성 불가 — 가짜 도면 대신 정직하게 422.
        raise HTTPException(status_code=422, detail=f"편집본 DXF 변환 실패: {str(e)[:120]}") from e

    return Response(
        content=dxf_bytes,
        media_type="application/dxf",
        headers={"Content-Disposition": f"attachment; filename={project_id}_edited.dxf"},
    )


_MAX_DXF_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB


@router.post("/{project_id}/drawings/import-dxf")
async def import_dxf(
    project_id: str,
    file: UploadFile = File(...),
    scale_px_per_m: float = Query(10.0, gt=0, description="캔버스 px/m 스케일(CADEditor 기본 10)"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """업로드한 DXF를 CAD2.0 셰이프(px 좌표)로 파싱해 반환한다(영속 없음 — 저장은 save).

    인증 필수(무인증 401) + 프로젝트 tenant 소유권 검사(불일치 403).
    .dxf만 지원(그 외 415 + DWG 변환 안내), 20MB 초과 413, 파싱 불가 422(정직 —
    가짜 셰이프 생성 금지). 미지원 엔티티는 ignored 목록으로 투명 보고.
    """
    # 소유권 검사(비UUID/프로젝트없음 → 통과, 타 tenant → 403)
    await _assert_project_owned(project_id, db, user)

    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".dxf"):
        raise HTTPException(
            status_code=415,
            detail="DXF 파일만 지원합니다. DWG는 CAD 프로그램에서 'DXF로 저장' 후 업로드해 주세요.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(data) > _MAX_DXF_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="DXF가 너무 큽니다(최대 20MB).")

    from app.services.cad.dxf_import_service import parse_dxf_to_shapes

    try:
        result = parse_dxf_to_shapes(data, scale_px_per_m=scale_px_per_m)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"DXF 파싱 실패: {str(e)[:150]}") from e

    return {"project_id": project_id, "filename": filename, **result}


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


def _attach_mass_contract(mass: dict[str, Any], req: BimGenerateRequest) -> dict[str, Any]:
    """site/legal이 없는 분기(명시 치수·폴백)에서 매스에 C2R 계약을 부착한다(공용·무날조).

    이 분기는 대지정보(SiteInput)·법규(legal)가 없으므로 rule_trace/rule_set_hash는 생략하고
    (가짜 법규 entry 금지), envelope_result+geometry_invariants만 붙인다. provenance 핑거프린트는
    req의 결정적 필드(zone·use·치수·층고)로 구성해 같은 요청이면 같은 run_id가 나오게 한다(멱등).
    """
    fingerprint = {
        "zone_code": req.zone_code,
        "building_use": req.building_use,
        "building_width_m": mass.get("building_width_m"),
        "building_depth_m": mass.get("building_depth_m"),
        "num_floors": mass.get("num_floors"),
        "floor_height_m": mass.get("floor_height_m", req.floor_height_m),
    }
    mass["compliance"] = build_mass_contract(mass, fingerprint=fingerprint)
    return mass


def _request_fingerprint(req: BimGenerateRequest) -> dict[str, Any]:
    """_resolve_mass_uncached의 출력을 '완전히 결정하는' req 필드만 담은 결정적 dict(캐시 열쇠 원료).

    왜(쉬운 설명): 캐시는 '같은 입력이면 같은 결과'라는 멱등성에 기댄다. 그러므로 매스 산출 결과를
      바꾸는 모든 입력 필드를 빠짐없이 담아야 한다(누락 시 서로 다른 입력이 같은 열쇠가 되어 캐시 오염).
      반대로 결과에 영향 없는 비결정 필드(project_name 등)는 빼야 한다(같은 결과인데 열쇠가 갈리는 낭비 방지).

    포함 필드 근거(이 필드들이 _resolve_mass_uncached의 모든 분기 입력을 완전히 결정한다):
      - building_width_m·building_depth_m·floor_count: 명시 치수 분기의 매스를 직접 결정.
      - floor_height_m: 모든 분기의 층고(높이·envelope)에 들어간다.
      - land_area_sqm: 자동산출 분기(AutoDesignEngine)의 면적 입력. (치수 분기 vs land_area 분기 갈림도 결정)
      - zone_code: 자동산출 분기의 법정/조례 한도·건축유형 추론 입력.
      - building_use: 실내요소(_enrich_interior)·세대평형·건축유형 추론 입력.
      - unit_types: 자동산출 분기 target_unit_types. ★순서 무관이므로 sorted로 정규화(같은 집합=같은 열쇠).

    제외(비결정·결과 무영향): project_name(IFC 라벨일 뿐 매스 기하 불변), 그리고 LayoutRequest가
      추가로 받는 필드(zone_name·avg_unit_area_sqm·site_geometry·llm_adjust)는 _resolve_mass가
      소비하지 않으므로(매스는 BimGenerateRequest 필드만으로 결정) 핑거프린트에 넣지 않는다.
    """
    return {
        "building_width_m": req.building_width_m,
        "building_depth_m": req.building_depth_m,
        "floor_count": req.floor_count,
        "floor_height_m": req.floor_height_m,
        "land_area_sqm": req.land_area_sqm,
        "zone_code": req.zone_code,
        "building_use": req.building_use,
        # 평형 목록은 순서가 달라도 같은 집합이면 같은 결과 → sorted로 정규화(없으면 None).
        "unit_types": sorted(req.unit_types) if req.unit_types else None,
    }


def _resolve_mass(req: BimGenerateRequest) -> dict[str, Any]:
    """_resolve_mass_uncached를 input_hash 멱등 캐시로 감싼 얇은 래퍼(시간절감·무회귀).

    동작(쉬운 설명):
    - 요청의 결정적 핑거프린트로 열쇠(input_hash)를 만든다 → 같은 입력이면 항상 같은 열쇠.
    - 캐시에 있으면(히트) 깊은 복사본을 돌려준다 → 호출부가 mass를 고쳐도 캐시 원본은 안 더럽혀진다.
    - 없으면(미스) 실제 산출(_resolve_mass_uncached)을 돌리고, 깊은 복사본을 캐시에 저장한다.

    ★무회귀: 산출 로직·반환값은 _resolve_mass_uncached가 100% 그대로 한다(캐시는 속도만 바꾼다).
      run_id·compliance·모든 매스 키가 캐시 유무와 무관하게 동일하다.
    ★_cache_hit 마커: 응답에 'cached' 표기를 위한 내부 플래그. ★캐시에 저장하는 값에는 넣지 않는다
      (clean copy 저장) → 다음 호출이 _cache_hit을 자체적으로 다시 세팅(가짜 표기 방지·무날조).
    """
    import structlog

    key = compute_input_hash(_request_fingerprint(req))
    cached = design_run_cache.get(key)
    structlog.get_logger().info("design_run_cache", hit=bool(cached), key=key[:16])
    if cached is not None:
        # 히트: 깊은 복사본 반환(호출부 mutate가 캐시 원본을 오염시키지 않게 격리).
        result = copy.deepcopy(cached)
        result["_cache_hit"] = True
        return result
    # 미스: 실제 산출 → clean 깊은 복사본을 캐시에 저장(저장본엔 _cache_hit 없음) → 반환본만 마킹.
    mass = _resolve_mass_uncached(req)
    design_run_cache.put(key, copy.deepcopy(mass))
    mass["_cache_hit"] = False
    return mass


def _resolve_mass_uncached(req: BimGenerateRequest) -> dict[str, Any]:
    """요청에서 건축 매스를 확정한다. 매스 직접입력 우선, 없으면 대지정보로 자동산출.

    확정된 매스에 실내 요소(코어·복도·창호)를 _enrich_interior로 보강하고,
    C2R 계약(envelope_result·geometry_invariants·rule_trace)을 부착한다(전 분기 공용·additive).

    ★이 함수는 _resolve_mass(캐시 래퍼)가 호출한다. 로직·반환은 캐시 도입 전과 100% 동일하다(무회귀).
    """
    if req.building_width_m and req.building_depth_m and req.floor_count:
        mass = {
            "building_width_m": req.building_width_m,
            "building_depth_m": req.building_depth_m,
            "num_floors": req.floor_count,
            "floor_height_m": req.floor_height_m,
        }
        mass = _enrich_interior(mass)
        # ★C2R 계약 부착(공용 헬퍼) — 명시 치수 분기는 site/legal이 없으므로 rule_trace는 생략(무날조).
        #   envelope_result+geometry_invariants만 붙는다. 핑거프린트는 req의 결정적 필드로 구성.
        _attach_mass_contract(mass, req)
        return mass
    # 자동 산출: AutoDesignEngine(대지면적+용도지역 → 최적 매스)
    if req.land_area_sqm:
        from app.services.cad.auto_design_engine import AutoDesignEngineService, SiteInput

        # ★건축유형별 매싱 목적함수 배선(선결·additive): building_use·unit_types를 전달하고,
        #   massing_strategy로 건축유형을 추론해 목적함수(고층저밀/고밀/혼합)를 주입한다.
        #   추론·목적 산출 실패는 graceful(목적 미주입=기존 동작 보존·무회귀).
        massing_objective = None
        building_type = None
        try:
            from app.services.cad.massing_strategy import (
                classify_building_type,
                resolve_massing_objective,
            )

            building_type = classify_building_type(
                req.zone_code, building_use=req.building_use,
            )
            massing_objective = resolve_massing_objective(building_type, req.zone_code)
        except Exception:  # noqa: BLE001
            massing_objective = None

        svc = AutoDesignEngineService()
        site = SiteInput(
            site_area_sqm=req.land_area_sqm,
            zone_code=req.zone_code,
            building_use=req.building_use,
            target_unit_types=req.unit_types or ["84A"],
            floor_height_m=req.floor_height_m,
            massing_objective=massing_objective,
        )
        legal = svc.get_legal_limits(req.zone_code)
        eff = svc.compute_effective_site(site)
        mass = svc.compute_optimal_mass(site, eff, legal)
        if building_type:
            mass.setdefault("building_type", building_type)
        mass = _enrich_interior(mass)
        # ★C2R 계약 부착(공용 헬퍼) — 자동산출 분기는 site·legal이 있으므로 rule_trace/rule_set_hash까지 채운다.
        #   total_units는 이 시점 미상이라 None → 세대 점검 SKIP(가짜 0세대 FAIL 금지·무날조).
        #   ★_enrich_interior 이후에 부착(실내요소가 반영된 매스 기준).
        contract = build_mass_contract(mass, site_input=site, legal=legal)
        mass["compliance"] = contract  # additive — mass dict에 부착(/mass·/layout·/bim 응답이 동봉)
        return mass
    # 최종 폴백: 합리적 기본값
    mass = {
        "building_width_m": 12.0, "building_depth_m": 9.0,
        "num_floors": req.floor_count or 5, "floor_height_m": req.floor_height_m,
    }
    mass = _enrich_interior(mass)
    # ★C2R 계약 부착(공용 헬퍼) — 폴백 분기도 site/legal 없음 → envelope_result+geometry_invariants만(무날조).
    _attach_mass_contract(mass, req)
    return mass


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
        # ★C2R 계약 동봉(additive) — _resolve_mass가 부착한 envelope_result·geometry_invariants·rule_trace.
        "compliance": mass.get("compliance"),
        # ★캐시 적중 표기(additive·무날조) — 동일 요청 2회째면 캐시 즉시반환(True).
        "cached": bool(mass.get("_cache_hit")),
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
        # ★podium-tower 매스(고FAR 상업지 주상복합) — 3D를 저층 podium+고층 tower 2-volume으로
        #   렌더하도록 프론트에 통과시킨다. 단일박스 매스면 None(프론트는 단일 렌더로 폴백).
        "massing_profile": mass.get("massing_profile"),
        "podium": mass.get("podium"),
        "tower": mass.get("tower"),
        # ★C2R 계약 동봉(additive) — _resolve_mass가 부착한 envelope_result·geometry_invariants·rule_trace.
        #   기존 키는 그대로 두고 새 키 compliance만 추가(소비처 무파손·전역 공용화 결실).
        "compliance": mass.get("compliance"),
        # ★캐시 적중 표기(additive·무날조) — 동일 요청 2회째면 캐시 즉시반환(True). 라이브 검증용.
        "cached": bool(mass.get("_cache_hit")),
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
    design_version_id: str, db: AsyncSession, user: Any = None
) -> dict[str, Any] | None:
    """design_versions(UUID) 행에서 저장된 매스를 복원한다(없으면 None).

    floor_count/max_height_m 컬럼 + design_data_json의 매스 필드를 사용해
    _resolve_mass와 동일한 형태(building_width/depth_m, num_floors, floor_height_m)로
    재구성한다. 폭/깊이가 저장돼 있지 않으면(예: cad_2d 편집본) 합리적 기본값으로 보완.
    가짜 데이터 생성 금지 — 조회 실패/무자료 시 None.

    IDOR 차단(감사 HIGH): 행에 tenant 소유권이 분명하면(owner_tenant not None) 요청자(user)의
    tenant와 일치할 때만 저장 매스를 복원한다. 불일치/무인증이면 '행을 못 본 것'으로 정직 강등(None)
    → 호출부가 폴백 절차매스로 진행해 타 설계 데이터(design_data_json)가 유출되지 않는다.
    소유 tenant가 없는 레거시 행(owner_tenant is None)은 기존대로 복원(무파괴).
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
                SELECT tenant_id, floor_count, max_height_m, design_data_json
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

    owner_tenant, floor_count, max_height_m, ddj = row[0], row[1], row[2], row[3]
    # 소유권 게이트: 소유 tenant가 분명한데 요청자 불일치/무인증이면 저장 매스를 노출하지 않는다.
    if owner_tenant is not None and (
        user is None or str(getattr(user, "tenant_id", "")) != str(owner_tenant)
    ):
        return None
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
    user=Depends(get_current_user_optional),
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

    # IDOR 차단: 소유 일치 사용자만 저장 매스를 받고, 무인증/타tenant/행없음은 폴백 절차매스로 강등.
    mass = await _load_mass_from_design_version(design_version_id, db, user)
    bim_source = "owned-design-version"
    if mass is None:
        # UUID 아님/행 없음/소유불일치 → 쿼리·기본 폴백 매스로 정직 절차생성(타 설계 데이터 무유출)
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
        bim_source = "fallback-procedural"

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
            "X-BIM-Source": bim_source,  # 정직표기: 소유본 복원 vs 폴백 절차매스
        },
    )


def _ascii_filename(name: str, fallback: str = "design") -> str:
    """ASCII 안전 파일명 — HTTP 헤더(latin-1)용. 비-ASCII·경로/특수문자 제거."""
    import re

    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", (name or "").strip()).strip("._")
    return cleaned[:80] or fallback


def _content_disposition(name: str, ext: str) -> str:
    """다운로드 Content-Disposition — ASCII filename + RFC 5987 filename*(유니코드 보존).

    HTTP 헤더는 latin-1만 허용하므로 한글 등은 filename=에 못 싣는다. ASCII 폴백 파일명과
    함께 filename*=UTF-8''<percent-encoded>로 원래 이름을 보존한다(헤더 주입·경로탈출 방지).
    """
    import re
    from urllib.parse import quote

    ascii_fn = f"{_ascii_filename(name)}.{ext}"
    raw = re.sub(r'[\\/\x00-\x1f"]+', "_", (name or "").strip()) or "design"
    utf8_fn = quote(f"{raw}.{ext}", safe="")
    return f'attachment; filename="{ascii_fn}"; filename*=UTF-8\'\'{utf8_fn}'


@router.post("/{project_id}/bim/export-ifc", response_class=Response)
async def export_bim_ifc(project_id: str, req: BimGenerateRequest):
    """3D BIM 모델을 IFC4 파일로 내보낸다(BIM 표준 교환).

    SP0 하드닝: param-based `/drawing/export-ifc`와 동일 견고성 — ifcopenshell 미설치 시 501,
    입력 오류 시 400, 그 외 500(원시 트레이스 비노출). Content-Disposition은 RFC 5987로
    한글 project_name을 안전 보존(latin-1 크래시 방지). 정상 경로 산출은 불변.
    """
    try:
        from app.services.bim.ifc_generator_service import build_ifc_from_mass
    except ImportError as exc:  # 모듈 자체 로드 실패
        raise HTTPException(status_code=501, detail=f"IFC 생성 모듈 누락: {exc}") from exc

    try:
        mass = _resolve_mass(req)
        ifc_bytes = build_ifc_from_mass(mass, project_name=req.project_name)
    except ImportError as exc:  # ifcopenshell 미설치(생성 호출 시점)
        raise HTTPException(
            status_code=501, detail=f"IFC 생성 의존성(ifcopenshell) 누락: {exc}",
        ) from exc
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"IFC 생성 입력 오류: {e}") from e
    except Exception as e:  # noqa: BLE001 — 원시 트레이스 비노출, 서버 로그만
        import logging

        logging.getLogger(__name__).error("BIM IFC 생성 중 오류: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="IFC 생성 중 오류가 발생했습니다") from e

    return Response(
        content=ifc_bytes,
        media_type="application/x-step",
        headers={"Content-Disposition": _content_disposition(req.project_name, "ifc")},
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
    user=Depends(get_current_user_optional),
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

    # 렌더 성공 시에만 사용료 차감(로그인 사용자일 때만; best-effort — 실패해도 결과 제공).
    charged = None
    if user is not None:
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


# ── 기하 SSOT 통합(/layout) + 오케스트레이터 노출(/proposals) ──

class LayoutRequest(BimGenerateRequest):
    """기하 SSOT(/layout) 요청 — /mass 입력(상속) + 평면 브리지·향·LLM 조정 입력.

    /mass와 동일 입력으로 매스를 확정하고, 거기에 동·층·코어·평형별 평면(generate_unit_plan
    실폴리곤)을 합성해 DesignGeometry 전체를 반환한다. 평형 믹스(unit_types)·필지 폴리곤
    (site_geometry·향 산출용)·LLM 부지맞춤 조정(llm_adjust·opt-in)을 추가로 받는다.
    """
    zone_name: str | None = None                  # 한글 용도지역명(allowed_uses·한도 키)
    avg_unit_area_sqm: float = Field(84.0, gt=0)  # 평형 미상 시 단일 평형 폴백
    site_geometry: dict[str, Any] | None = None   # 필지 GeoJSON(향 산출 — 미상이면 향 None)
    llm_adjust: bool = False                       # True면 추천 평면에 LLM 부지맞춤 미세조정(검증게이트)


class ProposalsRequest(BaseModel):
    """오케스트레이터(generate_design_proposals) 노출 요청(W1) — 부지조건 → 설계안 Top-N.

    tenant_id는 받지 않는다(인증 컨텍스트 강제). project_id는 경로(project_id)로 받아 소유검증.
    design-gen /generate와 동일 산출이며, 여기서는 설계 스튜디오 경로(/api/v1/design)로도 노출한다.
    """
    area_sqm: float = Field(..., gt=0)
    zone_code: str = "2R"
    zone_name: str | None = None
    sigungu: str | None = None
    dev_type: str = "M06"
    building_use: str | None = None
    ordinance_far_pct: float | None = Field(None, gt=0)
    ordinance_bcr_pct: float | None = Field(None, gt=0, le=100)
    width_m: float | None = Field(None, gt=0)
    depth_m: float | None = Field(None, gt=0)
    avg_unit_area_sqm: float = Field(84.0, gt=0)
    unit_types: list[str] | None = None
    top_n: int = Field(3, ge=1, le=10)
    verify: bool = False
    interpret: bool = False


def _build_site_context_for_layout(req: LayoutRequest, mass: dict[str, Any]):
    """LayoutRequest + 확정 매스 → compose용 SiteContext(composition 정본 재사용·DRY).

    매스 폭/깊이를 부지 치수 힌트로 넘기고, land_area·zone으로 법정/조례 한도를 채운다.
    """
    from app.services.design_ingest.composition import (
        map_building_use_kr,
        site_context_from_zone,
    )

    area = req.land_area_sqm or (
        float(mass.get("building_width_m") or 0) * float(mass.get("building_depth_m") or 0)
        * 100.0 / max(1.0, float(mass.get("bcr_pct") or 50.0))
    )
    return site_context_from_zone(
        req.zone_code, area,
        zone_name=req.zone_name,
        ordinance_far_pct=None, ordinance_bcr_pct=None,
        avg_unit_area_sqm=req.avg_unit_area_sqm,
        unit_types=req.unit_types,
        building_use_kr=map_building_use_kr(req.building_use),
    )


@router.post("/{project_id}/layout")
async def compute_design_layout(project_id: str, req: LayoutRequest):
    """기하 SSOT(DesignGeometry) — /mass 내부호출(매스) + 동·층·코어 + 평형별 평면(평면 브리지).

    하향식 단계: ①/mass(매스 SSOT) ②compose(평형 분해·배치 폴리곤) ③평면 브리지
    (generate_unit_plan 실폴리곤) ④코어/향 합성 → DesignGeometry 단일 정본 반환.
    선택형 LLM 부지맞춤 조정(llm_adjust)은 결정론 룰 검증게이트 통과 시에만 적용(폐기→원안 폴백).
    /mass 하위호환(매스 필드는 그대로 포함). 무날조: 미상은 None·정직고지.
    """
    from app.services.design_ingest.composition import (
        _NET_AREA_RATIO,
        compose,
        compute_unit_breakdown,
    )
    from app.services.design_ingest.design_geometry import (
        allowed_uses,
        build_design_geometry,
        llm_adjust_unit_plan,
    )

    # ① 매스(SSOT 단일화) — /mass와 동일 경로.
    mass = _resolve_mass(req)
    building_use = req.building_use or "공동주택"

    # ② compose — 평형 분해·배치 폴리곤(참조 도면 있을 때). 도면 없으면 [](아래 매스 기준 폴백).
    site = _build_site_context_for_layout(req, mass)
    candidates = compose(site, [], top_n=1)
    candidate = candidates[0].to_dict() if candidates else None

    # ②-b 도면 없이도 평면 브리지가 동작하도록 — 확정 매스 연면적으로 평형 분해(정본 재사용·DRY).
    #     compose는 참조도면 없으면 빈 결과라, /layout은 매스 SSOT(연면적·층수)에서 직접 평형을 분해해
    #     candidate.unit_breakdown을 채운다(평면 브리지 입력 보장 — D3 해소가 도면 유무와 무관).
    # ★podium-tower 매스면 주거(tower) 연면적·층수로 분해(podium 상가/주차 제외) — /units 경로
    #   (compute_unit_layout)와 동일 기준으로 정합. 단일박스면 total/num_floors 폴백(무회귀).
    gfa = mass.get("residential_gfa_sqm") or mass.get("total_floor_area_sqm")
    nfloors = mass.get("floors_for_units") or mass.get("num_floors")
    if gfa and nfloors and req.unit_types:
        per_floor_net = (float(gfa) * _NET_AREA_RATIO) / float(nfloors)
        ub = compute_unit_breakdown(per_floor_net, int(nfloors), req.unit_types)
        if ub:
            if candidate is None:
                candidate = {}
            candidate.setdefault("unit_breakdown", ub["units"])
            candidate.setdefault("estimated_units", ub["total_units"])
            candidate.setdefault("estimated_floors", int(nfloors))
            candidate.setdefault("estimated_gfa_sqm", float(gfa))

    # ③④ DesignGeometry 어셈블(매스+동+층+코어+평형별 평면) — 기하 SSOT.
    geometry = build_design_geometry(
        candidate, _site_summary_for_layout(site),
        mass=mass, site_geometry=req.site_geometry, building_use=building_use,
    )
    geo_dict = geometry.to_dict()

    # ④ LLM 부지맞춤 조정(opt-in·검증게이트) — 추천 평형(첫 평면 보유 유닛)에 best-effort 적용.
    llm_adjustment = None
    if req.llm_adjust:
        target = next((u for u in geo_dict["units"] if u.get("plan")), None)
        if target is not None:
            site_ctx = {
                "zone_name": req.zone_name, "zone_code": req.zone_code,
                "orientation": geo_dict["site"].get("orientation"),
                "area_sqm": geo_dict["site"].get("area_sqm"),
            }
            adj = await llm_adjust_unit_plan(target, site_context=site_ctx, similar_seeds=[])
            if adj is not None:
                llm_adjustment = {"unit_type": target.get("type"), **adj}
                if adj.get("applied"):
                    target["plan"]["rooms"] = adj["rooms"]  # 검증 통과분만 정본에 반영

    bw, bd = float(mass["building_width_m"]), float(mass["building_depth_m"])
    nf, fh = int(mass["num_floors"]), float(mass.get("floor_height_m", req.floor_height_m))
    return {
        "project_id": project_id,
        "geometry": geo_dict,
        "allowed_uses": allowed_uses(req.zone_name or req.zone_code),
        "llm_adjustment": llm_adjustment,
        # /mass 하위호환 필드(기존 소비처 무파손).
        "building_width_m": round(bw, 2),
        "building_depth_m": round(bd, 2),
        "num_floors": nf,
        "floor_height_m": fh,
        "building_height_m": round(nf * fh, 2),
        "bcr_pct": mass.get("bcr_pct"),
        "far_pct": mass.get("far_pct"),
        "total_units": candidate.get("estimated_units") if candidate else mass.get("total_units"),
        # ★C2R 계약 동봉(additive) — _resolve_mass가 부착한 envelope_result·geometry_invariants·rule_trace.
        "compliance": mass.get("compliance"),
        # ★캐시 적중 표기(additive·무날조) — 동일 요청 2회째면 캐시 즉시반환(True).
        "cached": bool(mass.get("_cache_hit")),
        "disclaimer": "AI 보조 초안 — 기하 SSOT(매스·배치·평면). 최종 인허가·설계 책임은 건축사.",
    }


def _site_summary_for_layout(site) -> dict[str, Any]:
    """compose SiteContext → build_design_geometry용 부지요약(면적·치수). 순수 매핑."""
    return {
        "area_sqm": site.area_sqm,
        "zone_code": site.zone_code,
        "zone_name": site.zone_name,
        "buildable_footprint_sqm": site.buildable_footprint_sqm,
        "max_gfa_sqm": site.max_gfa_sqm,
    }


@router.post("/{project_id}/proposals")
async def generate_design_proposals_endpoint(
    project_id: str,
    req: ProposalsRequest,
    current=Depends(get_current_user),
):
    """오케스트레이터 노출(W1) — 부지조건 → 인허가 부합 설계안 Top-N(근거·법령링크 동반).

    설계 스튜디오 경로(/api/v1/design)에서도 generate_design_proposals를 호출할 수 있게 노출한다.
    tenant_id는 인증 컨텍스트 강제(클라이언트 입력 무시). project_id는 경로로 받아 SSOT 일관.
    design-gen /generate와 동일 산출(중복 로직 없음 — 동일 오케스트레이터 재사용·DRY).
    """
    from app.services.design_ingest.orchestrator import (
        DesignRequest,
        generate_design_proposals,
    )

    kwargs: dict[str, Any] = {
        "area_sqm": req.area_sqm,
        "zone_code": req.zone_code,
        "zone_name": req.zone_name,
        "sigungu": req.sigungu,
        "dev_type": req.dev_type,
        "ordinance_far_pct": req.ordinance_far_pct,
        "ordinance_bcr_pct": req.ordinance_bcr_pct,
        "width_m": req.width_m,
        "depth_m": req.depth_m,
        "avg_unit_area_sqm": req.avg_unit_area_sqm,
        "unit_types": req.unit_types,
        "top_n": req.top_n,
        "tenant_id": str(getattr(current, "tenant_id", "")) or None,
        "project_id": project_id if _is_uuid(project_id) else None,
        "verify": req.verify,
        "interpret": req.interpret,
    }
    if req.building_use:
        kwargs["building_use"] = req.building_use
    return await generate_design_proposals(DesignRequest(**kwargs))


def _is_uuid(v: str) -> bool:
    import uuid as _uuid
    try:
        _uuid.UUID(str(v))
        return True
    except (ValueError, AttributeError, TypeError):
        return False
