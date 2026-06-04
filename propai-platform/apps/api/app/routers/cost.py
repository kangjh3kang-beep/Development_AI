"""v61 공사비 라우터 — IFC 물량 + 원가계산 + 몬테카를로 + 기성.

prefix: /api/v1/cost
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.session import get_db

from app.services.cost.origin_cost_calculator import OriginCostCalculator, CostItem
from app.services.cost.cost_monte_carlo import CostMonteCarlo
from app.services.bim.bim_service import BIMService

router = APIRouter(prefix="/api/v1/cost", tags=["v61 공사비"])
cost_calc = OriginCostCalculator()
bim_service = BIMService()

# ── 건축개요 기반 공사비 추정(수지·사업성과 단일 데이터원 연동) ──
_STRUCT_FACTOR = {"RC": 1.0, "RC조": 1.0, "SRC": 1.15, "SRC조": 1.15, "SC": 1.10, "철골": 1.10, "철골조": 1.10, "PC": 0.95, "목구조": 0.85}


class OverviewCostRequest(BaseModel):
    """건축개요(연면적·지상/지하 층수·구조·용도) 기반 공사비 추정 요청."""
    building_type: str = "apartment"
    total_gfa_sqm: float = Field(gt=0)
    floor_count_above: int = Field(1, ge=1)
    floor_count_below: int = Field(0, ge=0)
    structure_type: str = "RC"
    unit_cost_per_sqm: Optional[int] = None  # 직접공사비 단가 override(원/㎡)
    # 기하(geometry) 정밀 적산용 — 설계 매스 치수(있으면 실치수, 없으면 연면적·층수로 역산)
    project_id: Optional[str] = None
    building_width_m: Optional[float] = None
    building_depth_m: Optional[float] = None
    floor_height_m: float = 3.0


async def _resolve_design_mass(db: AsyncSession, project_id: str) -> dict[str, Any] | None:
    """프로젝트 최신 design_versions의 매스 치수(폭·깊이·층수)를 조회(없으면 None)."""
    import uuid as _uuid

    from sqlalchemy import text

    try:
        pid = _uuid.UUID(str(project_id))
    except (ValueError, AttributeError, TypeError):
        return None
    try:
        row = (await db.execute(text(
            "SELECT floor_count, total_floor_area_sqm, design_data_json FROM design_versions "
            "WHERE project_id = :pid ORDER BY version_number DESC LIMIT 1"), {"pid": str(pid)})).first()
        if not row:
            return None
        dj = row[2] or {}
        mass = dj.get("mass") if isinstance(dj, dict) else {}
        mass = mass or {}
        return {
            "building_width_m": mass.get("building_width_m"),
            "building_depth_m": mass.get("building_depth_m"),
            "num_floors": mass.get("num_floors") or row[0],
            "floor_height_m": mass.get("floor_height_m"),
        }
    except Exception:  # noqa: BLE001
        return None


@router.post("/estimate-overview", summary="건축개요 기반 공사비 추정(지상/지하/조경/간접·최저~최대 + 기하 QTO)")
async def estimate_overview(req: OverviewCostRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """선택한 건축개요로 지상·지하·조경 직접공사비 + 간접비(설계·감리·예비·일반관리)를
    산정하고, 건설물가 변동을 반영한 최저~최대 예상 공사비 레인지를 반환한다.
    (도면/BIM 완성 프로젝트는 향후 항목별 정밀 적산으로 대체) — 수지·사업성과 동일 개요 사용."""
    from app.services.feasibility.construction_cost_engine import (
        DEFAULT_DIRECT_COST_PER_SQM, calculate_indirect_cost,
    )
    PY = 3.305785
    base_unit = req.unit_cost_per_sqm or DEFAULT_DIRECT_COST_PER_SQM.get(
        req.building_type, DEFAULT_DIRECT_COST_PER_SQM["apartment"])
    unit = base_unit * _STRUCT_FACTOR.get(req.structure_type, 1.0)
    gfa = req.total_gfa_sqm
    gfa_below = min(gfa * 0.4, gfa * req.floor_count_below * 0.12)  # 지하 면적 추정
    gfa_above = max(0.0, gfa - gfa_below)

    def scenario(factor: float) -> dict[str, Any]:
        u = int(unit * factor)
        above = int(gfa_above * u)
        below = int(gfa_below * u * 1.3)  # 지하 30% 할증
        landscape = int((above + below) * 0.015)  # 조경 1.5%
        direct = above + below + landscape
        ind = calculate_indirect_cost(direct_cost_won=direct)
        total = direct + ind["total_indirect_cost_won"]
        return {
            "unit_cost_per_sqm": u,
            "aboveground_won": above, "underground_won": below, "landscape_won": landscape,
            "direct_won": direct,
            "design_fee_won": ind["design_fee_won"], "supervision_fee_won": ind["supervision_fee_won"],
            "contingency_won": ind["contingency_won"], "general_expense_won": ind["general_expense_won"],
            "indirect_won": ind["total_indirect_cost_won"],
            "total_won": total,
            "per_pyeong_won": int(total / (gfa / PY)) if gfa > 0 else 0,
        }

    expected = scenario(1.0)

    # ── 기하(geometry) 기반 정밀 적산 — 설계 매스 실치수 우선, 없으면 연면적·층수로 역산 ──
    from app.services.cost.geometry_qto import derive_dims_from_gfa, geometry_takeoff
    qto_source = "derived"
    W, Dd, Hh = req.building_width_m, req.building_depth_m, req.floor_height_m
    nf_above = req.floor_count_above
    if req.project_id:
        m = await _resolve_design_mass(db, req.project_id)
        if m and m.get("building_width_m") and m.get("building_depth_m"):
            W, Dd = float(m["building_width_m"]), float(m["building_depth_m"])
            if m.get("num_floors"):
                nf_above = int(m["num_floors"])
            if m.get("floor_height_m"):
                Hh = float(m["floor_height_m"])
            qto_source = "bim"
    if not (W and Dd):
        W, Dd = derive_dims_from_gfa(gfa_above, nf_above)
    geometry = geometry_takeoff(
        width_m=W, depth_m=Dd, floors_above=nf_above, floors_below=req.floor_count_below,
        floor_height_m=Hh, structure_type=req.structure_type,
    )
    geometry["source"] = qto_source

    # 항목별 정밀 적산(QTO) — 레미콘·철근·거푸집·조적·방수·창호·기계·전기(물량×단가).
    # 건축개요(연면적·층수·구조) 기반. 설계/BIM 완성 시 실 매스로 정밀화 가능.
    items_qto: list[dict[str, Any]] = []
    try:
        from app.services.cost.standard_quantity_estimator import StandardQuantityEstimator
        _BT_KR = {"apartment": "공동주택", "officetel": "오피스텔", "office": "근린생활시설",
                  "townhouse": "다세대주택", "single_house": "다세대주택", "warehouse": "근린생활시설"}
        raw = StandardQuantityEstimator().estimate(
            building_type=_BT_KR.get(req.building_type, "공동주택"),
            total_gfa_sqm=gfa, floor_count_above=req.floor_count_above,
            floor_count_below=req.floor_count_below, structure_type=req.structure_type,
        )
        for it in raw:
            unit_sum = float(it.get("mat_unit", 0)) + float(it.get("labor_unit", 0)) + float(it.get("exp_unit", 0))
            items_qto.append({
                "name": it.get("item_name"), "spec": it.get("spec"), "unit": it.get("unit"),
                "quantity": it.get("quantity"), "unit_cost_won": int(unit_sum),
                "cost_won": int(float(it.get("quantity", 0)) * unit_sum),
            })
    except Exception:  # noqa: BLE001
        items_qto = []

    return {
        "building_type": req.building_type, "structure_type": req.structure_type,
        "total_gfa_sqm": gfa, "gfa_above_sqm": round(gfa_above, 1), "gfa_below_sqm": round(gfa_below, 1),
        **expected,
        "range": {
            "min_won": scenario(0.92)["total_won"],
            "expected_won": expected["total_won"],
            "max_won": scenario(1.12)["total_won"],
        },
        "items": items_qto,
        "geometry": geometry,
        "qto_source": qto_source,
        "note": "건축개요 기반 표준 추정(지상/지하/조경/간접) + 기하(geometry) 정밀 적산. 설계 매스(BIM) 있으면 실치수로 자동 정밀화.",
    }


# ── 요청 스키마 ──

class IFCUploadRequest(BaseModel):
    """IFC 업로드 시뮬레이션 (실제는 File 업로드)."""
    elements: list[dict[str, Any]] = Field(
        ..., description="IFC 요소 리스트 [{element_type, quantity, ...}]")


class CostCalculateRequest(BaseModel):
    """원가계산 요청."""
    items: list[dict[str, Any]] = Field(
        ..., description="공사비 항목 리스트")
    rates: Optional[dict[str, float]] = Field(
        None, description="커스텀 법정요율 (None이면 2026 기본)")


class MonteCarloRequest(BaseModel):
    """몬테카를로 시뮬레이션 요청."""
    base_result: dict[str, Any] = Field(
        ..., description="OriginCostCalculator 결과")
    iterations: int = Field(10000, ge=100, le=100000)
    seed: int = Field(42)


class BillingCreateRequest(BaseModel):
    """기성 생성 요청."""
    billing_no: int = Field(..., ge=1)
    period_from: str
    period_to: str
    planned_value: float = Field(0, ge=0)
    earned_value: float = Field(0, ge=0)
    actual_cost: float = Field(0, ge=0)
    work_entries: list[dict[str, Any]] = Field(default_factory=list)


class FeasibilityRequest(BaseModel):
    """원가→수지분석 연동 요청."""
    total_project_cost: float = Field(..., gt=0)
    total_revenue: float = Field(..., gt=0)
    project_months: int = Field(36, ge=1)


# ── 응답 스키마 ──


class IFCUploadResponse(BaseModel):
    """IFC 업로드 결과."""
    project_id: str
    mapped_items: list[dict[str, Any]]
    item_count: int
    unique_work_codes: list[str]


class CostCalculateResponse(BaseModel):
    """원가계산 결과."""
    project_id: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    subtotals: dict[str, Any] = Field(default_factory=dict)
    total: float = 0.0

    # LLM(Claude) 원가 해석 (CostInterpreter, 키 설정 시 채워짐)
    ai_cost_analysis: Optional[str] = None
    ai_ve_suggestions: Optional[str] = None
    ai_material_advice: Optional[str] = None
    ai_schedule_impact: Optional[str] = None
    ai_risk_factors: Optional[str] = None

    class Config:
        extra = "allow"


class MonteCarloResponse(BaseModel):
    """몬테카를로 시뮬레이션 결과."""
    project_id: str
    mean: float = 0.0
    std: float = 0.0
    p10: float = 0.0
    p50: float = 0.0
    p90: float = 0.0

    class Config:
        extra = "allow"


class BillingCreateResponse(BaseModel):
    """기성 생성 결과."""
    project_id: str
    billing_no: int
    period: str
    planned_value: float
    earned_value: float
    actual_cost: float
    evm_spi: float
    evm_cpi: float
    status: str
    work_entries_count: int


class BillingSummaryResponse(BaseModel):
    """누적 기성 현황."""
    project_id: str
    total_billings: int
    cumulative_pv: float
    cumulative_ev: float
    cumulative_ac: float
    overall_spi: float
    overall_cpi: float
    status: str


class FeasibilityResultResponse(BaseModel):
    """수지분석 연동 결과."""
    project_id: str
    total_cost: float
    total_revenue: float
    gross_profit: float
    profit_rate_pct: float
    monthly_return: float
    irr_estimate: float


# ── 엔드포인트 ──

@router.post("/{project_id}/upload-ifc", response_model=IFCUploadResponse)
async def upload_ifc(project_id: str, req: IFCUploadRequest):
    """IFC 파일 업로드 + 공종코드 매핑."""
    mapped = bim_service.extract_quantities_with_work_codes(req.elements)
    return {
        "project_id": project_id,
        "mapped_items": mapped,
        "item_count": len(mapped),
        "unique_work_codes": list({m["work_code"] for m in mapped}),
    }


@router.post("/{project_id}/calculate", response_model=CostCalculateResponse)
async def calculate_cost(project_id: str, req: CostCalculateRequest):
    """원가계산서를 생성한다."""
    result = cost_calc.calculate(req.items, rates=req.rates)

    # LLM(Claude) 원가 해석 — 실패해도 산정 결과는 정상 반환(graceful fallback)
    ai: dict[str, Any] = {}
    try:
        from app.services.ai.cost_interpreter import CostInterpreter

        gfa = sum(float(it.get("quantity", 0) or 0) for it in req.items) or 0
        interp = await CostInterpreter().generate_interpretation({
            "total_cost": result.get("total_project_cost", 0),
            "cost_per_sqm": (
                round(result.get("total_project_cost", 0) / gfa) if gfa else 0
            ),
            "cost_items": [
                {
                    "category": k,
                    "amount": v,
                    "ratio_pct": (
                        round(v / result.get("total_project_cost", 1) * 100, 1)
                        if result.get("total_project_cost")
                        else 0
                    ),
                }
                for k, v in (result.get("category_totals", {}) or {}).items()
            ],
            "cost_breakdown": {
                "material_cost": result.get("direct_material_cost"),
                "labor_cost": result.get("total_labor_cost"),
                "expense_cost": result.get("direct_expense_cost"),
                "overhead_cost": result.get("general_mgmt"),
                "profit": result.get("profit"),
            },
        })
        if isinstance(interp, dict):
            ai = interp
    except Exception:
        ai = {}

    return {
        "project_id": project_id,
        **result,
        "ai_cost_analysis": ai.get("cost_analysis"),
        "ai_ve_suggestions": ai.get("ve_suggestions"),
        "ai_material_advice": ai.get("material_advice"),
        "ai_schedule_impact": ai.get("schedule_impact"),
        "ai_risk_factors": ai.get("risk_factors"),
    }


@router.post("/{project_id}/monte-carlo", response_model=MonteCarloResponse)
async def run_monte_carlo(project_id: str, req: MonteCarloRequest):
    """공사비 몬테카를로 시뮬레이션."""
    mc = CostMonteCarlo(req.base_result, iters=req.iterations, seed=req.seed)
    result = mc.run()
    return {
        "project_id": project_id,
        **result,
    }


@router.post("/{project_id}/billing/create", response_model=BillingCreateResponse)
async def create_billing(project_id: str, req: BillingCreateRequest):
    """기성을 생성한다 (EVM SPI/CPI 자동 산출)."""
    pv = req.planned_value
    ev = req.earned_value
    ac = req.actual_cost

    spi = round(ev / pv, 4) if pv > 0 else 0.0
    cpi = round(ev / ac, 4) if ac > 0 else 0.0

    return {
        "project_id": project_id,
        "billing_no": req.billing_no,
        "period": f"{req.period_from} ~ {req.period_to}",
        "planned_value": pv,
        "earned_value": ev,
        "actual_cost": ac,
        "evm_spi": spi,
        "evm_cpi": cpi,
        "status": "on_track" if spi >= 0.9 and cpi >= 0.9 else "at_risk",
        "work_entries_count": len(req.work_entries),
    }


@router.get("/{project_id}/billing/summary", response_model=BillingSummaryResponse)
async def billing_summary(project_id: str):
    """누적 기성 현황을 반환한다."""
    return {
        "project_id": project_id,
        "total_billings": 0,
        "cumulative_pv": 0,
        "cumulative_ev": 0,
        "cumulative_ac": 0,
        "overall_spi": 1.0,
        "overall_cpi": 1.0,
        "status": "no_data",
    }


@router.post("/{project_id}/feasibility", response_model=FeasibilityResultResponse)
async def cost_to_feasibility(project_id: str, req: FeasibilityRequest):
    """원가계산서→수지분석 연동."""
    profit = req.total_revenue - req.total_project_cost
    profit_rate = round(profit / req.total_revenue * 100, 2) if req.total_revenue > 0 else 0
    monthly_return = round(profit / req.project_months) if req.project_months > 0 else 0

    return {
        "project_id": project_id,
        "total_cost": req.total_project_cost,
        "total_revenue": req.total_revenue,
        "gross_profit": round(profit),
        "profit_rate_pct": profit_rate,
        "monthly_return": monthly_return,
        "irr_estimate": round(profit_rate / req.project_months * 12, 2),
    }


@router.get("/{project_id}/export-excel", response_class=Response)
async def export_excel(project_id: str):
    """원가계산서 샘플을 Excel 파일로 내보낸다."""
    from app.services.export.excel_export_service import ExcelExportService

    # 샘플 데이터로 원가계산서 생성
    sample_items = [
        {"work_code": "A01", "item_name": "철근콘크리트공사", "spec": "24-210-15",
         "unit": "m3", "quantity": 500, "mat_unit": 150000, "labor_unit": 80000, "exp_unit": 20000},
        {"work_code": "A05", "item_name": "창호공사", "spec": "AL 커튼월",
         "unit": "m2", "quantity": 300, "mat_unit": 200000, "labor_unit": 50000, "exp_unit": 10000},
        {"work_code": "E01", "item_name": "전기설비공사", "spec": "일반 전기",
         "unit": "식", "quantity": 1, "mat_unit": 500000000, "labor_unit": 200000000, "exp_unit": 50000000},
    ]
    result = cost_calc.calculate(sample_items)
    rows = cost_calc.to_excel_data(result)

    export_svc = ExcelExportService()
    file_bytes, content_type = export_svc.cost_sheet_to_xlsx(rows)

    ext = "xlsx" if "spreadsheet" in content_type else "csv"
    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="cost_sheet_{project_id}.{ext}"'
        },
    )
