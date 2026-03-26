"""Phase E climate risk and insurance models."""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class ClimateRiskAssessment(Base, TenantMixin, TimestampMixin):
    __tablename__ = "climate_risk_assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    construction_period_months: Mapped[int] = mapped_column(Integer, nullable=False)
    flood_risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    heat_risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    overall_risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    annual_expected_loss_krw: Mapped[float] = mapped_column(Float, nullable=False)
    risk_factors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    mitigation_tips: Mapped[list | None] = mapped_column(JSON, nullable=True)
    scenario_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class InsuranceRecommendation(Base, TenantMixin, TimestampMixin):
    __tablename__ = "insurance_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    climate_risk_assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("climate_risk_assessments.id"),
        nullable=False,
        index=True,
    )
    coverage_type: Mapped[str] = mapped_column(String(80), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    annual_premium_estimate_krw: Mapped[float] = mapped_column(Float, nullable=False)
    coverage_limit_krw: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    broker_notes_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
