"""Underwriting service for G81 investment screening."""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.phase_e_underwriting import (
    DataRoomDocument,
    InvestmentUnderwriting,
    LPReport,
)
from apps.api.services.jeonse_risk_service import JeonseRiskService

_DOC_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "market-study": ("market", "market-study", "demand", "feasibility"),
    "appraisal": ("appraisal", "valuation", "avm"),
    "financial-model": ("cashflow", "model", "underwriting", "financial"),
    "permits": ("permit", "approval", "license", "regulation"),
    "lease": ("lease", "rent roll", "tenant", "contract"),
}


class UnderwritingService:
    """Create and retrieve underwriting analyses."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _classify_document(file_name: str) -> str:
        normalized = file_name.lower()
        for doc_type, keywords in _DOC_TYPE_KEYWORDS.items():
            if any(keyword in normalized for keyword in keywords):
                return doc_type
        return "general"

    @staticmethod
    def _derive_score(
        profit_margin_ratio: float,
        debt_ratio: float,
        equity_multiple: float,
        jeonse_ratio: float | None,
    ) -> tuple[float, str, str, list[dict[str, str | float]]]:
        score = 0.5
        risk_flags: list[dict[str, str | float]] = []

        margin_delta = min(0.2, max(-0.2, (profit_margin_ratio - 0.15) * 0.7))
        debt_delta = min(0.2, max(-0.25, (0.55 - debt_ratio) * 0.45))
        multiple_delta = min(0.2, max(-0.15, (equity_multiple - 1.5) * 0.12))
        score += margin_delta + debt_delta + multiple_delta

        risk_flags.append(
            {
                "factor": "profit-margin",
                "impact": "positive" if margin_delta >= 0 else "negative",
                "value": round(profit_margin_ratio, 4),
            }
        )
        risk_flags.append(
            {
                "factor": "debt-ratio",
                "impact": "positive" if debt_delta >= 0 else "negative",
                "value": round(debt_ratio, 4),
            }
        )
        risk_flags.append(
            {
                "factor": "equity-multiple",
                "impact": "positive" if multiple_delta >= 0 else "negative",
                "value": round(equity_multiple, 4),
            }
        )

        if jeonse_ratio is not None:
            jeonse_level, jeonse_score = JeonseRiskService._calculate_risk_level(jeonse_ratio)
            score -= jeonse_score * 0.18
            risk_flags.append(
                {
                    "factor": "jeonse-risk",
                    "impact": jeonse_level.lower(),
                    "value": round(jeonse_ratio, 4),
                }
            )

        bounded_score = max(0.05, min(0.95, score))
        if bounded_score >= 0.75:
            return bounded_score, "LOW", "invest", risk_flags
        if bounded_score >= 0.6:
            return bounded_score, "MEDIUM", "invest-with-conditions", risk_flags
        if bounded_score >= 0.45:
            return bounded_score, "HIGH", "watchlist", risk_flags
        return bounded_score, "CRITICAL", "decline", risk_flags

    async def create_underwriting(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        project_name: str,
        total_cost_krw: float,
        projected_revenue_krw: float,
        acquisition_price_krw: float,
        equity_krw: float,
        debt_krw: float,
        jeonse_ratio: float | None,
        assumptions_json: dict | None,
        data_room_documents: Iterable[dict],
    ) -> InvestmentUnderwriting:
        projected_profit_krw = projected_revenue_krw - total_cost_krw
        profit_margin_ratio = (
            projected_profit_krw / projected_revenue_krw if projected_revenue_krw else 0.0
        )
        debt_ratio = debt_krw / total_cost_krw if total_cost_krw else 0.0
        equity_multiple = (
            projected_revenue_krw / equity_krw if equity_krw > 0 else 0.0
        )

        risk_score, risk_level, recommendation, key_risks = self._derive_score(
            profit_margin_ratio=profit_margin_ratio,
            debt_ratio=debt_ratio,
            equity_multiple=equity_multiple,
            jeonse_ratio=jeonse_ratio,
        )

        underwriting = InvestmentUnderwriting(
            tenant_id=tenant_id,
            project_id=project_id,
            project_name=project_name,
            total_cost_krw=total_cost_krw,
            projected_revenue_krw=projected_revenue_krw,
            acquisition_price_krw=acquisition_price_krw,
            equity_krw=equity_krw,
            debt_krw=debt_krw,
            projected_profit_krw=projected_profit_krw,
            profit_margin_ratio=profit_margin_ratio,
            debt_ratio=debt_ratio,
            equity_multiple=equity_multiple,
            jeonse_ratio=jeonse_ratio,
            risk_level=risk_level,
            risk_score=round(risk_score, 4),
            recommendation=recommendation,
            narrative=(
                f"Projected profit margin {profit_margin_ratio:.1%}, debt ratio {debt_ratio:.1%}, "
                f"equity multiple {equity_multiple:.2f}x. Recommendation: {recommendation}."
            ),
            key_risks=key_risks,
            assumptions_json=assumptions_json or {},
        )
        self.db.add(underwriting)
        await self.db.flush()

        metrics_json = {
            "projected_profit_krw": projected_profit_krw,
            "profit_margin_ratio": round(profit_margin_ratio, 4),
            "debt_ratio": round(debt_ratio, 4),
            "equity_multiple": round(equity_multiple, 4),
            "risk_score": round(risk_score, 4),
        }
        report = LPReport(
            tenant_id=tenant_id,
            project_id=project_id,
            underwriting_id=underwriting.id,
            report_title=f"{project_name} LP memo",
            executive_summary=(
                f"{project_name} screening indicates {risk_level.lower()} underwriting risk "
                f"with recommendation '{recommendation}'."
            ),
            metrics_json=metrics_json,
            distribution_waterfall_json={"preferred_return": 0.08, "promote_split": "80/20"},
            generated_by="underwriting-service",
        )
        self.db.add(report)

        for document in data_room_documents:
            file_name = str(document["file_name"])
            doc = DataRoomDocument(
                tenant_id=tenant_id,
                project_id=project_id,
                underwriting_id=underwriting.id,
                file_name=file_name,
                document_type=self._classify_document(file_name),
                storage_url=str(document["storage_url"]),
                size_bytes=int(document.get("size_bytes", 0)),
                tags_json=list(document.get("tags", [])),
                parsed_summary=document.get("parsed_summary"),
            )
            self.db.add(doc)

        await self.db.commit()
        await self.db.refresh(underwriting)
        return underwriting

    async def list_history(
        self,
        *,
        tenant_id: UUID,
        limit: int = 20,
    ) -> list[InvestmentUnderwriting]:
        stmt = (
            select(InvestmentUnderwriting)
            .where(InvestmentUnderwriting.tenant_id == tenant_id)
            .order_by(InvestmentUnderwriting.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
