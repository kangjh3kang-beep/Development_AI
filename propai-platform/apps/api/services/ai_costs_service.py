"""AI cost dashboard and budget persistence service."""

from datetime import datetime, timezone, UTC
UTC = UTC
from uuid import UUID

from packages.schemas.models import AICostBreakdownItem
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.ai_usage_log import AIUsageLog
from apps.api.database.models.phase_g_ai_costs import AICostBudget


class AICostsService:
    """Read AI usage metrics and persist monthly budgets."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def month_start() -> datetime:
        return datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def current_month_label() -> str:
        return AICostsService.month_start().strftime("%Y-%m")

    async def dashboard(self, tenant_id: UUID) -> tuple[str, list[AICostBreakdownItem]]:
        start_of_month = self.month_start()
        rows = (
            await self.db.execute(
                select(
                    AIUsageLog.service_name,
                    AIUsageLog.model_name,
                    func.count(AIUsageLog.id),
                    func.coalesce(
                        func.sum(
                            func.coalesce(AIUsageLog.input_tokens, 0)
                            + func.coalesce(AIUsageLog.output_tokens, 0)
                        ),
                        0,
                    ),
                    func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0),
                )
                .where(
                    AIUsageLog.tenant_id == tenant_id,
                    AIUsageLog.created_at >= start_of_month,
                )
                .group_by(AIUsageLog.service_name, AIUsageLog.model_name)
                .order_by(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0).desc())
            )
        ).all()

        items = [
            AICostBreakdownItem(
                service_name=service_name,
                model_name=model_name,
                request_count=int(request_count or 0),
                total_tokens=int(total_tokens or 0),
                total_cost_usd=round(float(total_cost_usd or 0.0), 6),
            )
            for service_name, model_name, request_count, total_tokens, total_cost_usd in rows
        ]
        return self.current_month_label(), items

    async def upsert_budget(
        self,
        *,
        tenant_id: UUID,
        endpoint: str,
        month: str,
        monthly_budget_usd: float,
        alert_threshold_ratio: float,
    ) -> AICostBudget:
        existing = await self.db.scalar(
            select(AICostBudget).where(
                AICostBudget.tenant_id == tenant_id,
                AICostBudget.endpoint == endpoint,
                AICostBudget.month == month,
            )
        )
        if existing is None:
            existing = AICostBudget(
                tenant_id=tenant_id,
                endpoint=endpoint,
                month=month,
                monthly_budget_usd=monthly_budget_usd,
                alert_threshold_ratio=alert_threshold_ratio,
            )
            self.db.add(existing)
        else:
            existing.monthly_budget_usd = monthly_budget_usd
            existing.alert_threshold_ratio = alert_threshold_ratio

        await self.db.commit()
        await self.db.refresh(existing)
        return existing

    async def budget_gate(
        self,
        *,
        tenant_id: UUID,
        endpoint: str,
        monthly_budget_override: float | None,
    ) -> tuple[float, float, float, bool]:
        current_cost = await self.db.scalar(
            select(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0)).where(
                AIUsageLog.tenant_id == tenant_id,
                AIUsageLog.created_at >= self.month_start(),
            )
        )
        current_cost_usd = round(float(current_cost or 0.0), 6)

        budget = monthly_budget_override
        if budget is None:
            record = await self.db.scalar(
                select(AICostBudget).where(
                    AICostBudget.tenant_id == tenant_id,
                    AICostBudget.endpoint == endpoint,
                    AICostBudget.month == self.current_month_label(),
                )
            )
            budget = record.monthly_budget_usd if record is not None else 50.0

        remaining_budget_usd = round(max(0.0, float(budget) - current_cost_usd), 6)
        return float(budget), current_cost_usd, remaining_budget_usd, current_cost_usd <= float(budget)
