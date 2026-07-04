from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.models.auth import User
from app.services.auth.auth_service import get_current_user
from app.services.finance.monte_carlo_service import MonteCarloService

router = APIRouter(prefix="/api/v1/finance", tags=["금융 AI"])
mc_service = MonteCarloService()

class SimulationRequest(BaseModel):
    total_cost_krw: float
    expected_revenue_krw: float
    construction_period_months: int
    discount_rate_mean: float = 0.08
    revenue_uncertainty: float = 0.15
    n_simulations: int = 10000

@router.post("/monte-carlo")
async def run_monte_carlo(req: SimulationRequest, current_user: User = Depends(get_current_user)):
    result = mc_service.run_simulation(
        total_cost_krw=req.total_cost_krw, expected_revenue_krw=req.expected_revenue_krw,
        construction_period_months=req.construction_period_months,
        discount_rate_mean=req.discount_rate_mean, revenue_uncertainty=req.revenue_uncertainty,
        n_simulations=req.n_simulations
    )
    # 표준 근거 블록(#5): NPV 분포·흑자확률의 실값·산식·출처를 dict 키로 가산(graceful·무목업).
    if isinstance(result, dict):
        try:
            from typing import Any

            from app.services.data_validation.evidence_contract import build_evidence_block

            items: list[dict[str, Any]] = []
            if result.get("npv_mean_krw") is not None:
                items.append({"label": "NPV 평균(원)", "value": result.get("npv_mean_krw"),
                              "basis": f"몬테카를로 {result.get('n_simulations')}회 NPV 표본 평균"})
            if result.get("npv_p10_krw") is not None and result.get("npv_p90_krw") is not None:
                items.append({"label": "NPV 80% 구간(원)",
                              "value": [result.get("npv_p10_krw"), result.get("npv_p90_krw")],
                              "basis": "NPV 표본 분포의 P10~P90 백분위"})
            if result.get("probability_positive_npv") is not None:
                items.append({"label": "흑자(NPV>0) 확률", "value": result.get("probability_positive_npv"),
                              "basis": "NPV>0 표본 비율"})
            if result.get("irr_mean") is not None:
                items.append({"label": "IRR 평균", "value": result.get("irr_mean"),
                              "basis": "(매출/총비용)^(1/T)−1 표본 평균(연환산)"})
            if items:
                result["evidence"] = build_evidence_block(
                    items=items,
                    sources=["프로젝트 투자·매출 가정(사용자 입력)"],
                )
        except Exception:  # noqa: BLE001 — 근거 블록 실패는 결과를 막지 않음(가산·정직).
            pass
    return result
