"""v61 설계도면 라우터 — 전체 도면 세트 + 대안 선정 + 인허가 도서.

prefix: /api/v1/design
"""

from __future__ import annotations

import contextlib
import copy
import json
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import idempotency  # WP-L: Idempotency-Key 재전송 안전(뮤테이팅 커맨드)
from app.services.auth.auth_service import get_current_user, get_current_user_optional
from app.services.cad import design_run_cache  # 설계 매스 input_hash 멱등 캐시(시간절감)
from app.services.cad.design_contract import build_mass_contract  # C2R 계약 부착 공용 헬퍼
from app.services.cad.provenance import (  # 결정적 입력 지문·run_id·콘텐츠 해시(int/float·키순서 정규화)
    compute_input_hash,
    make_run_id,
    sha256_hex,
)
from app.services.cad.sheet_frame import (  # WP-F 도면틀 표준(표제란·시트매니페스트·필수시트)
    apply_title_block_dxf,
    apply_title_block_svg,
    build_sheet_manifest,
    build_title_block,
    required_sheet_codes,
)
from app.services.drawing.design_alternative_selector import DesignAlternativeSelector
from app.services.drawing.svg_drawing_service import SVGDrawingService
from app.services.report.submission_bundle import (  # WP-F 제출 번들 컴파일러
    RequiredSheetsMissingError,
    build_submission_bundle,
)
from apps.api.database.session import get_db

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/design", tags=["v61 설계도면"])
svg_service = SVGDrawingService()
alt_selector = DesignAlternativeSelector()


async def _assert_project_owned(project_id: str, db: AsyncSession, user: Any) -> str | None:
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
    unit_types: list[str] | None = None
    zone_code: str | None = None
    # DXF 내보내기 도면종류 — 평면(floor_plan)/상세(detail)/단면(section)/입면(elevation)/배치(site).
    # 미전달 시 floor_plan(기존 동작 보존 — 하위호환).
    drawing_type: str = "floor_plan"


class SubmissionBundleRequest(DrawingSetRequest):
    """WP-F 심의·인허가 제출 번들 생성 요청 — 도면 파라미터(상속) + 발행일·축척·포함옵션.

    ★무목업: issue_date(발행일)는 서버 now()가 아니라 '요청 파라미터'로만 받는다. 미상 시 표제란 공란.
    """
    issue_date: str | None = Field(
        None, description="발행일(YYYY-MM-DD 등) — 명시 인자. 미상 시 표제란 공란(now() 금지)",
    )
    scale: str = Field("N.T.S.", description="도면 축척 표기(예: 1:100). 미상 시 N.T.S.")
    include_dxf: bool = Field(True, description="필수시트 DXF 동봉 여부(부가물 — 없어도 SVG로 필수시트 충족)")
    include_report: bool = Field(True, description="설계요약 보고서 PDF 동봉 여부")
    include_boq: bool = Field(True, description="공내역서(BOQ) xlsx 동봉 여부")
    households: int | None = Field(
        None, ge=0, description="세대수(BOQ 세대당 원단위 — 미상 시 연면적 원단위만)",
    )


class CADSaveRequest(BaseModel):
    """도면 저장 요청. 편집된 CAD 좌표(points/lines/surfaces)를 영속화한다."""
    drawing_code: str = "CAD-EDIT"
    drawing_type: str = "평면도"
    drawing_name: str | None = None
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
    floor_count: int | None = None
    building_height_m: float | None = None
    # 편집본 매스치수(폴리곤 bbox 역산값) — _load_mass_from_design_version이 GLB/해석에 소비.
    # 미전달 시 None(저장 JSON에 미기록 → 로드 시 합리적 기본값 폴백, 하위호환).
    building_width_m: float | None = None
    building_depth_m: float | None = None
    floor_height_m: float | None = None
    # ★WP-E R1(무낙관잠금 봉합·If-Match 의미론): 저장 직전 사용자가 '내가 본 최신 버전'을 함께
    #   보내면, 서버 현재 최신 버전과 다를 때(다른 사람이 그새 저장) 409로 거부한다(무음 덮어쓰기
    #   금지 = lost-update 방지). 미전달(None)이면 기존 동작(항상 MAX+1) 유지 — 점진 도입·하위호환.
    expected_version: int | None = None


class PhotorealRenderRequest(BaseModel):
    """AI 포토리얼 렌더 요청 — 3D 뷰포트 캡처 이미지를 사실적 외관 이미지로 변환.

    image_base64: 3D 화면 캡처(순수 base64 또는 data URI 모두 허용).
    style: 주간|야간|실사(기본 실사).
    strength: 0~1, 구조(깊이/윤곽) 보존 강도(기본 0.6).
    """
    image_base64: str = Field(..., min_length=1)
    style: str = Field("실사")
    strength: float = Field(0.6, ge=0.0, le=1.0)
    # 렌더 프로바이더 선택(선택형) — None이면 서버 기본(replicate ControlNet) 유지(후방호환).
    provider: str | None = None   # "openai" | "google" | "replicate"
    # 모델 ID 선택 — None이면 프로바이더 기본 모델 사용.
    model: str | None = None


class ConceptRenderRequest(BaseModel):
    """컨셉 조감도/투시도 요청 — 텍스트만으로 컨셉 이미지를 생성(text2img).

    3D 모델이 없거나 컨셉 이미지가 필요할 때 사용한다(설명만으로 조감도/투시도 생성).

    prompt: 건물·부지·분위기 설명(프론트가 건물 컨텍스트를 합성해 보낸다).
    view: aerial(조감도) | perspective(투시도) | street(거리뷰). 기본 aerial.
    provider: 이미지 프로바이더 선택(선택형). None이면 서버가 가용분 중 택1.
    model: 모델 ID 선택. None이면 프로바이더 기본 모델.
    """
    prompt: str = Field(..., min_length=1)
    # ★view는 허용값만(Literal) — 오타/잘못된 값은 422로 정직 거부(조용히 aerial로 바뀌지 않음).
    view: Literal["aerial", "perspective", "street"] = "aerial"
    provider: str | None = None          # "openai" | "google" | "replicate"
    model: str | None = None


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
    # ★B1(설계자동분석엔진 SSOT 관통) — 부지분석 실효 한도(%). 지자체 도시계획조례·계획상한을
    #   반영한 min(법정, 조례, 목표) 클램프는 엔진(AutoDesignEngineService._effective_limits)이
    #   담당한다(라우터는 그대로 전달만 — seed-design(mass_templates.py)과 동일 패턴). 미제공 시
    #   None=법정상한 기준(기존 동작 100% 불변 — 하위호환).
    ordinance_far_pct: float | None = Field(None, gt=0, description="부지분석 SSOT 실효 용적률(%)")
    ordinance_bcr_pct: float | None = Field(None, gt=0, le=100, description="부지분석 SSOT 실효 건폐율(%)")
    # ★WP-U2a(실효FAR 근거 정직 전파·additive): ordinance_far_pct가 far_tier SSOT
    #   (calc_effective_far) 산출 실효치일 때 그 산정 근거 라벨(예 "구조상한(건폐율×층수)")과
    #   신뢰 플래그. 수치 산출에는 무영향 — 산출물 메타(rule_trace·applied_limits)로만 전파.
    far_basis: str | None = Field(None, description="실효 용적률 산정 근거(far_tier SSOT far_basis)")
    far_reliable: bool | None = Field(None, description="실효 용적률 SSOT 산정 성공 여부(정직 표기)")
    # ★B2(특이부지 게이트 전 경로 패리티) — 있으면 학교용지·GB·농지·산지·맹지 등 특이요인을 검사해
    #   응답에 경고만 additive 부착(차단 아님). 컨텍스트가 전혀 없으면 게이트 자체를 생략한다
    #   (정직 — 무날조). pnu는 현재 판정에 쓰이지 않고 추적용 메타로 echo만 된다.
    pnu: str | None = Field(None, description="필지 PNU(특이부지 게이트 참고 메타)")
    land_category: str | None = Field(None, description="지목(예: 학교용지·전·답·임야) — 특이부지 게이트 입력")
    special_districts: list[str] | None = Field(
        None, description="특별구역(개발제한구역·문화재·군사·상수원 등) — 특이부지 게이트 입력",
    )


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
    # WP-F(additive): 시트 매니페스트(번호·이름·포맷·sha256·필수·존재) — 기존 필드 무회귀.
    sheet_manifest: list[dict[str, Any]] = Field(default_factory=list)


