"""Unified v53 risk scoring engine."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.phase_v53_operations import (
    DigitalTwinStatusSnapshot,
    PermitSubmission,
    UnifiedRiskAssessment,
)


class RiskScoringEngine:
    """Project-level risk scoring with persisted downside metrics."""

    WEIGHTS = {
        "market": 0.15,
        "financial": 0.18,
        "regulatory": 0.14,
        "operational": 0.12,
        "climate": 0.11,
        "construction": 0.16,
        "leasing": 0.14,
    }

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
        return max(lower, min(upper, value))

    @classmethod
    def _grade(cls, score: float) -> str:
        if score < 25:
            return "A"
        if score < 40:
            return "B"
        if score < 55:
            return "C"
        if score < 70:
            return "D"
        if score < 85:
            return "E"
        return "F"

    @classmethod
    def _dimension_scores(
        cls,
        *,
        market_risk_score: float,
        ltv_ratio: float,
        dscr: float,
        permit_readiness_ratio: float,
        operational_readiness_ratio: float | None,
        climate_risk_score: float,
        cost_volatility_ratio: float,
        occupancy_rate: float,
        presale_ratio: float,
    ) -> list[dict]:
        market = cls._clamp(market_risk_score)
        financial = cls._clamp((ltv_ratio * 70.0) + max(1.2 - dscr, 0.0) * 45.0)
        regulatory = cls._clamp((1.0 - permit_readiness_ratio) * 100.0)
        if operational_readiness_ratio is not None:
            operational = cls._clamp((1.0 - operational_readiness_ratio) * 100.0)
            operational_reason = (
                f"Latest digital twin readiness was {operational_readiness_ratio * 100:.1f}%."
            )
        else:
            operational = cls._clamp((1.0 - occupancy_rate) * 50.0 + cost_volatility_ratio * 30.0)
            operational_reason = "No persisted digital twin status was available, so fallback heuristics were used."
        climate = cls._clamp(climate_risk_score)
        construction = cls._clamp(cost_volatility_ratio * 100.0)
        leasing = cls._clamp((1.0 - occupancy_rate) * 60.0 + (1.0 - presale_ratio) * 40.0)

        return [
            {
                "dimension": "market",
                "score": round(market, 2),
                "weight": cls.WEIGHTS["market"],
                "rationale": f"Market risk input was {market_risk_score:.1f} on a 0-100 scale.",
            },
            {
                "dimension": "financial",
                "score": round(financial, 2),
                "weight": cls.WEIGHTS["financial"],
                "rationale": f"LTV {ltv_ratio:.2f} and DSCR {dscr:.2f} drove the funding stress profile.",
            },
            {
                "dimension": "regulatory",
                "score": round(regulatory, 2),
                "weight": cls.WEIGHTS["regulatory"],
                "rationale": f"Permit readiness was normalized to {permit_readiness_ratio * 100:.1f}%.",
            },
            {
                "dimension": "operational",
                "score": round(operational, 2),
                "weight": cls.WEIGHTS["operational"],
                "rationale": operational_reason,
            },
            {
                "dimension": "climate",
                "score": round(climate, 2),
                "weight": cls.WEIGHTS["climate"],
                "rationale": f"Climate risk input was {climate_risk_score:.1f}.",
            },
            {
                "dimension": "construction",
                "score": round(construction, 2),
                "weight": cls.WEIGHTS["construction"],
                "rationale": f"Cost volatility ratio was {cost_volatility_ratio:.2f}.",
            },
            {
                "dimension": "leasing",
                "score": round(leasing, 2),
                "weight": cls.WEIGHTS["leasing"],
                "rationale": (
                    f"Occupancy {occupancy_rate:.2f} and presale {presale_ratio:.2f} determined lease-up pressure."
                ),
            },
        ]

    async def _latest_operational_readiness(
        self,
        tenant_id: UUID,
        project_id: UUID,
    ) -> float | None:
        result = await self.db.execute(
            select(DigitalTwinStatusSnapshot)
            .where(
                DigitalTwinStatusSnapshot.tenant_id == tenant_id,
                DigitalTwinStatusSnapshot.project_id == project_id,
            )
            .order_by(DigitalTwinStatusSnapshot.created_at.desc())
            .limit(1)
        )
        snapshot = result.scalar_one_or_none()
        if snapshot is None:
            return None
        return max(min(snapshot.operational_readiness_score / 100.0, 1.0), 0.0)

    async def _latest_permit_readiness(
        self,
        tenant_id: UUID,
        project_id: UUID,
    ) -> float | None:
        result = await self.db.execute(
            select(PermitSubmission)
            .where(
                PermitSubmission.tenant_id == tenant_id,
                PermitSubmission.project_id == project_id,
            )
            .order_by(PermitSubmission.created_at.desc())
            .limit(1)
        )
        submission = result.scalar_one_or_none()
        if submission is None:
            return None
        return max(min(submission.readiness_score / 100.0, 1.0), 0.0)

    async def analyze(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        base_project_cost_krw: float,
        market_risk_score: float,
        ltv_ratio: float,
        dscr: float,
        permit_readiness_ratio: float,
        occupancy_rate: float,
        presale_ratio: float,
        climate_risk_score: float,
        cost_volatility_ratio: float,
    ) -> dict:
        latest_operational = await self._latest_operational_readiness(tenant_id, project_id)
        latest_permit = await self._latest_permit_readiness(tenant_id, project_id)
        effective_permit = max(permit_readiness_ratio, latest_permit or 0.0)
        dimensions = self._dimension_scores(
            market_risk_score=market_risk_score,
            ltv_ratio=ltv_ratio,
            dscr=dscr,
            permit_readiness_ratio=effective_permit,
            operational_readiness_ratio=latest_operational,
            climate_risk_score=climate_risk_score,
            cost_volatility_ratio=cost_volatility_ratio,
            occupancy_rate=occupancy_rate,
            presale_ratio=presale_ratio,
        )
        composite = round(
            sum(item["score"] * item["weight"] for item in dimensions),
            2,
        )
        var_95_ratio = round(
            0.03 + (composite / 100.0 * 0.14) + (cost_volatility_ratio * 0.08),
            4,
        )
        p90_adjusted_cost = round(base_project_cost_krw * (1.0 + var_95_ratio), 2)
        expected_downside = round(base_project_cost_krw * (composite / 100.0) * 0.06, 2)
        grade = self._grade(composite)
        summary = (
            f"Unified risk grade {grade} with composite score {composite:.1f}, "
            f"VaR95 {var_95_ratio * 100:.1f}%, and P90 cost {p90_adjusted_cost:,.0f} KRW."
        )

        assessment = UnifiedRiskAssessment(
            tenant_id=tenant_id,
            project_id=project_id,
            composite_risk_score=composite,
            grade=grade,
            var_95_ratio=var_95_ratio,
            p90_adjusted_cost_krw=p90_adjusted_cost,
            expected_downside_krw=expected_downside,
            dimension_scores_json=dimensions,
            assumptions_json={
                "market_risk_score": market_risk_score,
                "ltv_ratio": ltv_ratio,
                "dscr": dscr,
                "permit_readiness_ratio": permit_readiness_ratio,
                "effective_permit_readiness_ratio": effective_permit,
                "occupancy_rate": occupancy_rate,
                "presale_ratio": presale_ratio,
                "climate_risk_score": climate_risk_score,
                "cost_volatility_ratio": cost_volatility_ratio,
                "latest_operational_readiness_ratio": latest_operational,
            },
            summary=summary,
        )
        self.db.add(assessment)
        await self.db.commit()
        await self.db.refresh(assessment)
        return {
            "assessment_id": assessment.id,
            "project_id": assessment.project_id,
            "composite_risk_score": assessment.composite_risk_score,
            "grade": assessment.grade,
            "var_95_ratio": assessment.var_95_ratio,
            "p90_adjusted_cost_krw": assessment.p90_adjusted_cost_krw,
            "expected_downside_krw": assessment.expected_downside_krw,
            "dimension_scores": dimensions,
            "summary": assessment.summary or "",
            "created_at": assessment.created_at,
        }

    async def get_latest(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
    ) -> dict | None:
        result = await self.db.execute(
            select(UnifiedRiskAssessment)
            .where(
                UnifiedRiskAssessment.tenant_id == tenant_id,
                UnifiedRiskAssessment.project_id == project_id,
            )
            .order_by(UnifiedRiskAssessment.created_at.desc())
            .limit(1)
        )
        assessment = result.scalar_one_or_none()
        if assessment is None:
            return None
        return {
            "assessment_id": assessment.id,
            "project_id": assessment.project_id,
            "composite_risk_score": assessment.composite_risk_score,
            "grade": assessment.grade,
            "var_95_ratio": assessment.var_95_ratio,
            "p90_adjusted_cost_krw": assessment.p90_adjusted_cost_krw,
            "expected_downside_krw": assessment.expected_downside_krw,
            "dimension_scores": list(assessment.dimension_scores_json or []),
            "summary": assessment.summary or "",
            "created_at": assessment.created_at,
        }
