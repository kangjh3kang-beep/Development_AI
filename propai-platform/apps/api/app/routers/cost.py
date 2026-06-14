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

# ── BIM 물량(bim_quantities) 공종코드 → 단가 SSOT(UnitPriceRepository) 키 매핑 ──
# ifc_work_map 의 leaf 코드만 단가에 대응(부모 집계코드 A01/A05 는 미가격 — 중복합산 방지).
# 매핑 없는 코드(기계/전기/마감 등)는 단가 미보유로 0원·priced=false 정직 표기.
_BIM_WORKCODE_TO_PRICE_KEY: dict[str, str] = {
    "A01-01": "formwork",   # 거푸집
    "A01-02": "rebar",      # 철근
    "A01-03": "concrete",   # 콘크리트
    "A02": "concrete",      # 기초공사 → 콘크리트
    "A03": "masonry",       # 조적공사
    "A04": "waterproof",    # 방수공사
    "A05-03": "window",     # 창호프레임
    "A06": "waterproof",    # 지붕공사 → 방수
}


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
    # 지하면적 = 층 바닥판 비례 추정. 지하 바닥판은 주차·기계실로 지상보다 약간 넓어(≈1.2배)
    # footprint×지하층수×1.2 로 잡는다. 기존 min(gfa*0.4, gfa*층수*0.12)은 고층(예 35F/5F)에서도
    # 0.4 cap 에 걸려 지하가 총GFA의 40%(지상의 67%)가 되는 물리적 비현실 → 층수비례로 교정.
    _fa = max(1, int(req.floor_count_above))
    _fb = max(0, int(req.floor_count_below))
    _BK = 1.2  # 지하 바닥판 확장계수
    gfa_below = (gfa * (_fb * _BK) / (_fa + _fb * _BK)) if _fb > 0 else 0.0
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
    unit_price_source = "fallback"
    try:
        from app.services.cost.standard_quantity_estimator import StandardQuantityEstimator

        # 단가 SSOT(UnitPriceRepository) 1회 async 조회 주입 — DB 실패 시 None 폴백
        # (estimator가 기존 동기 fallback resolve로 회귀, 회귀 0).
        unit_prices: dict[str, dict[str, Any]] | None = None
        try:
            from app.services.cost.unit_price_repository import UnitPriceRepository
            unit_prices = await UnitPriceRepository().get_prices()
        except Exception:  # noqa: BLE001
            unit_prices = None
        if unit_prices and any(
            (p or {}).get("price_source") not in (None, "fallback") for p in unit_prices.values()
        ):
            unit_price_source = "db"

        _BT_KR = {"apartment": "공동주택", "officetel": "오피스텔", "office": "근린생활시설",
                  "townhouse": "다세대주택", "single_house": "다세대주택", "warehouse": "근린생활시설"}
        raw = StandardQuantityEstimator().estimate(
            building_type=_BT_KR.get(req.building_type, "공동주택"),
            total_gfa_sqm=gfa, floor_count_above=req.floor_count_above,
            floor_count_below=req.floor_count_below, structure_type=req.structure_type,
            prices=unit_prices,
        )
        for it in raw:
            unit_sum = float(it.get("mat_unit", 0)) + float(it.get("labor_unit", 0)) + float(it.get("exp_unit", 0))
            items_qto.append({
                "name": it.get("item_name"), "spec": it.get("spec"), "unit": it.get("unit"),
                "quantity": it.get("quantity"), "unit_cost_won": int(unit_sum),
                "cost_won": int(float(it.get("quantity", 0)) * unit_sum),
                # 단가 출처 정직 표기(DB 출처명 또는 "fallback") — additive 필드.
                "price_source": it.get("price_source", "fallback"),
                "price_basis_year": it.get("price_basis_year", 2026),
            })
    except Exception:  # noqa: BLE001
        items_qto = []
        unit_price_source = "fallback"

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
        # 항목 단가 출처 요약 — DB 단가 1건 이상 반영 시 "db", 전부 하드코딩 fallback이면 "fallback".
        "unit_price_source": unit_price_source,
        "note": "건축개요 기반 표준 추정(지상/지하/조경/간접) + 기하(geometry) 정밀 적산. 설계 매스(BIM) 있으면 실치수로 자동 정밀화.",
    }