class DrawingSaveResponse(BaseModel):
    """도면 저장 결과."""
    project_id: str
    drawing_code: str
    drawing_type: str
    svg_length: int
    layer_count: int
    status: str
    # ★후속④(design-run 승인 흐름 표면화): 저장 시 design_run이 실제 영속되면 그 실키(run_id)와
    #   승인차원 status(DRAFT/APPROVED)를 additive 동봉한다. 프론트는 이 run_id로
    #   POST /design-runs/{run_id}/approve(명시 인간승인)를 호출해 승인 흐름을 표면화한다.
    #   미영속(매스치수 부재로 스킵/영속 실패) 시 None(정직) — 기존 응답 필드는 무변경(하위호환).
    design_run: dict[str, Any] | None = None


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

def _inject_unit_mix(
    project_data: dict[str, Any], *, building_use: str, unit_types: list[str] | None
) -> None:
    """실제 세대믹스(AutoDesignEngine)를 산출해 project_data['units']에 주입(데이터 있으면).

    generate-full-set·submission-bundle 공용 헬퍼 — 기준층 평면도를 실제 세대분할로 그리기 위함.
    산출 실패(엔진 미배포·입력 부족 등)는 조용히 통과(generic 균등분할 폴백 — 기존 동작 보존·무회귀).
    """
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
        core_layout = svc.compute_core_layout(mass, building_use)
        unit_layout = svc.compute_unit_layout(
            mass, core_layout, unit_types or ["59A", "84A"], building_use,
        )
        project_data["units"] = unit_layout.get("units")
    except Exception:  # noqa: BLE001 — 산출 실패해도 generic 분할로 도면 생성
        pass


@router.post("/{project_id}/generate-full-set", response_model=FullDrawingSetResponse)
async def generate_full_drawing_set(project_id: str, req: DrawingSetRequest):
    """전체 도면 세트를 일괄 생성한다 (B-01~C-03).

    building_use·unit_types가 주어지면 AutoDesignEngine으로 실제 평형믹스(세대배치)를
    산출해 기준층 평면도를 실제 세대 분할로 그린다(미전달 시 generic 균등분할 폴백).
    """
    project_data = req.model_dump()
    _inject_unit_mix(
        project_data, building_use=req.building_use, unit_types=req.unit_types
    )

    drawings = svg_service.generate_full_drawing_set(project_data)
    return {
        "project_id": project_id,
        "drawings": {code: {"svg_length": len(svg), "has_content": bool(svg)}
                     for code, svg in drawings.items()},
        "drawing_count": len(drawings),
        # WP-F(additive): 시트 매니페스트 — 기존 drawings/drawing_count 필드는 불변.
        "sheet_manifest": build_sheet_manifest(drawings),
    }


