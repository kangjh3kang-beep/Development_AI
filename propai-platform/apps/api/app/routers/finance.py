from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.services.finance.monte_carlo_service import MonteCarloService
from app.services.auth.auth_service import get_current_user
from app.models.auth import User

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
    return mc_service.run_simulation(
        total_cost_krw=req.total_cost_krw, expected_revenue_krw=req.expected_revenue_krw,
        construction_period_months=req.construction_period_months,
        discount_rate_mean=req.discount_rate_mean, revenue_uncertainty=req.revenue_uncertainty,
        n_simulations=req.n_simulations
    )