async def _load_bim_quantities(db: AsyncSession, project_id: str) -> list[dict[str, Any]]:
    """프로젝트 bim_quantities 를 공종코드 단위로 합산 조회(없으면 빈 리스트)."""
    import uuid as _uuid

    from sqlalchemy import text

    try:
        pid = _uuid.UUID(str(project_id))
    except (ValueError, AttributeError, TypeError):
        return []
    rows = (await db.execute(text(
        "SELECT work_code, "
        "       COALESCE(MAX(unit), '') AS unit, "
        "       COALESCE(SUM(quantity), 0) AS quantity, "
        "       COUNT(*) AS line_count "
        "FROM bim_quantities WHERE project_id = :pid AND work_code IS NOT NULL "
        "GROUP BY work_code ORDER BY work_code"), {"pid": str(pid)})).mappings().all()
    return [dict(r) for r in rows]


@router.get(
    "/{project_id}/bim-quantities/origin-cost",
    summary="BIM 물량(bim_quantities) + 단가 SSOT → 원가계산 12단계(공종코드 결합·정직성)",
)
async def bim_quantities_origin_cost(
    project_id: str, db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """저장된 BIM 물량을 단가 SSOT와 결합해 OriginCostCalculator 12단계 원가를 산정한다.

    bim_quantities 0건이면 가짜 0원 대신 `status="no_bim_quantities"` 로 정직 응답한다.
    단가 미보유 공종(기계/전기/마감 등)은 0원·priced=false 로 표기(중복합산·허위값 없음)."""
    grouped = await _load_bim_quantities(db, project_id)
    if not grouped:
        # 정직성: 물량 없음 → 가짜값 없이 빈 상태 반환(프론트가 안내 표시).
        return {
            "project_id": project_id,
            "status": "no_bim_quantities",
            "message": "이 프로젝트에 저장된 BIM 물량(bim_quantities)이 없습니다. IFC 분석을 먼저 실행하세요.",
            "items": [],
            "priced_item_count": 0,
            "unpriced_work_codes": [],
        }

    # 단가 SSOT 1회 조회(DB 우선·실패 시 fallback) — 출처 정직 표기.
    unit_prices: dict[str, dict[str, Any]] = {}
    unit_price_source = "fallback"
    try:
        from app.services.cost.unit_price_repository import UnitPriceRepository
        unit_prices = await UnitPriceRepository().get_prices()
        if any((p or {}).get("price_source") not in (None, "fallback") for p in unit_prices.values()):
            unit_price_source = "db"
    except Exception:  # noqa: BLE001
        unit_prices = {}
        unit_price_source = "fallback"

    from app.services.cost.ifc_work_map import IFC_WORK_MAP

    # work_code → 표시명(ifc_work_map 역참조, 첫 매칭).
    code_to_name: dict[str, str] = {}
    for _ifc_type, mappings in IFC_WORK_MAP.items():
        for wc, wn in mappings:
            code_to_name.setdefault(wc, wn)

    cost_items: list[dict[str, Any]] = []
    priced_items: list[dict[str, Any]] = []
    unpriced_codes: list[str] = []
    for g in grouped:
        wc = g.get("work_code") or ""
        qty = float(g.get("quantity") or 0)
        unit = g.get("unit") or ""
        price_key = _BIM_WORKCODE_TO_PRICE_KEY.get(wc)
        price = unit_prices.get(price_key) if price_key else None
        if price and price_key:
            mat_u = float(price.get("mat_unit", 0))
            labor_u = float(price.get("labor_unit", 0))
            exp_u = float(price.get("exp_unit", 0))
            item = {
                "work_code": wc,
                "item_name": code_to_name.get(wc, wc),
                "spec": price.get("spec", ""),
                "unit": price.get("unit") or unit,
                "quantity": qty,
                "mat_unit": mat_u,
                "labor_unit": labor_u,
                "exp_unit": exp_u,
            }
            cost_items.append(item)
            priced_items.append({
                **item,
                "amount": int(qty * (mat_u + labor_u + exp_u)),
                "price_source": price.get("price_source", "fallback"),
                "price_key": price_key,
                "priced": True,
            })
        else:
            # 단가 미보유(매핑 없음 또는 단가 조회 실패) — 정직 표기(0원·priced=false).
            unpriced_codes.append(wc)
            priced_items.append({
                "work_code": wc, "item_name": code_to_name.get(wc, wc),
                "unit": unit, "quantity": qty, "amount": 0,
                "price_source": None, "price_key": None, "priced": False,
            })

    calc = cost_calc.calculate(cost_items)
    return {
        "project_id": project_id,
        "status": "ok",
        "items": priced_items,
        "priced_item_count": len(cost_items),
        "unpriced_work_codes": unpriced_codes,
        "unit_price_source": unit_price_source,
        "cost": calc,
        "total_project_cost": calc.get("total_project_cost", 0),
        "note": "BIM 물량×단가 SSOT 12단계 원가(추정). 단가 미보유 공종은 0원(priced=false) — 전문 적산사 검토 권장.",
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


# ── D2: 기성고 EVM 실구현 — PV/EV/AC·SPI/CPI·과다청구 이상탐지·해시체인 ──


class BillingRegisterRequest(BaseModel):
    """회차별 기성 등록(progress_billings 영속)."""
    round: int = Field(..., ge=1, description="기성 회차")
    work_type: Optional[str] = Field(None, description="공종(표준단가 대조 키)")
    contract_amount: float = Field(0, ge=0, description="해당 공종 계약액(원)")
    claimed_amount: float = Field(0, ge=0, description="청구액(원)")
    claimed_qty: Optional[float] = Field(None, description="청구 물량")
    unit_price: Optional[float] = Field(None, description="청구 단가(원/단위)")
    contract_unit_price: Optional[float] = Field(None, description="계약 단가(원/단위, 단가이탈 기준)")
    progress_pct: float = Field(0, ge=0, le=100, description="누적 계획 공정률(%)")
    period_from: Optional[str] = None
    period_to: Optional[str] = None
    contract_total: Optional[float] = Field(None, description="전체 계약총액(없으면 회차 계약액 합)")


@router.post("/{project_id}/billing", summary="D2 기성 등록(영속+EVM 누적+과다청구 이상탐지+해시체인)")
async def register_billing_d2(project_id: str, req: BillingRegisterRequest) -> dict[str, Any]:
    """회차별 기성을 영속하고, 등록 즉시 트리거된 과다청구 경고를 반환한다."""
    from app.services.cost import billing_service

    return await billing_service.register_billing(
        project_id=project_id,
        billing_no=req.round,
        work_type=req.work_type,
        contract_amount=req.contract_amount,
        claimed_amount=req.claimed_amount,
        claimed_qty=req.claimed_qty,
        unit_price=req.unit_price,
        contract_unit_price=req.contract_unit_price,
        progress_pct=req.progress_pct,
        period_from=req.period_from,
        period_to=req.period_to,
        contract_total=req.contract_total,
    )


@router.get("/{project_id}/billing", summary="D2 기성 목록+EVM summary+곡선+이상경고")
async def get_billing_d2(project_id: str, contract_total: Optional[float] = None) -> dict[str, Any]:
    """기성 회차 목록 + EVM(PV/EV/AC·SPI/CPI·누적곡선) + 과다청구 이상경고."""
    from app.services.cost import billing_service

    return await billing_service.get_billing_summary(
        project_id=project_id, contract_total=contract_total)


@router.get("/{project_id}/billing/anomaly", summary="D2 과다청구 이상탐지(단독)")
async def get_billing_anomaly_d2(project_id: str, contract_total: Optional[float] = None) -> dict[str, Any]:
    """과다청구 이상탐지 단독 조회(단가이탈·누적초과·SPI/CPI·급증)."""
    from app.services.cost import billing_service

    return await billing_service.get_anomalies(
        project_id=project_id, contract_total=contract_total)


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


# ── CM 상세적산(MVP): BOQ 영속화 · 대안설계 원가비교(D1) · 시장가 3중(D4) ──


class BoqRequest(BaseModel):
    """BOQ(상세적산) 생성·영속화 요청 — 건축개요 기반."""
    building_type: str = "apartment"
    total_gfa_sqm: float = Field(gt=0)
    floor_count_above: int = Field(1, ge=1)
    floor_count_below: int = Field(0, ge=0)
    structure_type: str = "RC"
    tenant_id: Optional[str] = None
    persist: bool = True


class AlternativeVariant(BaseModel):
    """대안설계 변형 — base 대비 override(구조/층수 등)."""
    label: str
    overrides: dict[str, Any] = Field(default_factory=dict)


class AlternativesRequest(BaseModel):
    """D1 대안설계 A/B 원가비교 요청."""
    base_params: dict[str, Any] = Field(default_factory=dict)
    variants: list[AlternativeVariant] = Field(default_factory=list)


def _merge_params(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """base_params + overrides 병합(허용 키만)."""
    allowed = {"building_type", "total_gfa_sqm", "floor_count_above",
               "floor_count_below", "structure_type"}
    out = {
        "building_type": base.get("building_type", "apartment"),
        "total_gfa_sqm": float(base.get("total_gfa_sqm", 0) or 0),
        "floor_count_above": int(base.get("floor_count_above", 1) or 1),
        "floor_count_below": int(base.get("floor_count_below", 0) or 0),
        "structure_type": base.get("structure_type", "RC"),
    }
    for k, v in (overrides or {}).items():
        if k in allowed and v is not None:
            out[k] = v
    out["total_gfa_sqm"] = float(out["total_gfa_sqm"])
    out["floor_count_above"] = int(out["floor_count_above"])
    out["floor_count_below"] = int(out["floor_count_below"])
    return out


@router.post("/{project_id}/boq", summary="상세적산 BOQ 생성·영속화(D4 시장가 3중·정직성 표기)")
async def create_boq(project_id: str, req: BoqRequest) -> dict[str, Any]:
    """건축개요로 BOQ(공종별 물량·단가·금액)를 생성하고 cost_estimate(+item)에 영속화한다.
    각 항목에 standard/market(KCCI)/actual:null 3중 단가(D4)와 출처·신뢰구간을 부착한다."""
    from app.services.cost.boq_builder import build_boq
    from app.services.cost.cost_estimate_repository import save_estimate

    boq = await build_boq(
        building_type=req.building_type, total_gfa_sqm=req.total_gfa_sqm,
        floor_count_above=req.floor_count_above, floor_count_below=req.floor_count_below,
        structure_type=req.structure_type, qto_source="derived",
    )
    estimate_id: Optional[str] = None
    if req.persist:
        saved = await save_estimate(
            project_id=project_id, tenant_id=req.tenant_id,
            header=boq["header"], items=boq["items"],
            summary=boq["summary"], badges=boq["badges"],
        )
        estimate_id = saved.get("estimate_id")

    # D6 AI 해석(BOQ) — 실패해도 결과는 정상 반환(graceful)
    ai_analysis: Optional[str] = None
    try:
        from app.services.ai.cost_interpreter import CostInterpreter
        calc = boq.get("_calc", {})
        interp = await CostInterpreter().generate_interpretation({
            "project_name": project_id,
            "building_type": req.building_type,
            "total_gfa_sqm": req.total_gfa_sqm,
            "floor_count": req.floor_count_above,
            "total_cost": calc.get("total_project_cost", 0),
            "cost_per_sqm": round(calc.get("total_project_cost", 0) / req.total_gfa_sqm)
            if req.total_gfa_sqm else 0,
            "cost_items": [
                {"category": it["name"], "amount": it["amount"]} for it in boq["items"]
            ],
        })
        if isinstance(interp, dict):
            ai_analysis = interp.get("cost_analysis")
    except Exception:  # noqa: BLE001
        ai_analysis = None

    return {
        "ok": True,
        "estimate_id": estimate_id,
        "items": boq["items"],
        "summary": boq["summary"],
        "badges": boq["badges"],
        "ai_cost_analysis": ai_analysis,
    }


@router.get("/estimate/{estimate_id}", summary="BOQ 단건 조회(영속화된 원가계산서)")
async def get_boq(estimate_id: str) -> dict[str, Any]:
    """영속화된 BOQ(헤더+항목)를 조회한다."""
    from app.services.cost.cost_estimate_repository import get_estimate
    est = await get_estimate(estimate_id)
    if not est:
        raise HTTPException(status_code=404, detail="estimate not found")
    return {"ok": True, **est}


@router.get("/{project_id}/estimates", summary="프로젝트 BOQ 목록(최신순)")
async def list_boq(project_id: str) -> dict[str, Any]:
    """프로젝트의 영속화된 BOQ 목록을 반환한다."""
    from app.services.cost.cost_estimate_repository import list_estimates
    return {"ok": True, "items": await list_estimates(project_id)}


@router.post("/{project_id}/alternatives", summary="D1 대안설계 A/B 원가비교(변형별 델타·영향공종)")
async def cost_alternatives(project_id: str, req: AlternativesRequest) -> dict[str, Any]:
    """base_params 대비 각 변형(구조/층수 등 override)의 원가를 재산정하여
    총액 델타·델타%·영향공종을 반환한다(추정)."""
    from app.services.cost.boq_builder import build_boq

    bp = _merge_params(req.base_params, {})
    if bp["total_gfa_sqm"] <= 0:
        raise HTTPException(status_code=422, detail="base_params.total_gfa_sqm > 0 필요")

    base_boq = await build_boq(
        building_type=bp["building_type"], total_gfa_sqm=bp["total_gfa_sqm"],
        floor_count_above=bp["floor_count_above"], floor_count_below=bp["floor_count_below"],
        structure_type=bp["structure_type"], qto_source="derived",
    )
    base_total = int(base_boq["summary"]["total"])
    base_by_code = {it["code"]: it["amount"] for it in base_boq["items"]}

    variants_out: list[dict[str, Any]] = []
    for v in req.variants:
        vp = _merge_params(req.base_params, v.overrides)
        vb = await build_boq(
            building_type=vp["building_type"], total_gfa_sqm=vp["total_gfa_sqm"],
            floor_count_above=vp["floor_count_above"], floor_count_below=vp["floor_count_below"],
            structure_type=vp["structure_type"], qto_source="derived",
        )
        v_total = int(vb["summary"]["total"])
        delta = v_total - base_total
        # 영향공종: 항목별 금액 변화 큰 순.
        affected: list[str] = []
        for it in vb["items"]:
            b_amt = base_by_code.get(it["code"], 0)
            if abs(it["amount"] - b_amt) > max(1, base_total * 0.005):
                affected.append(it["name"])
        rationale = ", ".join(
            f"{k}={vp[k]}" for k in ("structure_type", "floor_count_above", "floor_count_below",
                                     "total_gfa_sqm") if vp[k] != bp[k]
        ) or "변경 없음"
        variants_out.append({
            "label": v.label, "total": v_total,
            "delta": delta, "delta_pct": round(delta / base_total * 100, 2) if base_total else 0,
            "affected_work_types": affected[:8], "rationale": rationale,
        })

    return {
        "ok": True,
        "base": {"total": base_total},
        "variants": variants_out,
        "note": "대안별 원가는 건축개요 기반 추정(±12%) — 전문 적산사 검토 권장.",
    }


@router.get("/unit-prices", summary="단가 SSOT 조회(D4 standard/market/actual 3중)")
async def get_unit_prices() -> dict[str, Any]:
    """단가 SSOT(material_unit_prices DB 우선·fallback) 목록 — standard/market/actual 3중."""
    from app.services.cost.boq_builder import _KEY_TO_KCCI, _kcci_market_unit
    from app.services.cost.unit_price_repository import UnitPriceRepository

    prices = await UnitPriceRepository().get_prices()
    items: list[dict[str, Any]] = []
    for key, p in prices.items():
        std = int(p["mat_unit"] + p["labor_unit"] + p["exp_unit"])
        market = _kcci_market_unit(key) if key in _KEY_TO_KCCI else None
        items.append({
            "code": key, "name": p["spec"], "unit": p["unit"],
            "standard": std, "market": market, "actual": None,
            "source": p["price_source"], "basis_year": p["price_basis_year"],
            "region": p.get("region"),
        })
    return {
        "ok": True, "items": items,
        "note": "standard=표준품셈/단가DB, market=KCCI 변동모델, actual=실적 데이터 없음. 참고용·전문 적산사 검토 권장.",
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