def _parse_mix_param(mix: str | None, floor_count: int) -> list[dict[str, Any]] | None:
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
    unit_types: str | None = Query(None, description="쉼표구분 평형(예: 59A,84A)"),
    mix: str | None = Query(None, description="세대믹스 명시(P4 슬라이더): 'type:area:total' 쉼표구분(예: 59A:59:20,84A:84:20)"),
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
    land_area_sqm: float | None = None
    sale_price_per_pyeong_won: float | None = None    # 원/평(F1 시세 전달 권장)
    official_price_per_sqm: float | None = None        # 공시지가 원/㎡(토지비)
    price_multiplier: float = 1.2                          # 감정가 배율
    build_cost_per_sqm: int | None = None              # 직접공사비 단가 원/㎡(override)
    # 편집본 건축면적(㎡) — 전달 시 폭×깊이 대신 이 값으로 연면적·전용면적 산정(CAD 편집 정합).
    # 미전달 시 building_width_m×building_depth_m(기존 동작, 하위호환).
    footprint_sqm: float | None = Field(None, gt=0)


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

        # ★WP-E R1(무낙관잠금 레이스 봉합): 같은 프로젝트+design_type의 동시 저장을 트랜잭션
        #   advisory lock으로 직렬화한다(analysis_ledger append 선례 재사용). 이 락이 없으면
        #   두 요청이 같은 MAX(version)을 읽어 같은 next_ver를 이중 발번하는 lost-update가 난다.
        #   락은 커밋/롤백 시 자동 해제(프로세스 스코프·신규 스키마 0).
        #   ★권고③(64bit 상향): hashtext(::int4→bigint 캐스트)는 32bit라 서로 다른 키가 같은
        #     락으로 뭉칠 충돌 확률이 크다 → hashtextextended(키, 0)의 64bit 해시가 목표(신키).
        #   ★분리 리뷰 MEDIUM(전환기 레이스 봉합): 배포는 블루그린이라 신·구 파드가 잠시 혼재한다
        #     (WORKTREES.md·safe-deploy). 이 전환창 동안 구파드는 여전히 구키(32bit hashtext)로만
        #     잠그므로, 신키만 쓰면 신파드끼리는 직렬화돼도 신-구 파드 간에는 서로 다른 락 공간이라
        #     상호배제가 깨진다(레이스 재발). 그래서 과도기엔 **두 키 모두** 고정 순서(구키 먼저)로
        #     연속 획득한다 — 구키가 최소공통분모라 신·구 파드가 뒤섞여도 구키에서 만나 직렬화된다.
        #     신키는 32bit보다 넓은 공간으로 오탐충돌만 줄인다(있으면 더 안전, 없어도 구키가 방어).
        #     ★순서 고정 이유(데드락 방지): 두 세션이 반대 순서로 락을 걸면 상호대기(deadlock)가
        #     날 수 있다 — 항상 구키→신키 순서만 쓰면 원형대기가 성립하지 않는다.
        #     ★차기 릴리스에서 구키(hashtext) 획득 제거 예정(신키 단독 운영 — 전체 파드가 신키
        #     배포분으로 롤아웃 완료된 뒤). version_number 유니크 제약(DB 레벨 이중방어)은 WP-M
        #     (alembic 헤드 병합) 이후 별도 alembic 마이그레이션으로 다룬다 — 이 WP는 애플리케이션
        #     레벨 직렬화(advisory lock)만 담당하고 스키마 변경은 하지 않는다(제약 준수).
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lk)::bigint)"),  # 구키(32bit) — 먼저.
            {"lk": f"design_versions:{pid}:cad_2d"},
        )
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lk, 0))"),  # 신키(64bit) — 다음.
            {"lk": f"design_versions:{pid}:cad_2d"},
        )
        # 현재 최대 버전 (raw — ORM 컬럼 불일치 우회)
        ver_row = (await db.execute(
            text("SELECT COALESCE(MAX(version_number),0) FROM design_versions "
                 "WHERE project_id = :pid AND design_type = 'cad_2d'"),
            {"pid": str(pid)},
        )).first()
        current_ver = int(ver_row[0]) if ver_row else 0
        # ★If-Match 의미론(하위호환): expected_version이 오면 서버 현재 최신과 대조해 불일치 시
        #   409로 거부한다(무음 덮어쓰기 금지). 미제공(None)이면 기존 동작(항상 MAX+1) 유지.
        if req.expected_version is not None and req.expected_version != current_ver:
            await db.rollback()  # advisory lock 즉시 해제(다른 대기 저장이 지연되지 않게).
            raise HTTPException(
                status_code=409,
                detail=(f"버전 충돌: expected_version={req.expected_version}이(가) 현재 최신 "
                        f"버전({current_ver})과 다릅니다. 최신본을 다시 불러온 뒤 저장하세요."),
            )
        next_ver = current_ver + 1

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
        # ★WP-D 세션3(additive·raw SQL·스키마 불변): 완전한 매스(폭·깊이·층수 3필드)가 있으면
        #   design_data_json 내부에 BimIR provenance 스탬프를 함께 저장한다. 신규 컬럼 없음 —
        #   JSON 내부 additive 키 'bimir'만 추가한다(기존 스키마·저장본 shape 불변). 저장값은
        #   4-스칼라 정체(bimir_version·element_count·design_input_hash·run_id)뿐이며, 전체 BimIR
        #   직렬화(대용량·현 소비처 없음)는 세션4 잔여로 남긴다(write-path 기아 방지). design_input_hash는
        #   provenance compute_input_hash와 동일 계약이라, 이 행을 재현·중복제거·병합의 결정적 앵커로 쓴다.
        if (
            req.building_width_m is not None
            and req.building_depth_m is not None
            and req.floor_count is not None
        ):
            try:
                from app.services.bim.ifc_to_gltf_service import bimir_meta_from_mass

                _stamp_mass: dict[str, Any] = {
                    "building_width_m": req.building_width_m,
                    "building_depth_m": req.building_depth_m,
                    "num_floors": req.floor_count,
                }
                # floor_height_m은 None이면 키를 넣지 않는다(어댑터 기본 3.0 적용 — float(None) 크래시 회피).
                if req.floor_height_m is not None:
                    _stamp_mass["floor_height_m"] = req.floor_height_m
                design_payload["bimir"] = bimir_meta_from_mass(_stamp_mass)
            except Exception:  # noqa: BLE001 — 스탬프 실패가 저장을 막지 않는다(예외격리)
                pass
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

        # ★WP-E: design_run 영속(DRAFT) — 도면 커밋 후 별도 best-effort 트랜잭션으로 설계 실행의
        #   통일 앵커(bare 기하)·표면해시(save_stamp)·기하해시를 design_runs에 기록한다. 완전한
        #   매스(폭·깊이·층수)가 있을 때만 기록하고, 실패해도 이미 커밋된 도면은 안전하다(예외격리).
        design_run_info: dict[str, Any] | None = None
        if (
            req.building_width_m is not None
            and req.building_depth_m is not None
            and req.floor_count is not None
        ):
            with contextlib.suppress(Exception):  # 영속 실패가 저장 응답을 막지 않음(예외격리).
                from app.services.cad import design_run_store

                _stamp = design_payload.get("bimir") if isinstance(design_payload.get("bimir"), dict) else {}
                _run = await design_run_store.persist_design_run(
                    db=db, tenant_id=str(tenant_id), project_id=str(pid),
                    building_width_m=req.building_width_m, building_depth_m=req.building_depth_m,
                    num_floors=req.floor_count, floor_height_m=req.floor_height_m,
                    surface="save_stamp", surface_hash=(_stamp or {}).get("design_input_hash"),
                    compiler_version=(_stamp or {}).get("bimir_version"),
                    metrics={"floor_count": req.floor_count, "building_height_m": req.building_height_m},
                )
                # ★후속④: persist_design_run 반환 계약(design_run_store.py:318-324 — run_id·status 등)의
                #   실키(run_id)·승인차원 status만 응답에 additive 동봉한다. 프론트가 이 run_id로
                #   /design-runs/{run_id}/approve(인간승인)를 호출해 승인 흐름을 표면화한다. run_id가
                #   있을 때만 세팅(없으면 None 유지 — 정직). status는 신규 DRAFT 또는 보존된 기존 승인.
                if isinstance(_run, dict) and _run.get("run_id"):
                    design_run_info = {"run_id": _run["run_id"], "status": _run.get("status")}
        return {
            "project_id": project_id, "drawing_code": req.drawing_code,
            "drawing_type": req.drawing_type, "svg_length": len(req.svg_content),
            "layer_count": len(req.layers), "status": f"saved(v{next_ver})",
            "design_run": design_run_info,
        }
    except HTTPException:
        # ★409(버전 충돌) 등 의도된 HTTP 응답은 아래 generic 핸들러가 500으로 변환하지 않도록
        #   먼저 그대로 전파한다(HTTPException도 Exception 하위형이므로 순서가 중요).
        raise
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


# WP-F: 필수시트(sheet_frame.required_sheet_codes) → DXF 생성기 매핑. export_dxf 위의
# dtype 분기와 동일 서비스 호출(재발명 금지) — 시트코드별로 알맞은 도면종류만 뽑아 쓴다.
def _dxf_bytes_for_sheet(cad_service: Any, code: str, req: SubmissionBundleRequest) -> bytes | None:
    """시트 코드(B-01 등) → 해당 DXF bytes. 미지원 코드는 None(정직 — SVG만 번들에 포함)."""
    if code == "B-01":
        return cad_service.create_site_plan_dxf(
            site_width_m=req.site_width_m, site_depth_m=req.site_depth_m,
            building_width_m=req.building_width_m, building_depth_m=req.building_depth_m,
            parking_count=req.parking_count,
        )
    if code == "B-02-STD":
        return cad_service.create_detailed_floor_plan_dxf(
            building_width_m=req.building_width_m, building_depth_m=req.building_depth_m,
            floor_count=req.floor_count, unit_width_m=req.unit_width_m,
        )
    if code == "B-03":
        return cad_service.create_section_drawing_dxf(
            building_width_m=req.building_width_m, building_depth_m=req.building_depth_m,
            floor_count=req.floor_count, floor_height_m=req.floor_height_m,
            basement_floors=req.basement_floors,
        )
    if code == "B-04-F":
        return cad_service.create_elevation_drawing_dxf(
            building_width_m=req.building_width_m, building_depth_m=req.building_depth_m,
            floor_count=req.floor_count, floor_height_m=req.floor_height_m,
            unit_width_m=req.unit_width_m, view="front",
        )
    if code == "B-04-S":
        return cad_service.create_elevation_drawing_dxf(
            building_width_m=req.building_width_m, building_depth_m=req.building_depth_m,
            floor_count=req.floor_count, floor_height_m=req.floor_height_m,
            unit_width_m=req.unit_width_m, view="side",
        )
    return None


