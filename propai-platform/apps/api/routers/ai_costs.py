"""AI cost dashboard endpoints."""

from fastapi import APIRouter, Depends, Query
from packages.schemas.models import (
    AIBudgetGateResponse,
    AICostBudgetRequest,
    AICostBudgetResponse,
    AICostDashboardResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.ai_costs_service import AICostsService

router = APIRouter()


@router.get("/dashboard", response_model=AICostDashboardResponse)
async def get_ai_cost_dashboard(
    current_user: CurrentUser = Depends(RequirePermission("ai_costs", "read")),
    db: AsyncSession = Depends(get_db),
) -> AICostDashboardResponse:
    service = AICostsService(db)
    month, items = await service.dashboard(current_user.tenant_id)

    return AICostDashboardResponse(
        month=month,
        total_cost_usd=round(sum(item.total_cost_usd for item in items), 6),
        total_tokens=sum(item.total_tokens for item in items),
        by_service=items,
    )


@router.post("/budget", response_model=AICostBudgetResponse)
async def configure_ai_budget(
    body: AICostBudgetRequest,
    current_user: CurrentUser = Depends(RequirePermission("ai_costs", "write")),
    db: AsyncSession = Depends(get_db),
) -> AICostBudgetResponse:
    service = AICostsService(db)
    budget = await service.upsert_budget(
        tenant_id=current_user.tenant_id,
        endpoint=body.endpoint,
        month=body.month or service.current_month_label(),
        monthly_budget_usd=body.monthly_budget_usd,
        alert_threshold_ratio=body.alert_threshold_ratio,
    )
    return AICostBudgetResponse(
        budget_id=budget.id,
        endpoint=budget.endpoint,
        month=budget.month,
        monthly_budget_usd=budget.monthly_budget_usd,
        alert_threshold_ratio=budget.alert_threshold_ratio,
        created_at=budget.created_at,
    )


@router.get("/budget-gate/{endpoint:path}", response_model=AIBudgetGateResponse)
async def evaluate_budget_gate(
    endpoint: str,
    monthly_budget_usd: float | None = Query(default=None, ge=0),
    current_user: CurrentUser = Depends(RequirePermission("ai_costs", "read")),
    db: AsyncSession = Depends(get_db),
) -> AIBudgetGateResponse:
    service = AICostsService(db)
    budget, current_cost_usd, remaining_budget_usd, allowed = await service.budget_gate(
        tenant_id=current_user.tenant_id,
        endpoint=endpoint,
        monthly_budget_override=monthly_budget_usd,
    )

    return AIBudgetGateResponse(
        endpoint=endpoint,
        monthly_budget_usd=budget,
        current_cost_usd=current_cost_usd,
        remaining_budget_usd=remaining_budget_usd,
        allowed=allowed,
    )
