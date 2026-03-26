"""ESG and GRESB scoring service."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.phase_e_esg import CarbonFootprint, ESGReport, GRESBAssessment


class ESGService:
    """Create ESG, carbon, and GRESB records using deterministic scoring."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _gresb_rating(overall_score: float) -> str:
        if overall_score >= 85:
            return "5 Star"
        if overall_score >= 75:
            return "4 Star"
        if overall_score >= 65:
            return "3 Star"
        if overall_score >= 55:
            return "2 Star"
        return "1 Star"

    @staticmethod
    def _derive_scores(
        *,
        total_carbon_tco2e: float,
        gross_floor_area_sqm: float,
        energy_independence_rate: float,
        climate_risk_score: float,
        lost_time_incident_rate: float,
        community_programs_count: int,
        board_independence_ratio: float,
    ) -> tuple[float, float, float, float, str, str]:
        intensity = total_carbon_tco2e * 1000 / gross_floor_area_sqm

        environmental = 92 - min(42, intensity / 8) + min(18, energy_independence_rate * 0.18) - climate_risk_score * 14
        social = 78 - min(25, lost_time_incident_rate * 8) + min(12, community_programs_count * 2.5)
        governance = 58 + board_independence_ratio * 42

        e_score = round(max(0.0, min(100.0, environmental)), 2)
        s_score = round(max(0.0, min(100.0, social)), 2)
        g_score = round(max(0.0, min(100.0, governance)), 2)
        overall = round(e_score * 0.45 + s_score * 0.25 + g_score * 0.30, 2)
        rating = ESGService._gresb_rating(overall)

        if overall >= 80:
            action_plan = "Maintain disclosure cadence and prepare external assurance for annual reporting."
        elif overall >= 65:
            action_plan = "Improve climate mitigation evidence and strengthen governance disclosures."
        else:
            action_plan = "Prioritize carbon reduction roadmap, safety controls, and board oversight improvements."

        return e_score, s_score, g_score, overall, rating, action_plan

    async def assess(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        reporting_period: str,
        gross_floor_area_sqm: float,
        scope1_tco2e: float,
        scope2_tco2e: float,
        scope3_tco2e: float,
        energy_independence_rate: float,
        climate_risk_score: float,
        lost_time_incident_rate: float,
        community_programs_count: int,
        board_independence_ratio: float,
        disclosures: list[dict],
    ) -> tuple[ESGReport, CarbonFootprint, GRESBAssessment]:
        total_carbon_tco2e = scope1_tco2e + scope2_tco2e + scope3_tco2e
        e_score, s_score, g_score, overall, rating, action_plan = self._derive_scores(
            total_carbon_tco2e=total_carbon_tco2e,
            gross_floor_area_sqm=gross_floor_area_sqm,
            energy_independence_rate=energy_independence_rate,
            climate_risk_score=climate_risk_score,
            lost_time_incident_rate=lost_time_incident_rate,
            community_programs_count=community_programs_count,
            board_independence_ratio=board_independence_ratio,
        )

        report = ESGReport(
            tenant_id=tenant_id,
            project_id=project_id,
            reporting_period=reporting_period,
            status="completed",
            environmental_score=e_score,
            social_score=s_score,
            governance_score=g_score,
            disclosures_json=disclosures,
            summary=f"Overall ESG score {overall} with {rating} equivalent performance.",
        )
        self.db.add(report)

        footprint = CarbonFootprint(
            tenant_id=tenant_id,
            project_id=project_id,
            scope1_tco2e=scope1_tco2e,
            scope2_tco2e=scope2_tco2e,
            scope3_tco2e=scope3_tco2e,
            intensity_kgco2e_per_sqm=round(total_carbon_tco2e * 1000 / gross_floor_area_sqm, 2),
            baseline_year=2026,
            breakdown_json={
                "energy_independence_rate": energy_independence_rate,
                "climate_risk_score": climate_risk_score,
            },
        )
        self.db.add(footprint)

        assessment = GRESBAssessment(
            tenant_id=tenant_id,
            project_id=project_id,
            assessment_year=2026,
            score=overall,
            rating=rating,
            gaps_json=[
                {"factor": "environment", "score": e_score},
                {"factor": "social", "score": s_score},
                {"factor": "governance", "score": g_score},
            ],
            action_plan=action_plan,
        )
        self.db.add(assessment)

        await self.db.commit()
        await self.db.refresh(report)
        await self.db.refresh(footprint)
        await self.db.refresh(assessment)
        return report, footprint, assessment
