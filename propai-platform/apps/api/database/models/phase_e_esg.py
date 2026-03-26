"""Phase E ESG, carbon, and GRESB models."""

import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class ESGReport(Base, TenantMixin, TimestampMixin):
    __tablename__ = "esg_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    reporting_period: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    environmental_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    social_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    governance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    disclosures_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class CarbonFootprint(Base, TenantMixin, TimestampMixin):
    __tablename__ = "carbon_footprints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    scope1_tco2e: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    scope2_tco2e: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    scope3_tco2e: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    intensity_kgco2e_per_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_year: Mapped[int | None] = mapped_column(nullable=True)
    breakdown_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class GRESBAssessment(Base, TenantMixin, TimestampMixin):
    __tablename__ = "gresb_assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    assessment_year: Mapped[int] = mapped_column(nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating: Mapped[str | None] = mapped_column(String(10), nullable=True)
    gaps_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    action_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
