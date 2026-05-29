"""v61 공사비 라우터 — IFC 물량 + 원가계산 + 몬테카를로 + 기성.

prefix: /api/v1/cost
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.cost.origin_cost_calculator import OriginCostCalculator, CostItem
from app.services.cost.cost_monte_carlo import CostMonteCarlo
from app.services.bim.bim_service import BIMService

router = APIRouter(prefix="/api/v1/cost", tags=["v61 공사비"])
cost_calc = OriginCostCalculator()
bim_service = BIMService()


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
    return {
        "project_id": project_id,
        **result,
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