def _build_submission_report_model(
    project_id: str, req: SubmissionBundleRequest, *, run_id: str | None,
) -> Any:
    """제출 번들 동봉용 설계요약 보고서 ReportModel 조립(산식 계산 0 — 기하 입력값 그대로 표기).

    ★재사용: report.render 정본 모델·렌더러(PDF)를 그대로 쓴다(신규 PDF 라이브러리 0).
    """
    from app.services.report.render.model import KVTableBlock, ReportMeta, ReportModel, Section

    overview = Section(section_no=1, title="설계 개요", blocks=[
        KVTableBlock(rows=[
            ("프로젝트", req.project_name),
            ("대지폭(m)", req.site_width_m),
            ("대지깊이(m)", req.site_depth_m),
            ("건물폭(m)", req.building_width_m),
            ("건물깊이(m)", req.building_depth_m),
            ("층수", req.floor_count),
            ("지하층수", req.basement_floors),
            ("층고(m)", req.floor_height_m),
            ("주차대수", req.parking_count),
            ("용도지역", req.zone_code),
            ("건물용도", req.building_use),
        ]),
    ])
    provenance = Section(section_no=2, title="근거", blocks=[
        KVTableBlock(rows=[("run_id", run_id), ("축척", req.scale), ("발행일", req.issue_date)]),
    ])
    return ReportModel(
        meta=ReportMeta(
            title="설계 제출 번들 — 설계요약 보고서",
            project_address=req.project_name,
            doc_no=project_id,
            generated_at=req.issue_date or None,  # ★now() 금지 — 명시 인자만(미상 시 정직 공란)
        ),
        sections=[overview, provenance],
    )


@router.post("/{project_id}/submission-bundle", response_class=Response)
async def generate_submission_bundle(
    project_id: str,
    req: SubmissionBundleRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """심의·인허가 제출 번들(zip)을 생성한다 — 도면(SVG/DXF)+보고서 PDF+BOQ xlsx 단일 zip.

    도면틀(타이틀블록)을 모든 시트에 additive로 씌우고, 필수시트(sheet_frame 표준) 100%
    충족을 강제한다 — 미충족 시 422 + 누락 목록(무음 부분산출 금지). 매니페스트(파일별
    sha256·run_id/input_hash)는 zip 내부 manifest.json 에 동봉(전수 대조 가능).
    인증 필수(무인증 401) + 프로젝트 tenant 소유권 검사(불일치 403 — 비UUID/데모는 검사 생략).

    ★WP-L Idempotency-Key: 같은 키+같은 요청이면 재생성 없이 처음 zip을 그대로 재생(재전송 안전).
      같은 키인데 다른 요청이면 422(키 오사용). 산출은 결정적이라(now()/uuid 0) 캐시본과 동치.
    """
    await _assert_project_owned(project_id, db, user)

    project_data = req.model_dump()
    _inject_unit_mix(project_data, building_use=req.building_use, unit_types=req.unit_types)

    # ── provenance(결정적) — 요청 입력 그대로에서 파생. now()/uuid 미사용. ──
    input_hash = compute_input_hash(project_data)
    run_id = make_run_id(input_hash)

    # ── WP-L 멱등 재생 판정(키 있을 때만) ──
    # ★request_hash는 산출물에 영향을 주는 요청 필드 전체를 반영해야 한다. input_hash(=기하 앵커
    #   compute_input_hash)는 표제란 cosmetic(축척·발행일)을 제외하므로, scale/issue_date만 다른
    #   요청이 같은 키로 오면 낡은 표제란 zip이 재생된다(리뷰 MEDIUM). 명시 편입해 봉합.
    _bundle_req_hash = idempotency.compute_request_hash(
        {"input_hash": input_hash, "scale": req.scale, "issue_date": req.issue_date or ""}
    )
    _idem_tenant = str(getattr(user, "tenant_id", "") or "") or None
    _idem_key = idempotency.normalize_key(idempotency_key)
    if _idem_key:
        _look = await idempotency.lookup(
            db=db, key=_idem_key, tenant_id=_idem_tenant,
            endpoint="submission-bundle", request_hash=_bundle_req_hash,
        )
        if _look.state == idempotency.STATE_CONFLICT:
            raise HTTPException(
                status_code=422,
                detail="같은 Idempotency-Key가 다른 요청에 재사용되었습니다.",
            )
        if _look.state == idempotency.STATE_REPLAY and _look.stored is not None:
            _replay = _look.stored.to_response()
            if _replay is not None:
                return _replay  # 처음 zip 그대로 재생(재생성 0)

    # ── 1) 도면 SVG 산출 + 표제란(additive) 부착 ──
    raw_drawings = svg_service.generate_full_drawing_set(project_data)
    tb_scale, tb_date = req.scale, (req.issue_date or "")
    drawings_svg: dict[str, str] = {}
    for code, svg in raw_drawings.items():
        if not svg:
            continue
        content_hash = sha256_hex(svg)  # 프레임 전 순수 도면 콘텐츠 지문(표제란 표기용)
        tb = build_title_block(
            code, project_name=req.project_name, scale=tb_scale,
            issue_date=tb_date, content_hash=content_hash,
        )
        drawings_svg[code] = apply_title_block_svg(svg, tb)

    # ── 2) DXF(옵션) — 필수시트만 부가로 생성 + 표제란 부착(실패해도 SVG로 필수시트는 충족) ──
    drawings_dxf: dict[str, bytes] = {}
    if req.include_dxf:
        try:
            from app.services.cad.parametric_cad_service import ParametricCADService

            cad_service = ParametricCADService()
            for code in required_sheet_codes():
                if not raw_drawings.get(code):
                    continue
                dxf_bytes = _dxf_bytes_for_sheet(cad_service, code, req)
                if not dxf_bytes:
                    continue
                tb = build_title_block(
                    code, project_name=req.project_name, scale=tb_scale, issue_date=tb_date,
                    content_hash=sha256_hex(raw_drawings[code]),
                )
                drawings_dxf[code] = apply_title_block_dxf(dxf_bytes, tb)
        except Exception as exc:  # noqa: BLE001 — DXF는 부가물(SVG로 필수시트 이미 충족):
            # ezdxf 미설치(ImportError)뿐 아니라 특정 시트 치수 조합에서의 예상 밖 예외까지 폭넓게
            # 흡수해, 부가 산출물 실패가 번들 전체를 500으로 끌고 내려가지 않게 한다(무음은 아님 —
            # 원인을 반드시 로깅). 필수시트는 이미 SVG로 충족돼 있으므로 산출 거부 사유가 아니다.
            logger.warning("submission_bundle_dxf_generation_failed", project_id=project_id, error=str(exc))

    # ── 3) 보고서 PDF(옵션) — ReportModel 정본 렌더러 재사용(산식 계산 0) ──
    report_pdf: bytes | None = None
    if req.include_report:
        from app.services.report.render import render_report

        model = _build_submission_report_model(project_id, req, run_id=run_id)
        report_pdf, _mime, _ext = render_report(model, "pdf")

    # ── 4) BOQ xlsx(옵션) — boq_parametric_engine(초안) → boq_excel_export(엑셀), 재사용 ──
    boq_xlsx: bytes | None = None
    if req.include_boq:
        from app.services.cost.boq_excel_export import build_xlsx
        from app.services.cost.boq_parametric_engine import generate_draft

        gfa = req.building_width_m * req.building_depth_m * req.floor_count
        draft = generate_draft({"gfa_sqm": gfa, "households": req.households})
        boq_xlsx = build_xlsx(draft, priced=False)

    # ── 5) 번들 컴파일 — 필수시트 미충족 시 RequiredSheetsMissingError(422 정직 거부) ──
    try:
        zip_bytes, _manifest = build_submission_bundle(
            project_id=project_id,
            project_name=req.project_name,
            issue_date=tb_date,
            drawings_svg=drawings_svg,
            drawings_dxf=drawings_dxf,
            report_pdf=report_pdf,
            boq_xlsx=boq_xlsx,
            provenance={"run_id": run_id, "input_hash": input_hash},
        )
    except RequiredSheetsMissingError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": "필수시트 미충족 — 산출 거부", "missing": exc.missing},
        ) from exc

    # ── WP-L: 성공 zip을 키로 기억(다음 재전송이 재생성 없이 이 바이트를 재생) ──
    if _idem_key:
        await idempotency.save(
            db=db, key=_idem_key, tenant_id=_idem_tenant, endpoint="submission-bundle",
            request_hash=_bundle_req_hash, response_status=200, body=zip_bytes,
            media_type="application/zip", run_id=run_id,
        )

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={project_id}_submission_bundle.zip"},
    )


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

    # ★공용 콘텐츠 검증(WP-H 세션2 전역 스윕·fail-closed) — 파싱 전에 실행/스크립트 위장·
    # MIME 위장·경로순회·폴리글랏 압축폭탄을 차단한다. ★expected_kinds 미지정(CSV/parcel_excel과
    # 동일 정책 — WP-H 세션2 CI 회귀 수정): DXF는 강한 매직바이트가 없는 텍스트 포맷이라
    # (ASCII DXF는 "0\nSECTION" 류 휴리스틱만 존재) 정상 파일도 매직판별 실패로 415 과대거부될
    # 수 있다. 형식 판정은 다운스트림 parse_dxf_to_shapes(파서, 손상 시 422)가 맡고, 여기서는
    # exe/스크립트·활성콘텐츠·경로순회·압축폭탄만 차단한다(형식 화이트리스트 생략, 그 외 방어 동일).
    from app.services.security.content_inspection import http_status_for, inspect_upload

    _verdict = inspect_upload(data, filename, file.content_type)
    if not _verdict.allowed:
        raise HTTPException(
            status_code=http_status_for(_verdict.code),
            detail=f"업로드가 거부되었습니다: {_verdict.reason}",
        )

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


