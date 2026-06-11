"""도면 자동 생성 라우터.

프론트엔드 CAD 컴포넌트가 호출하는 /api/v1/drawing/* 엔드포인트를 제공한다.
app/services/drawing, app/services/cad 서비스를 활용한다.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

# 진짜 비용유발(LLM 호출) 엔드포인트만 로그인 필수 — 현재는 parse_intent(자연어→의도).
# 도면/설계 산출(auto_design·design_alternatives·design_operate·site/floor_plan)은 순수 결정론
# 계산(SLSQP·룰)으로 LLM 비용이 없고, 스튜디오의 /design/* 생성과 동일하게 무인증 허용해야
# 일관적(로그인 만료/게스트에서도 스튜디오 설계 생성이 동작). 외부 남용은 레이트리밋 계층에서 차단.
from apps.api.auth.jwt_handler import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# ── 자연어 의도 → 평형(UNIT_TYPES) 매핑 (CAD Phase 2) ──
# auto_design_engine.UNIT_TYPES 키 기준. 원룸=초소형, 투룸=소형, 쓰리룸=중형.
_MIX_TO_UNIT_TYPES: dict[str, str] = {
    "원룸": "39A",
    "투룸": "59A",
    "쓰리룸": "84A",
}
# priority(수익/거주/균형)별 기본 평형 조합 — 3개 차별화 대안의 기준.
_PRIORITY_UNIT_TYPES: dict[str, list[str]] = {
    "yield": ["39A", "49A"],        # 수익형: 소형 다세대
    "livability": ["84A", "114A"],  # 거주형: 중대형 여유
    "balanced": ["59A", "84A"],     # 균형형
}

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
    daylight_north: bool = Field(False, description="정북일조 단계후퇴(북측 채광) 적용")


class AutoDesignRequest(BaseModel):
    """단일 AI 자동 설계 생성 요청 (CAD Phase 2)."""

    site_area_sqm: float = Field(..., gt=0, description="대지면적 (㎡)")
    site_shape: Optional[list[dict[str, float]]] = Field(None, description="대지 형상 좌표 [{x,y}]")
    site_width_m: float = Field(0.0, ge=0, description="대지 폭 (m, 0이면 자동)")
    site_depth_m: float = Field(0.0, ge=0, description="대지 깊이 (m, 0이면 자동)")
    zone_code: str = Field("2R", description="용도지역 코드 (1R/2R/3R/GC/NC/QI/QR)")
    building_use: str = Field("공동주택", description="건축물 용도")
    target_unit_types: list[str] = Field(default=["84A"], description="세대 유형")
    floor_height_m: float = Field(3.0, gt=2.0, description="기본 층고 (m)")
    setback_m: dict[str, float] = Field(
        default={"north": 3.0, "south": 2.0, "east": 1.5, "west": 1.5},
        description="세트백 거리 (m)",
    )
    daylight_north: bool = Field(False, description="정북일조 단계후퇴(북측 채광) 적용 — 상부 층 북측 자동 후퇴")


class ParseIntentRequest(BaseModel):
    """자연어 설계 의도 파싱 요청 (CAD Phase 2)."""

    text: str = Field(..., description="자연어 설계 의도 (예: '원룸 위주 50세대 수익 최대')")
    site_area_sqm: Optional[float] = Field(None, gt=0, description="대지면적 (㎡, 선택)")
    zone_code: Optional[str] = Field(None, description="용도지역 코드 (선택)")


class CalculateAreaRequest(BaseModel):
    """폴리곤 면적 계산 요청 (CADEditor 편집 좌표 → 면적·건폐율)."""

    points: list[dict[str, float]] = Field(..., description="점 목록 [{id, x, y}]")
    surfaces: list[dict] = Field(..., description="폴리곤 목록 [{id, pointIds}]")
    scale: float = Field(10.0, gt=0, description="1m = N px")
    site_area_sqm: float = Field(0.0, ge=0, description="대지면적 (㎡)")


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


@router.post("/calculate-area")
async def calculate_area(req: CalculateAreaRequest):
    """DesignPayload(편집 좌표)에서 폴리곤별 면적 + 건폐율을 계산한다.

    순수 Shoelace 기하 계산(서비스 의존성 없음)이라 _check_services 불요.
    surfaces 항목은 pointIds(camelCase) 또는 point_ids(snake_case) 모두 허용한다.
    """
    point_map = {p["id"]: (p["x"], p["y"]) for p in req.points if "id" in p}
    results = []
    total_area_sqm = 0.0

    for surf in req.surfaces:
        pid_list = surf.get("pointIds") or surf.get("point_ids") or []
        coords = [point_map[pid] for pid in pid_list if pid in point_map]
        if len(coords) < 3:
            continue
        # Shoelace
        area_px = 0.0
        for i in range(len(coords)):
            j = (i + 1) % len(coords)
            area_px += coords[i][0] * coords[j][1]
            area_px -= coords[j][0] * coords[i][1]
        area_px = abs(area_px) / 2.0
        area_sqm = area_px / (req.scale * req.scale)
        total_area_sqm += area_sqm
        results.append({
            "surface_id": surf.get("id", ""),
            "area_sqm": round(area_sqm, 2),
            "area_pyeong": round(area_sqm / 3.3058, 2),
        })

    bcr_pct = round(total_area_sqm / req.site_area_sqm * 100, 2) if req.site_area_sqm > 0 else 0.0

    return {
        "surfaces": results,
        "total_area_sqm": round(total_area_sqm, 2),
        "total_area_pyeong": round(total_area_sqm / 3.3058, 2),
        "bcr_percent": bcr_pct,
    }


# priority별 평형 후보·수요편향 — 대안마다 평형배분이 실제로 달라지게 한다.
# yield(수익형): 소형 다세대 / livability(거주형): 중대형 / balanced(균형): 전체.
_PRIORITY_MIX_PROFILE: dict[str, dict] = {
    "yield": {
        "enabled_types": ["S39", "S49", "S59", "S74"],
        "demand_ratio": {"S39": 0.30, "S49": 0.30, "S59": 0.25, "S74": 0.15},
    },
    "livability": {
        "enabled_types": ["S74", "S84", "S102", "S135"],
        "demand_ratio": {"S74": 0.20, "S84": 0.35, "S102": 0.30, "S135": 0.15},
    },
    "balanced": {
        "enabled_types": None,  # 전체 평형
        "demand_ratio": None,   # 기본 시장수요
    },
}


def _unit_mix_for(summary: dict, priority: str = "balanced", region: str = "서울") -> dict:
    """대안의 연면적·법규로 유닛믹스(평형배분)를 최적화한다(검증된 SLSQP 엔진 재사용).

    auto_design_engine이 산출한 평형은 단순 균등배분이라, 수익 관점의 정밀
    평형배분(어떤 평형을 몇 세대)은 unit_mix_optimizer로 보강한다.
    priority별 평형 후보·수요편향을 달리해 대안마다 배분이 실제로 달라진다.
    실패 시 빈 dict.
    """
    try:
        from app.services.feasibility.unit_mix_optimizer import (
            UnitMixInput,
            UnitMixOptimizer,
        )

        gfa = float(summary.get("total_floor_area_sqm") or 0)
        if gfa <= 0:
            return {}
        profile = _PRIORITY_MIX_PROFILE.get(priority, _PRIORITY_MIX_PROFILE["balanced"])
        result = UnitMixOptimizer().optimize(
            UnitMixInput(
                total_gfa_sqm=gfa,
                max_far_pct=float(summary.get("far_percent") or 250),
                max_bcr_pct=float(summary.get("max_bcr_pct") or 60),
                region=region,
                enabled_types=profile["enabled_types"],
                demand_ratio=profile["demand_ratio"],
            )
        )
        # 라우터 응답엔 핵심만 노출.
        # 주의: optimizer_total_units는 GFA만으로 수익을 극대화한 '이론적' 평형배분
        # 세대수다(코어·복도·주차 차감 전). 실제 buildable 세대수는 summary.total_units.
        # 프론트는 distribution(비율)을 평형 추천으로 쓰고, 카운트는 summary를 신뢰.
        units = result.get("units", [])
        distribution = [
            {
                "code": u.get("code"),
                "name": u.get("name"),
                "area_sqm": u.get("area_sqm"),
                "ratio_pct": u.get("ratio_pct"),
            }
            for u in units
        ]
        return {
            "method": result.get("method"),
            "optimizer_total_units": result.get("total_units"),
            "total_revenue_100m": result.get("total_revenue_100m"),
            "gfa_efficiency_pct": result.get("gfa_efficiency_pct"),
            "distribution": distribution,  # 평형별 비율(추천) — 카운트는 summary 신뢰
            "units": units,                # 최적화 상세(이론적 세대수 포함)
        }
    except Exception as e:  # noqa: BLE001 — 보강 실패해도 기본 설계는 유효
        logger.warning("유닛믹스 최적화 보강 실패: %s", e)
        return {}


def _score_alternative(
    summary: dict, compliance: dict, legal: dict, priority: str = "balanced",
) -> float:
    """대안 점수(0~100). 우선순위(수익/거주/균형)에 따라 가중치를 달리한다.

    - 법규 위반 시 큰 감점(준수가 최우선).
    - yield: 세대수·용적률 활용도 가중.
    - livability: 세대당 면적·낮은 건폐율 가중.
    - balanced: 두 축 균형.
    legal: get_legal_limits 결과(max_far_percent/max_bcr_percent) — 활용도 분모.
    """
    far = float(summary.get("far_percent") or 0)
    max_far = float(legal.get("max_far_percent") or far or 1)
    units = int(summary.get("total_units") or 0)
    gfa = float(summary.get("total_floor_area_sqm") or 0)
    bcr = float(summary.get("bcr_percent") or 0)
    max_bcr = float(legal.get("max_bcr_percent") or bcr or 1)

    far_util = min(far / max_far, 1.0) if max_far > 0 else 0.0  # 용적률 활용도 0~1
    area_per_unit = (gfa / units) if units > 0 else 0.0
    livability = min(area_per_unit / 85.0, 1.0)  # 세대당 85㎡ 기준 0~1
    bcr_openness = 1.0 - min(bcr / max_bcr, 1.0) if max_bcr > 0 else 0.0  # 낮을수록 쾌적

    if priority == "yield":
        base = far_util * 0.6 + min(units / 100.0, 1.0) * 0.4
    elif priority == "livability":
        base = livability * 0.6 + bcr_openness * 0.4
    else:  # balanced
        base = far_util * 0.4 + livability * 0.4 + bcr_openness * 0.2

    score = base * 100.0
    if not compliance.get("all_pass", False):
        score -= 40.0  # 법규 미준수 강한 감점
    return round(max(0.0, min(100.0, score)), 1)


@router.post("/design-alternatives")
async def design_alternatives(req: DesignAlternativesRequest):
    """수익형/거주형/균형형 3개 대안을 생성·점수화·정렬하여 비교한다.

    각 대안은 평형배분(유닛믹스)이 다르며, 법규 준수 여부(all_pass)와 점수(score)를
    포함한다. 법규 위반 대안은 명시되며 정렬 시 후순위로 밀린다.
    """
    _check_services()
    site_input = SiteInput(
        site_area_sqm=req.site_area_sqm,
        zone_code=req.zone_code,
        building_use=req.building_use,
        target_unit_types=req.target_unit_types,
        floor_height_m=req.floor_height_m,
        setback_m=req.setback_m,
        daylight_step=req.daylight_north,
    )
    results = auto_design_engine.generate_alternatives(site_input, count=req.count)
    legal = auto_design_engine.get_legal_limits(req.zone_code)

    # 대안별 우선순위(엔진 생성 순서: A=균형, B=수익(소형), C=거주(중대형)).
    priorities = ["balanced", "yield", "livability"]

    alternatives: list[dict] = []
    for idx, r in enumerate(results):
        priority = priorities[idx] if idx < len(priorities) else "balanced"
        unit_mix = _unit_mix_for(r.summary, priority)
        score = _score_alternative(r.summary, r.compliance, legal, priority)
        alternatives.append({
            "alternative_name": r.summary.get("alternative_name", f"대안 {chr(65 + idx)}"),
            "priority": priority,
            "summary": r.summary,
            "compliance": r.compliance,  # bcr_ok/far_ok/height_ok/setback_ok/all_pass
            "unit_mix": unit_mix,        # 수익 최적 평형배분(SLSQP)
            "design_payload": r.design_payload,
            "score": score,
            "compliant": bool(r.compliance.get("all_pass", False)),
        })

    # 정렬: 법규 준수 대안 우선 → 점수 내림차순.
    alternatives.sort(key=lambda a: (not a["compliant"], -a["score"]))
    for rank, a in enumerate(alternatives, start=1):
        a["rank"] = rank

    return {
        "alternatives": alternatives,
        "recommended_index": 0 if alternatives else None,
    }


@router.post("/auto-design")
async def auto_design(req: AutoDesignRequest):
    """대지면적+법규 기반 단일 AI 자동 설계를 생성한다(CAD Phase 2).

    Phase 1에서 정의됐으나 라이브 미노출(404)이던 엔드포인트를 실 라우터에 추가.
    """
    _check_services()
    site_input = SiteInput(
        site_area_sqm=req.site_area_sqm,
        site_shape=req.site_shape,
        site_width_m=req.site_width_m,
        site_depth_m=req.site_depth_m,
        zone_code=req.zone_code,
        building_use=req.building_use,
        target_unit_types=req.target_unit_types,
        floor_height_m=req.floor_height_m,
        setback_m=req.setback_m,
        daylight_step=req.daylight_north,
    )
    result = auto_design_engine.generate(site_input)
    unit_mix = _unit_mix_for(result.summary)
    return {
        "design_payload": result.design_payload,
        "summary": result.summary,
        "compliance": result.compliance,
        "unit_mix": unit_mix,
        "legal_limits": auto_design_engine.get_legal_limits(req.zone_code),
    }


class DesignOperateRequest(BaseModel):
    """검증형 설계 생성·편집 요청 (CAD P2 — 의도→스펙→커널→근거검증 일원화)."""

    text: str = Field("", description="자연어/음성 설계 의도(빈값=파라미터만)")
    site_area_sqm: float = Field(..., gt=0)
    zone_code: str = Field("2R")
    building_use: str = Field("공동주택")
    floor_height_m: float = Field(3.0, gt=1.5, le=6.0)
    num_floors: Optional[int] = Field(None, ge=1, le=120)
    target_unit_types: list[str] = Field(default=["84A"])
    corridor_width_m: Optional[float] = Field(None)
    priority: str = Field("balanced")
    setback_m: dict[str, float] = Field(
        default={"north": 3.0, "south": 2.0, "east": 1.5, "west": 1.5}
    )


@router.post("/design-operate")
async def design_operate(req: DesignOperateRequest):
    """검증형 설계 생성·편집 (CAD P2).

    자연어/음성 의도 → DesignSpec 결정론 반영 → 커널 생성 → 법규 근거검증.
    화면 수치는 전부 커널 산출값, violations로 법규 위반을 표면화(할루시네이션 차단).
    """
    from app.services.cad.design_spec import DesignSpec, Setback
    from app.services.cad.design_operator import DesignOperator

    sb = req.setback_m or {}
    spec = DesignSpec(
        site_area_sqm=req.site_area_sqm,
        zone_code=req.zone_code,
        building_use=req.building_use,
        floor_height_m=req.floor_height_m,
        num_floors=req.num_floors,
        target_unit_types=req.target_unit_types or ["84A"],
        corridor_width_m=req.corridor_width_m,
        priority=req.priority,
        setback_m=Setback(
            north=sb.get("north", 3.0), south=sb.get("south", 2.0),
            east=sb.get("east", 1.5), west=sb.get("west", 1.5),
        ),
    )
    result = await DesignOperator().operate(req.text, spec)
    result["legal_limits"] = auto_design_engine.get_legal_limits(req.zone_code)
    return result


@router.post("/parse-intent")
async def parse_intent(req: ParseIntentRequest, _user: CurrentUser = Depends(get_current_user)):
    """자연어 설계 의도를 구조화 파라미터로 변환한다(CAD Phase 2).

    LLM(BaseInterpreter 경유, 토큰계측) → 실패 시 규칙기반 폴백.
    반환된 target_unit_types/building_use를 /auto-design에 그대로 넘길 수 있다.
    """
    try:
        from app.services.ai.design_intent_interpreter import DesignIntentInterpreter

        interpreter = DesignIntentInterpreter()
        intent = await interpreter.parse(
            req.text, site_area_sqm=req.site_area_sqm, zone_code=req.zone_code,
        )
    except Exception as e:  # noqa: BLE001 — 의도 파싱 실패는 규칙기반으로 흡수
        logger.warning("의도 파싱 실패, 규칙기반 폴백: %s", e)
        from app.services.ai.design_intent_interpreter import parse_intent_rule_based

        intent = parse_intent_rule_based(req.text)
        intent["source"] = "rule"

    # 의도 → auto_design_engine이 바로 쓰는 target_unit_types로 변환(프론트 편의).
    suggested_types = _intent_to_unit_types(intent)
    intent["suggested_unit_types"] = suggested_types
    return {"intent": intent}


def _intent_to_unit_types(intent: dict) -> list[str]:
    """파싱된 의도 → auto_design_engine.UNIT_TYPES 평형 코드 목록.

    1순위 unit_mix(비율 있는 룸타입), 없으면 priority 기본 조합.
    """
    mix = intent.get("unit_mix")
    if isinstance(mix, dict) and mix:
        types = [
            _MIX_TO_UNIT_TYPES[room]
            for room, ratio in mix.items()
            if room in _MIX_TO_UNIT_TYPES and (ratio or 0) > 0
        ]
        if types:
            return types
    priority = intent.get("priority") or "balanced"
    return _PRIORITY_UNIT_TYPES.get(priority, _PRIORITY_UNIT_TYPES["balanced"])


@router.get("/legal-limits")
async def legal_limits(
    zone_code: str = Query("2R", description="용도지역 코드 (1R/2R/3R/GC/NC/QI/QR)"),
):
    """용도지역의 법정 건폐율·용적률·높이 상한을 반환한다(프론트 슬라이더 하드캡용).

    auto_design_engine._LEGAL_LIMITS(ZONE_LIMITS)를 단일 출처로 재사용.
    """
    _check_services()
    limits = auto_design_engine.get_legal_limits(zone_code)
    return {
        "zone_code": zone_code,
        "max_bcr_percent": limits["max_bcr_percent"],
        "max_far_percent": limits["max_far_percent"],
        "max_height_m": limits["max_height_m"],
        "min_setback_m": limits["min_setback_m"],
        "sunlight_hours": limits["sunlight_hours"],
    }
