"""Feasibility analysis service backed by financial_analyses persistence."""

from math import isfinite
from uuid import UUID

from packages.schemas.models import FeasibilityCashflowRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.financial_analysis import FinancialAnalysis
from apps.api.database.models.project import Project


class FeasibilityService:
    """Create and read deterministic feasibility analysis scenarios."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _build_cashflows(
        *,
        annual_revenue_krw: float,
        annual_operating_cost_krw: float,
        annual_growth_rate: float,
        discount_rate: float,
        analysis_years: int,
    ) -> list[FeasibilityCashflowRow]:
        rows: list[FeasibilityCashflowRow] = []

        for year in range(1, analysis_years + 1):
            growth_multiplier = (1 + annual_growth_rate) ** (year - 1)
            revenue = annual_revenue_krw * growth_multiplier
            operating_cost = annual_operating_cost_krw * growth_multiplier
            net_cashflow = revenue - operating_cost
            discounted_cashflow = net_cashflow / ((1 + discount_rate) ** year)
            rows.append(
                FeasibilityCashflowRow(
                    year=year,
                    revenue_krw=round(revenue, 2),
                    operating_cost_krw=round(operating_cost, 2),
                    net_cashflow_krw=round(net_cashflow, 2),
                    discounted_cashflow_krw=round(discounted_cashflow, 2),
                )
            )
        return rows

    @staticmethod
    def _calc_irr(cashflows: list[float]) -> float:
        lo, hi = -0.5, 1.0
        for _ in range(120):
            mid = (lo + hi) / 2
            npv = 0.0
            valid = True
            for index, cashflow in enumerate(cashflows):
                denominator = (1 + mid) ** index
                if denominator == 0:
                    valid = False
                    break
                npv += cashflow / denominator
            if not valid or not isfinite(npv):
                hi = mid
                continue
            if npv > 0:
                lo = mid
            else:
                hi = mid
        return round((lo + hi) / 2, 6)

    @staticmethod
    def _calc_payback_period_months(
        *,
        total_investment_krw: float,
        annual_cashflows: list[FeasibilityCashflowRow],
        exit_value_krw: float,
    ) -> int:
        cumulative = -total_investment_krw
        for row in annual_cashflows:
            cumulative += row.net_cashflow_krw
            if cumulative >= 0:
                return row.year * 12

        cumulative += exit_value_krw
        if cumulative >= 0:
            return len(annual_cashflows) * 12

        return (len(annual_cashflows) + 1) * 12

    @staticmethod
    def _calc_risk_score(
        *,
        irr: float,
        payback_period_months: int,
        total_revenue_krw: float,
        total_operating_cost_krw: float,
        discount_rate: float,
    ) -> float:
        margin = 0.0
        if total_revenue_krw > 0:
            margin = max(0.0, min(1.0, (total_revenue_krw - total_operating_cost_krw) / total_revenue_krw))

        irr_penalty = max(0.0, min(1.0, (0.12 - irr) / 0.12))
        payback_penalty = max(0.0, min(1.0, (payback_period_months - 48) / 72))
        discount_penalty = max(0.0, min(1.0, (discount_rate - 0.05) / 0.1))
        margin_credit = margin * 0.35

        risk_score = 0.55 * irr_penalty + 0.3 * payback_penalty + 0.15 * discount_penalty - margin_credit
        return round(max(0.0, min(1.0, risk_score)), 4)

    async def analyze(
        self,
        *,
        project_id: UUID,
        tenant_id: UUID,
        scenario_name: str,
        total_investment_krw: float,
        annual_revenue_krw: float,
        annual_operating_cost_krw: float,
        discount_rate: float,
        annual_growth_rate: float,
        analysis_years: int,
        exit_value_krw: float | None,
    ) -> FinancialAnalysis:
        project = await self.db.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.tenant_id == tenant_id,
                Project.is_deleted == False,  # noqa: E712
            )
        )
        if project is None:
            raise ValueError("Project not found")

        resolved_exit_value = float(exit_value_krw or (total_investment_krw * 1.18))
        cashflows = self._build_cashflows(
            annual_revenue_krw=annual_revenue_krw,
            annual_operating_cost_krw=annual_operating_cost_krw,
            annual_growth_rate=annual_growth_rate,
            discount_rate=discount_rate,
            analysis_years=analysis_years,
        )

        total_revenue = round(sum(row.revenue_krw for row in cashflows), 2)
        total_operating_cost = round(sum(row.operating_cost_krw for row in cashflows), 2)
        npv = -total_investment_krw
        for row in cashflows:
            npv += row.discounted_cashflow_krw
        npv += resolved_exit_value / ((1 + discount_rate) ** analysis_years)

        irr = self._calc_irr(
            [-total_investment_krw]
            + [row.net_cashflow_krw for row in cashflows[:-1]]
            + [cashflows[-1].net_cashflow_krw + resolved_exit_value]
        )
        payback_period_months = self._calc_payback_period_months(
            total_investment_krw=total_investment_krw,
            annual_cashflows=cashflows,
            exit_value_krw=resolved_exit_value,
        )
        risk_score = self._calc_risk_score(
            irr=irr,
            payback_period_months=payback_period_months,
            total_revenue_krw=total_revenue,
            total_operating_cost_krw=total_operating_cost,
            discount_rate=discount_rate,
        )

        analysis = FinancialAnalysis(
            tenant_id=tenant_id,
            project_id=project_id,
            npv=round(npv, 2),
            irr=irr,
            payback_period_months=payback_period_months,
            total_investment=round(total_investment_krw, 2),
            total_revenue=total_revenue,
            risk_score=risk_score,
            scenario_name=scenario_name,
            assumptions={
                "discount_rate": discount_rate,
                "annual_growth_rate": annual_growth_rate,
                "analysis_years": analysis_years,
                "exit_value_krw": resolved_exit_value,
                "project_name": project.name,
            },
            cash_flow_yearly=[row.model_dump() for row in cashflows],
        )
        self.db.add(analysis)
        await self.db.commit()
        await self.db.refresh(analysis)
        return analysis

    async def get_latest(
        self,
        *,
        project_id: UUID,
        tenant_id: UUID,
    ) -> FinancialAnalysis | None:
        return await self.db.scalar(
            select(FinancialAnalysis)
            .where(
                FinancialAnalysis.project_id == project_id,
                FinancialAnalysis.tenant_id == tenant_id,
            )
            .order_by(FinancialAnalysis.created_at.desc())
            .limit(1)
        )