def _attach_special_parcel_gate(mass: dict[str, Any], req: BimGenerateRequest) -> dict[str, Any]:
    """특이부지 게이트(B2) additive 부착 — 학교용지·GB·농지·산지·맹지 등 경고만 부착(차단 아님).

    req에 land_category·special_districts 컨텍스트가 있을 때만 판정하고, 없으면
    mass["special_parcel"]=None(정직 생략 — 무날조). _resolve_mass_uncached의 3분기(명시치수·
    자동산출·최종폴백) 공용 — 매스 SSOT(compliance와 같은 자리)에 부착되므로 /mass·/bim·/layout
    응답이 자동으로 동봉한다(proposals 경로의 _detect_special과 동일 원천 재사용 — 전역패리티).
    """
    from app.services.zoning.special_parcel_gate import build_special_parcel_gate

    # LayoutRequest는 zone_name(한글 용도지역명)을 추가로 갖는다 — 있으면 우선(더 정확한 zone_type).
    zone_type = getattr(req, "zone_name", None) or req.zone_code
    mass["special_parcel"] = build_special_parcel_gate(
        land_category=req.land_category,
        zone_type=zone_type,
        special_districts=req.special_districts,
        area_sqm=req.land_area_sqm,
        pnu=req.pnu,
    )
    # ── WP-B: 개발행위허가 절차게이트(국토계획법 §56~58) additive 부착 ──
    #   설계생성 진입점(매스 SSOT)에도 개발행위허가 대상 여부·기준을 동봉해, 녹지·비도시 부지가
    #   허가 판정 없이 설계로 진행되던 과대낙관을 봉합한다(build_special_parcel_gate와 동일 패턴·
    #   실패 graceful None). zone_name(한글명)이 있으면 우선(더 정확한 용도지역).
    try:
        from app.services.permit.dev_act_permit_gate import build_dev_act_permit_gate

        mass["dev_act_permit_gate"] = build_dev_act_permit_gate(
            zone_type=zone_type,
            land_category=req.land_category,
            area_sqm=req.land_area_sqm,
            special_districts=req.special_districts,
            pnu=req.pnu,
        )
    except Exception:  # noqa: BLE001 — 게이트 실패가 매스 산출(주 경로)을 깨면 안 됨(best-effort)
        mass["dev_act_permit_gate"] = None

    # ── WP-A: 접도·도로 기반(P4) access_basis additive 부착 ──
    #   설계생성 진입점(매스 SSOT)에도 접도 판정(legal/physical/emergency 3상태)을 동봉한다.
    #   이 진입점엔 도로 실데이터(road_side·road_contact 등)가 없어 대부분 정직하게 미확정
    #   (REQUIRES_AUTHORITY_CONFIRMATION)으로 응답하지만, build_dev_act_permit_gate와 동일하게
    #   실패는 graceful None으로 흡수한다(best-effort, 주 경로 무손상).
    try:
        from app.services.access.access_basis_service import build_access_basis_gate

        mass["access_basis"] = build_access_basis_gate(
            zone_type=zone_type,
            land_category=req.land_category,
            special_districts=req.special_districts,
            pnu=req.pnu,
        )
    except Exception:  # noqa: BLE001 — 게이트 실패가 매스 산출(주 경로)을 깨면 안 됨(best-effort)
        mass["access_basis"] = None

    # ── WP-G: 부지기반(P7) 게이트 스냅샷 additive 부착 ──
    #   설계생성 진입점(매스 SSOT)에 P0 자동판정을 자동 결선한다. access_status는 위 access_basis
    #   (권위 서비스 실산출값)를 그대로 넘긴다 — dev_act_status와 동일하게 caller 자기신고가 아닌
    #   server_derived 신뢰경계다. basis_status는 항상 ADVISORY로 고정된다(AUTHORIZED는
    #   /api/v1/basis/{run_id}/approve 인간승인 API 전용 — 이 자동경로에서는 절대 도달하지 않는다).
    try:
        from app.services.basis.site_basis_service import gate_design_entry

        dev_act_status = (mass.get("dev_act_permit_gate") or {}).get("status")
        access_status = (mass.get("access_basis") or {}).get("status")
        mass["site_basis_gate"] = gate_design_entry(
            dev_act_status=dev_act_status, access_status=access_status,
        )
    except Exception:  # noqa: BLE001 — 게이트 실패가 매스 산출(주 경로)을 깨면 안 됨(best-effort)
        mass["site_basis_gate"] = None
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
      - ordinance_far_pct·ordinance_bcr_pct(B1): 자동산출 분기 SiteInput에 주입돼 _effective_limits의
        min(법정,조례,목표) 클램프 결과(far_pct·bcr_pct·num_floors 등)를 바꾼다 — 누락 시 조례값만
        다른 요청이 같은 캐시열쇠로 충돌해 잘못된 매스를 돌려주는 캐시오염 버그가 된다.
      - land_category·special_districts·pnu(B2): _attach_special_parcel_gate가 부착하는
        mass["special_parcel"](developability·warnings)을 바꾼다 — 같은 이유로 누락 시 캐시오염.
      - zone_name(B2·★독립리뷰 CRITICAL 반영): _attach_special_parcel_gate가 zone_type으로
        zone_name을 zone_code보다 우선 소비하므로 special_parcel 결과를 바꾼다 — 누락 시
        zone_name만 다른 요청이 같은 캐시열쇠로 충돌해 **다른 부지의 특이부지 경고가 새어
        나가는** 크로스 캐시오염(캐시는 전역 단일 인스턴스·테넌트 무관)이 된다.

    제외(비결정·결과 무영향): project_name(IFC 라벨일 뿐 매스 기하 불변), 그리고 LayoutRequest가
      추가로 받는 나머지 필드(avg_unit_area_sqm·site_geometry·llm_adjust)는 _resolve_mass가
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
        # ★B1: 부지분석 실효 한도(조례) — 자동산출 분기의 min(법정,조례,목표) 클램프 결과에 영향.
        "ordinance_far_pct": req.ordinance_far_pct,
        "ordinance_bcr_pct": req.ordinance_bcr_pct,
        # ★WP-U2a: 실효 근거 메타 — build_mass_contract의 rule_trace(basis 문구·far_basis 키)가
        #   캐시되는 mass 안에 실리므로, 누락 시 근거만 다른 요청이 같은 열쇠로 충돌해 남의 근거
        #   문구를 돌려주는 캐시오염이 된다(ordinance_*와 동일 이유).
        "far_basis": req.far_basis,
        "far_reliable": req.far_reliable,
        # ★B2: 특이부지 게이트 입력 — mass["special_parcel"](경고)에 영향.
        "land_category": req.land_category,
        "special_districts": sorted(req.special_districts) if req.special_districts else None,
        "pnu": req.pnu,
        # ★B2(독립리뷰 CRITICAL): 게이트가 zone_name을 zone_code보다 우선 소비 — 결과를 바꾸는 입력.
        "zone_name": getattr(req, "zone_name", None),
    }


