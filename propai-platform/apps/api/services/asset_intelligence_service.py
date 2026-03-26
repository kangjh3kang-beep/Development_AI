"""Asset intelligence service for G90."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.avm_valuation import AVMValuation
from apps.api.database.models.phase_e_climate import ClimateRiskAssessment
from apps.api.database.models.phase_f_asset_intelligence import (
    AssetIntelligenceSnapshot,
    CapexOptimizationResult,
)
from apps.api.database.models.phase_f_maintenance import PredictiveMaintenanceAlert
from apps.api.database.models.phase_f_tenant import TenantFinancialHealth


class AssetIntelligenceService:
    """Aggregate project signals into an asset intelligence snapshot."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _latest_alert(self, project_id: UUID) -> PredictiveMaintenanceAlert | None:
        stmt = (
            select(PredictiveMaintenanceAlert)
            .where(PredictiveMaintenanceAlert.project_id == project_id)
            .order_by(PredictiveMaintenanceAlert.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _latest_tenant_health(self, project_id: UUID) -> TenantFinancialHealth | None:
        stmt = (
            select(TenantFinancialHealth)
            .where(TenantFinancialHealth.project_id == project_id)
            .order_by(TenantFinancialHealth.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _latest_climate(self, project_id: UUID) -> ClimateRiskAssessment | None:
        stmt = (
            select(ClimateRiskAssessment)
            .where(ClimateRiskAssessment.project_id == project_id)
            .order_by(ClimateRiskAssessment.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _latest_avm(self, project_id: UUID) -> AVMValuation | None:
        stmt = (
            select(AVMValuation)
            .where(AVMValuation.project_id == project_id)
            .order_by(AVMValuation.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _resolve_scores(
        self,
        *,
        project_id: UUID,
        maintenance_score: float | None,
        tenant_score: float | None,
        market_score: float | None,
        climate_score: float | None,
    ) -> dict[str, float]:
        resolved = {
            "maintenance": 62.0 if maintenance_score is None else maintenance_score,
            "tenant": 64.0 if tenant_score is None else tenant_score,
            "market": 66.0 if market_score is None else market_score,
            "climate": 60.0 if climate_score is None else climate_score,
        }

        if maintenance_score is None:
            alert = await self._latest_alert(project_id)
            if alert is not None:
                resolved["maintenance"] = round(max(0.0, min(100.0, 100 - alert.anomaly_score * 100)), 2)

        if tenant_score is None:
            health = await self._latest_tenant_health(project_id)
            if health is not None:
                resolved["tenant"] = round(
                    max(
                        0.0,
                        min(
                            100.0,
                            health.occupancy_rate * 55
                            + (1 - health.arrears_ratio) * 25
                            + (1 - health.churn_risk_score) * 20,
                        ),
                    ),
                    2,
                )

        if climate_score is None:
            climate = await self._latest_climate(project_id)
            if climate is not None:
                severity = max(climate.flood_risk_score, climate.heat_risk_score)
                resolved["climate"] = round(max(0.0, min(100.0, 100 - severity * 100)), 2)

        if market_score is None:
            avm = await self._latest_avm(project_id)
            if avm is not None:
                resolved["market"] = round(max(0.0, min(100.0, avm.confidence_score * 100)), 2)

        return resolved

    @staticmethod
    def _grade(composite_score: float) -> str:
        if composite_score >= 85:
            return "A"
        if composite_score >= 72:
            return "B"
        if composite_score >= 60:
            return "C"
        if composite_score >= 45:
            return "D"
        return "E"

    @staticmethod
    def _capex_plan(component_scores: dict[str, float]) -> list[dict]:
        recommendations: list[dict] = []
        if component_scores["maintenance"] < 70:
            recommendations.append(
                {
                    "strategy": "HVAC reliability retrofit",
                    "expected_roi": 0.16,
                    "payback_months": 24,
                }
            )
        if component_scores["tenant"] < 68:
            recommendations.append(
                {
                    "strategy": "Tenant service and amenity uplift",
                    "expected_roi": 0.13,
                    "payback_months": 18,
                }
            )
        if component_scores["climate"] < 70:
            recommendations.append(
                {
                    "strategy": "Flood and heat resilience package",
                    "expected_roi": 0.11,
                    "payback_months": 30,
                }
            )
        if not recommendations:
            recommendations.append(
                {
                    "strategy": "Deferred capex reserve optimization",
                    "expected_roi": 0.08,
                    "payback_months": 12,
                }
            )
        return recommendations

    async def analyze(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        base_value_krw: float,
        maintenance_score: float | None,
        tenant_score: float | None,
        market_score: float | None,
        climate_score: float | None,
    ) -> tuple[AssetIntelligenceSnapshot, list[CapexOptimizationResult]]:
        component_scores = await self._resolve_scores(
            project_id=project_id,
            maintenance_score=maintenance_score,
            tenant_score=tenant_score,
            market_score=market_score,
            climate_score=climate_score,
        )

        composite_score = round(
            component_scores["maintenance"] * 0.22
            + component_scores["tenant"] * 0.25
            + component_scores["market"] * 0.33
            + component_scores["climate"] * 0.20,
            2,
        )
        grade = self._grade(composite_score)
        adjustment_factor = 0.88 + composite_score / 100 * 0.24
        adjusted_value_krw = round(base_value_krw * adjustment_factor, 2)

        snapshot = AssetIntelligenceSnapshot(
            tenant_id=tenant_id,
            project_id=project_id,
            composite_score=composite_score,
            grade=grade,
            adjusted_value_krw=adjusted_value_krw,
            component_scores_json=component_scores,
            narrative=(
                f"Composite score {composite_score} driven by market {component_scores['market']}, "
                f"tenant {component_scores['tenant']}, maintenance {component_scores['maintenance']}, "
                f"and climate {component_scores['climate']}."
            ),
        )
        self.db.add(snapshot)
        await self.db.flush()

        capex_results: list[CapexOptimizationResult] = []
        for item in self._capex_plan(component_scores):
            result = CapexOptimizationResult(
                tenant_id=tenant_id,
                project_id=project_id,
                snapshot_id=snapshot.id,
                strategy_name=item["strategy"],
                expected_roi=item["expected_roi"],
                payback_months=item["payback_months"],
                recommendations_json=[item],
            )
            self.db.add(result)
            capex_results.append(result)

        await self.db.commit()
        await self.db.refresh(snapshot)
        for result in capex_results:
            await self.db.refresh(result)
        return snapshot, capex_results
