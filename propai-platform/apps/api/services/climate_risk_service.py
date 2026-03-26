"""Climate risk service for G85 resilience workflows."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.phase_e_climate import (
    ClimateRiskAssessment,
    InsuranceRecommendation,
)
from apps.api.services.construction_ai_service import ConstructionAIService


class ClimateRiskService:
    """Persist climate assessments and insurance recommendations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.construction_service = ConstructionAIService(db)

    @staticmethod
    def _priority(score: float) -> str:
        if score >= 0.7:
            return "high"
        if score >= 0.45:
            return "medium"
        return "low"

    async def analyze_and_store(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        lat: float,
        lon: float,
        construction_period_months: int,
        asset_value_krw: float,
    ) -> tuple[ClimateRiskAssessment, list[InsuranceRecommendation]]:
        baseline = await self.construction_service.analyze_climate_risk(
            project_id=project_id,
            lat=lat,
            lon=lon,
            construction_period_months=construction_period_months,
        )

        severity_score = max(
            baseline["flood_risk_score"],
            baseline["heat_risk_score"],
        )
        annual_expected_loss_krw = asset_value_krw * (0.004 + severity_score * 0.028)

        assessment = ClimateRiskAssessment(
            tenant_id=tenant_id,
            project_id=project_id,
            latitude=lat,
            longitude=lon,
            construction_period_months=construction_period_months,
            flood_risk_score=baseline["flood_risk_score"],
            heat_risk_score=baseline["heat_risk_score"],
            overall_risk_level=baseline["overall_risk_level"],
            annual_expected_loss_krw=round(annual_expected_loss_krw, 2),
            risk_factors=baseline["risk_factors"],
            mitigation_tips=baseline["mitigation_tips"],
            scenario_notes="Derived from construction climate baseline with insurance packaging.",
        )
        self.db.add(assessment)
        await self.db.flush()

        coverage_specs = [
            (
                "flood-damage",
                baseline["flood_risk_score"],
                asset_value_krw * 0.35,
                "Protects against inundation, runoff, and site restoration losses.",
            ),
            (
                "heat-stress-delay",
                baseline["heat_risk_score"],
                asset_value_krw * 0.12,
                "Offsets schedule slippage and productivity drops during prolonged heat events.",
            ),
            (
                "business-interruption",
                (baseline["flood_risk_score"] + baseline["heat_risk_score"]) / 2,
                asset_value_krw * 0.18,
                "Covers downtime-driven revenue interruption and carrying cost exposure.",
            ),
        ]

        recommendations: list[InsuranceRecommendation] = []
        for coverage_type, score, coverage_limit_krw, rationale in coverage_specs:
            premium_rate = 0.006 + score * 0.01
            recommendation = InsuranceRecommendation(
                tenant_id=tenant_id,
                project_id=project_id,
                climate_risk_assessment_id=assessment.id,
                coverage_type=coverage_type,
                priority=self._priority(score),
                annual_premium_estimate_krw=round(coverage_limit_krw * premium_rate, 2),
                coverage_limit_krw=round(coverage_limit_krw, 2),
                rationale=rationale,
                broker_notes_json={
                    "risk_score": round(score, 4),
                    "premium_rate": round(premium_rate, 4),
                },
            )
            self.db.add(recommendation)
            recommendations.append(recommendation)

        await self.db.commit()
        await self.db.refresh(assessment)
        return assessment, recommendations