def _attach_design_basis(mass: dict[str, Any], req: BimGenerateRequest) -> None:
    """★WP-E 세션2(P9 Program·Constraint 정형화) — options를 DesignBasis로 파싱해 매스에 부착.

    무엇을(쉬운 설명): 흩어진 options(building_use·unit_types·zone_code·목표한도)를 정형 스키마
      (program_items + hard/soft 제약)로 승격하고, 산출된 매스 지표(far_pct·bcr_pct·높이·층수)로
      hard(법정·물리)/soft(선호) 제약을 판정해 결과를 mass에 additive로 붙인다:
        mass["design_basis"]      = 정형 계약(프로그램·제약)
        mass["basis_evaluation"]  = 판정 결과(satisfied·unsat_reasons·soft_warnings·unevaluated)
      hard 위반(unsat_reasons)이 있으면 무음으로 넘기지 않고 구조화 사유를 남긴다(Unsat Core 최소사상).

    ★무회귀(additive·폴백 유지): 이 함수는 mass에 키를 추가만 한다 — 기존 키·산출을 바꾸지 않는다.
      임계값·지표가 없으면 그 제약은 unevaluated로 정직 표기(근거 없는 거부 금지). 이 함수의 어떤
      실패도 매스 산출(주 경로)을 깨지 않는다(예외격리 — 미부착=기존 options dict 경로 유지·폴백).
    ★실제 산출 거부는 대표 소비처(generate_bim_model)가 settings.DESIGN_BASIS_ENFORCE=True일 때만 한다.
    """
    try:
        from app.services.cad.auto_design_engine import AutoDesignEngineService
        from app.services.cad.design_basis import (
            build_design_basis_from_options,
            extract_metrics_from_mass,
        )

        # 법정 한도는 정본(get_legal_limits)에서만 받는다(무날조 — 임계값 날조 금지).
        legal = AutoDesignEngineService.get_legal_limits(req.zone_code)
        basis = build_design_basis_from_options(
            building_use=req.building_use,
            unit_types=req.unit_types,
            legal_limits=legal,
            # 조례 실효 한도(있을 때만)를 선호(soft) 목표로 넘긴다 — 위반해도 경고만(기존 동작 불변).
            target_far_percent=req.ordinance_far_pct,
            target_bcr_percent=req.ordinance_bcr_pct,
        )
        evaluation = basis.evaluate(extract_metrics_from_mass(mass))
        mass["design_basis"] = basis.model_dump(mode="json")
        mass["basis_evaluation"] = evaluation.model_dump(mode="json")
        if evaluation.unsat_reasons:  # 무음 퇴화 금지 — hard 위반은 로그로도 남긴다.
            import structlog

            structlog.get_logger().warning(
                "design_basis hard 위반",
                zone=req.zone_code, use=req.building_use,
                codes=[u.constraint_code for u in evaluation.unsat_reasons],
                enforce=_design_basis_enforce_enabled(),
            )
    except Exception:  # noqa: BLE001 — DesignBasis 부착 실패가 매스 산출을 막지 않음(폴백=기존 경로).
        pass


def _design_basis_enforce_enabled() -> bool:
    """DesignBasis hard 위반 시 산출 거부를 실제로 강제할지(기본 False=그림자·무회귀)."""
    try:
        from app.core.config import settings

        return bool(getattr(settings, "DESIGN_BASIS_ENFORCE", False))
    except Exception:  # noqa: BLE001
        return False


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
    #   ★DesignBasis 부착(WP-E)은 _resolve_mass_uncached(정본 빌더) 내부에서 하므로 여기선 손대지
    #     않는다 — 캐시/무캐시 결과가 완전히 동일하게 유지된다(cache 투명성 계약·무회귀).
    mass = _resolve_mass_uncached(req)
    design_run_cache.put(key, copy.deepcopy(mass))
    mass["_cache_hit"] = False
    return mass


def _resolve_mass_uncached(req: BimGenerateRequest) -> dict[str, Any]:
    """요청에서 건축 매스를 확정한다. 매스 직접입력 우선, 없으면 대지정보로 자동산출.

    확정된 매스에 실내 요소(코어·복도·창호)를 _enrich_interior로 보강하고,
    C2R 계약(envelope_result·geometry_invariants·rule_trace)+DesignBasis(WP-E 정형 프로그램·제약)를
    부착한다(전 분기 공용·additive).

    ★이 함수는 _resolve_mass(캐시 래퍼)가 호출한다. 결정적 부착이라 캐시/무캐시 결과가 100% 동일하다.
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
        # ★특이부지 게이트(B2) additive 부착 — 이 분기는 조례 실효한도(B1) 적용 대상이 아니다
        #   (SiteInput/법정한도 자체를 안 쓰는 명시치수 분기이므로 조례 클램프가 개입할 여지가 없음).
        _attach_special_parcel_gate(mass, req)
        _attach_design_basis(mass, req)  # ★WP-E 정형 근거 부착(대표 소비경로·additive·예외격리).
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
            # ★B1(설계자동분석엔진 SSOT 관통) — 부지분석 실효 한도(%). seed-design(mass_templates.py
            #   :203-213)과 동일 패턴으로 SiteInput에 그대로 전달한다. 엔진의 _effective_limits가
            #   이미 min(법정,조례,목표) 클램프를 수행하므로 여기서는 전달만(엔진 수정 불필요).
            #   미제공(None) 시 클램프 미적용=법정상한 기준(기존 동작 100% 불변).
            ordinance_far_percent=req.ordinance_far_pct,
            ordinance_bcr_percent=req.ordinance_bcr_pct,
            # ★WP-U2a: 실효 근거 메타(있을 때만 값) — rule_trace·applied_limits로 정직 전파.
            far_basis=req.far_basis,
            far_reliable=req.far_reliable,
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
        # ★특이부지 게이트(B2) additive 부착 — 학교용지·GB·농지·산지·맹지 등 경고만(차단 아님).
        _attach_special_parcel_gate(mass, req)
        _attach_design_basis(mass, req)  # ★WP-E 정형 근거 부착 — 이 분기는 far/bcr 지표가 있어 법정 hard 실평가.
        return mass
    # 최종 폴백: 합리적 기본값
    mass = {
        "building_width_m": 12.0, "building_depth_m": 9.0,
        "num_floors": req.floor_count or 5, "floor_height_m": req.floor_height_m,
    }
    mass = _enrich_interior(mass)
    # ★C2R 계약 부착(공용 헬퍼) — 폴백 분기도 site/legal 없음 → envelope_result+geometry_invariants만(무날조).
    _attach_mass_contract(mass, req)
    # ★특이부지 게이트(B2) additive 부착 — 폴백 분기도 컨텍스트가 있으면 동일하게 판정(전 경로 패리티).
    _attach_special_parcel_gate(mass, req)
    _attach_design_basis(mass, req)  # ★WP-E 정형 근거 부착(전 경로 패리티·additive·예외격리).
    return mass


@router.post("/{project_id}/bim/generate")
async def generate_bim_model(project_id: str, req: BimGenerateRequest):
    """3D BIM(IFC) 모델을 생성하고 요약 메타 + AI 설계해석을 반환한다.

    ★무거운계산 캐시(INC6-b·시간/LLM비용 절감): 이 엔드포인트는 한 번에 ~56초가 걸린다 —
      대부분 DesignInterpreter(Claude LLM, 6섹션)와 build_ifc_from_mass(1.5MB IFC)다.
      이 무거운 계산 묶음(ai_interpretation + ifc 바이트수)은 '설계입력에 대해 결정적'이다:
      입력 = {mass, zone_code, building_use, units_data}, units_data도 mass에서 결정된다.
      그러므로 동일 설계입력 반복 시 input_hash를 열쇠로 보관해두면 LLM/IFC 재계산을 통째로 생략한다.

    ★정확성(캐시 안 하는 것): project_id(경로)·glb_url(project_id 임베드)·mass(round)·compliance는
      요청마다 신선하게 새로 만든다(절대 캐시 공유 금지). 캐시값은 설계입력 결정 부분(해석/세대/ifc길이)만.
      → 다른 프로젝트가 같은 설계입력을 보내도 응답의 project_id/glb_url은 각자 신선(오염 0).
    """
    from app.services.bim.ifc_generator_service import build_ifc_from_mass

    mass = _resolve_mass(req)

    # ★WP-E 하드게이트(대표 소비처): DesignBasis hard(법정·물리) 위반이면 무음 퇴화 대신 산출을
    #   거부하고 구조화 Unsat 사유를 반환한다(계획서 게이트 "Hard 위반 산출 0"). 기본 shadow
    #   (DESIGN_BASIS_ENFORCE=False)에서는 거부하지 않는다(무회귀 — 위반 사유는 mass에 부착만).
    #   ★견고화: "is False" 대신 "is not True"로 비교한다 — 부착이 부분 손상돼 satisfied 키가
    #     None/누락이면(정상 True/False가 아니면) ENFORCE 모드에서는 "판정불명=미충족"으로 보수
    #     처리해 거부한다(무음 통과 방지). shadow(기본값)에서는 이 분기 자체가 평가되지 않는다.
    _eval = mass.get("basis_evaluation") if isinstance(mass, dict) else None
    if (
        _design_basis_enforce_enabled()
        and isinstance(_eval, dict)
        and _eval.get("satisfied") is not True
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": "DesignBasis hard 제약 위반으로 설계 산출을 거부합니다(무음 퇴화 금지).",
                "unsat_reasons": _eval.get("unsat_reasons", []),
                "soft_warnings": _eval.get("soft_warnings", []),
            },
        )

    # ── 무거운계산 캐시 열쇠: mass캐시와 같은 결정적 핑거프린트지만 "bim:" prefix로 네임스페이스 분리 ──
    #   (mass캐시 값은 매스 dict, bim캐시 값은 해석/ifc길이 묶음 — 같은 열쇠로 섞이면 안 되므로 prefix).
    # ★왜 bim_key에만 project_name = ifc_bytes(IFC 바이트수)가 project_name(IFC 라벨)에 의존하므로,
    #   무거운계산 캐시는 project_name까지 열쇠에 넣어 결정성을 지킨다.
    #   매스 캐시는 기하만이라 project_name 무관(그대로 — _request_fingerprint는 안 건드림).
    bim_fp = {**_request_fingerprint(req), "project_name": req.project_name}
    bim_key = "bim:" + compute_input_hash(bim_fp)
    cached_bim = design_run_cache.get(bim_key)

    if cached_bim is not None:
        # 히트: 깊은 복사본에서 무거운계산 결과만 꺼낸다(IFC빌드·core/unit layout·DesignInterpreter 전부 생략).
        payload = copy.deepcopy(cached_bim)
        ai_interpretation = payload.get("ai_interpretation")
        ifc_len = int(payload.get("ifc_len", 0))
        bim_cache_hit = True
    else:
        # 미스: 기존 흐름 그대로 무거운 계산을 수행한 뒤, clean 깊은 복사본을 캐시에 저장한다.
        ifc_bytes = build_ifc_from_mass(mass, project_name=req.project_name)
        ifc_len = len(ifc_bytes)

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
            # ★R1 R2(근원 봉합): BaseInterpreter._invoke가 이제 폴백-only 결과를 빈 dict로 강등하므로
            #   (base_interpreter.py, is_fallback_only SSOT) interp는 이미 안전하다. 아래 재판정은
            #   이중 방어(무해·삭제 불필요) — design_ingest/orchestrator.py._interpret_proposal과 동일 판정.
            from app.services.ai.base_interpreter import is_fallback_only

            if isinstance(interp, dict) and interp and not is_fallback_only(interp, DesignInterpreter.fallback_key):
                ai_interpretation = interp
        except Exception as e:  # noqa: BLE001
            import structlog

            structlog.get_logger().warning("설계 AI 해석 스킵", error=str(e)[:120])

        # 무거운계산 묶음을 깊은 복사본으로 저장(양방향 격리·INC6과 동일 패턴).
        #   ★해석 None(LLM 키없음/실패)도 그대로 캐시 → 다음에도 일관(무날조). 키가 생기면 배포 재시작으로 자동무효화.
        #   ★units_data는 저장 안 함 = 히트 경로에서 다시 읽지 않고 응답에도 없으므로(죽은 페이로드)
        #     deepcopy 비용·메모리를 아낀다.
        design_run_cache.put(bim_key, copy.deepcopy({
            "ai_interpretation": ai_interpretation,
            "ifc_len": ifc_len,
        }))
        bim_cache_hit = False

    # ★WP-D 세션3(additive): BimIR 정체·provenance 메타 부착 — glb_url이 가리키는 산출물의
    #   BimIR 정체(bimir_version·element_count·design_input_hash·run_id)를 JSON에도 표기한다.
    #   mass는 항상 신선 산출(캐시 히트여도 위에서 재해석)이라 메타도 신선하다. 순수 계산
    #   (ifcopenshell 불필요)이라 캐시 밖에서 저렴하게 산출. 실패해도 모델은 정상 반환(예외격리).
    bimir_meta: dict[str, Any] | None
    try:
        from app.services.bim.ifc_to_gltf_service import bimir_meta_from_mass

        bimir_meta = bimir_meta_from_mass(mass)
    except Exception as e:  # noqa: BLE001
        import structlog

        structlog.get_logger().warning("BimIR 메타 산출 스킵", error=str(e)[:120])
        bimir_meta = None

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
        "ifc_bytes": ifc_len,
        "glb_url": f"/api/v1/design/{project_id}/bim/model.glb",
        # ★C2R 계약 동봉(additive) — _resolve_mass가 부착한 envelope_result·geometry_invariants·rule_trace.
        "compliance": mass.get("compliance"),
        # ★특이부지 게이트 동봉(additive·B2) — _resolve_mass가 부착한 학교용지·GB·농지·산지 등 경고
        #   (developability·warnings·legal_refs). 컨텍스트 없으면 None(정직 생략).
        "special_parcel": mass.get("special_parcel"),
        # ★캐시 적중 표기(additive·무날조) — /bim의 cached는 '무거운계산(LLM/IFC) 캐시 적중'을 의미한다
        #   (mass._cache_hit이 아님). 동일 설계입력 2회째면 LLM/IFC를 생략하고 캐시값을 즉시 반환(True).
        "cached": bim_cache_hit,
        # ★BimIR 정체·provenance(additive·세션3) — bimir_version·element_count·design_input_hash·run_id.
        #   design_input_hash는 provenance compute_input_hash와 동일 계약(이중 해시 발산 방지). 산출 불가 시 None.
        "bimir": bimir_meta,
        # ★DesignBasis 판정 동봉(additive·생성허브 100%) — _attach_design_basis 가 mass 내부에만 부착하던
        #   basis_evaluation(unsat_reasons·soft_warnings)을 응답에 직렬화한다. 종전엔 어떤 응답에도 실리지
        #   않아 "법규 적합성" 판정 근거가 프론트에서 보이지 않았다(WP-E 완결 자산 미표면). 미산출=None(정직).
        "basis_evaluation": mass.get("basis_evaluation"),
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
        # ★특이부지 게이트 동봉(additive·B2) — 학교용지·GB·농지·산지 등 경고(컨텍스트 없으면 None).
        "special_parcel": mass.get("special_parcel"),
        # ★캐시 적중 표기(additive·무날조) — 동일 요청 2회째면 캐시 즉시반환(True). 라이브 검증용.
        "cached": bool(mass.get("_cache_hit")),
    }


@router.post("/{project_id}/bim/model.glb", response_class=Response)
async def get_bim_glb(project_id: str, req: BimGenerateRequest):
    """3D BIM 모델을 glTF binary(.glb)로 반환한다 — 프론트 useGLTF가 직접 로드.

    ★WP-D 세션3 배선: glb 산출을 BimIR 경유(bimir_from_mass→build_gltf_from_bimir)로 흐르게 하되,
      실패 시 기존 직접 경로로 폴백한다(공용 헬퍼 glb_from_mass_with_bimir·무회귀). BimIR 정체/
      provenance는 응답 헤더(X-BIMIR-*)로 additive 표기한다(glb 바이트는 불변).
    """
    from app.services.bim.ifc_to_gltf_service import (
        bimir_meta_to_headers,
        glb_from_mass_with_bimir,
    )

    mass = _resolve_mass(req)
    try:
        glb, bimir_meta = glb_from_mass_with_bimir(mass, project_name=req.project_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"BIM 모델 생성 실패: {str(e)[:120]}") from e
    return Response(
        content=glb,
        media_type="model/gltf-binary",
        headers={
            "Content-Disposition": f"inline; filename={project_id}.glb",
            **bimir_meta_to_headers(bimir_meta),
        },
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
    from app.services.bim.ifc_to_gltf_service import (
        bimir_meta_to_headers,
        glb_from_mass_with_bimir,
    )

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

    # ★WP-D 세션3 배선: glb 산출을 BimIR 경유로(실패 시 직접 경로 폴백·공용 헬퍼). 무회귀.
    try:
        glb, bimir_meta = glb_from_mass_with_bimir(mass, project_name=project_name)
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
            **bimir_meta_to_headers(bimir_meta),  # BimIR 정체·provenance(additive)
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
        req.image_base64,
        style=req.style,
        strength=req.strength,
        provider=req.provider,
        model=req.model,
    )

    # 키 미설정/실패는 그대로 정직 반환(과금 없음).
    if result.get("status") != "ok":
        return result

    # 렌더 성공 시에만 사용료 차감(로그인 사용자일 때만; best-effort — 실패해도 결과 제공).
    # ★프로바이더 무관 동일 과금코드(photoreal_render) — INC2는 단일 코드(신규 과금 추가 금지).
    charged = None
    if user is not None:
        try:
            await billing_service.load_config(db)
            c = await billing_service.charge_service(db, user.id, "photoreal_render")
            charged = c.get("charged_krw")
        except Exception:  # noqa: BLE001
            pass

    # 프로바이더별 성공 반환형이 다르다(replicate=image_url / openai·google=image_base64).
    # 둘 중 있는 것을 그대로 전달(소비처는 image_base64 우선, 없으면 image_url 사용).
    return {
        "status": "ok",
        "image_url": result.get("image_url"),
        "image_base64": result.get("image_base64"),
        "provider": result.get("provider"),
        "model": result.get("model"),
        "message": "비파괴 렌더(원본 3D 불변)",
        "charged": charged,
    }


@router.post("/{project_id}/render-concept")
async def render_concept(
    project_id: str,
    req: ConceptRenderRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    """텍스트→컨셉 조감도/투시도(text2img). 3D가 없어도 설명만으로 컨셉 이미지 생성.

    정직 처리:
    - 이미지 프로바이더 키/SDK 미설정 → status="no_key"(에러 아님, 200). 가짜 이미지 절대 금지.
    - 외부 호출 실패/빈 결과 → status="error"(사유 안내). 성공 시에만 과금.
    - 과금코드 concept_render는 관리자 미설정 시 무료(미설정무료 정책).
    """
    from app.services.billing import billing_service
    from app.services.drawing import photoreal_render_service

    result = await photoreal_render_service.render_concept(
        req.prompt,
        view=req.view,
        provider=req.provider,
        model=req.model,
    )

    # 키 미설정/실패는 그대로 정직 반환(과금 없음).
    if result.get("status") != "ok":
        return result

    # 생성 성공 시에만 사용료 차감(로그인 사용자일 때만; best-effort — 실패해도 결과 제공).
    # ★concept_render 과금코드 — 관리자 미설정 시 0원=무료(미설정무료 정책).
    charged = None
    if user is not None:
        try:
            await billing_service.load_config(db)
            c = await billing_service.charge_service(db, user.id, "concept_render")
            charged = c.get("charged_krw")
        except Exception:  # noqa: BLE001
            pass

    # 프로바이더별 성공 반환형이 다르다(replicate=image_url / openai·google=image_base64).
    # 둘 중 있는 것을 그대로 전달(소비처는 image_base64 우선, 없으면 image_url 사용).
    return {
        "status": "ok",
        "image_url": result.get("image_url"),
        "image_base64": result.get("image_base64"),
        "provider": result.get("provider"),
        "model": result.get("model"),
        "view": result.get("view"),
        "message": "컨셉 렌더(text2img)",
        "charged": charged,
    }


@router.get("/image-providers")
async def list_image_providers():
    """프론트 드롭다운용 — 라이브 가용(키+SDK 있는) 이미지 프로바이더만 노출(반쪽출하 방지).

    인증 불요(시크릿 없음·가용목록만). 경로: GET /api/v1/design/image-providers.
    """
    from app.services.ai.image_provider import get_available_image_providers

    return {"providers": get_available_image_providers()}


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
        # ★B1 교정 — 기존 하드코딩 None(조례 미반영)이던 것을 req의 부지분석 실효 한도로 교체.
        #   미제공 시 여전히 None(기존 동작 100% 불변) — 제공 시에만 site_context_from_zone이
        #   법정상한보다 우선 적용(조례가 법정을 넘으면 내부에서 법정으로 클램프·가짜 상향 없음).
        ordinance_far_pct=req.ordinance_far_pct, ordinance_bcr_pct=req.ordinance_bcr_pct,
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
        # ★특이부지 게이트 동봉(additive·B2) — 학교용지·GB·농지·산지 등 경고(컨텍스트 없으면 None).
        "special_parcel": mass.get("special_parcel"),
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
