"""Cost escalation persistence model for v53 cost intelligence."""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class CostEscalationSnapshot(Base, TenantMixin, TimestampMixin):
    """Persist project-level PPI escalation analysis results."""

    __tablename__ = "cost_escalation_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    baseline_year: Mapped[int] = mapped_column(Integer, nullable=False)
    target_year: Mapped[int] = mapped_column(Integer, nullable=False)
    construction_duration_months: Mapped[int] = mapped_column(Integer, nullable=False)
    base_construction_cost_krw: Mapped[float] = mapped_column(Float, nullable=False)
    adjusted_cost_krw: Mapped[float] = mapped_column(Float, nullable=False)
    escalation_amount_krw: Mapped[float] = mapped_column(Float, nullable=False)
    overall_escalation_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    material_share_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    labor_share_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    overhead_share_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    contingency_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    contingency_amount_krw: Mapped[float] = mapped_column(Float, nullable=False)
    ppi_source: Mapped[str] = mapped_column(String(60), nullable=False, default="ecos-simulated")
    yearly_projection_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    material_impacts_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    alerts_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    request_assumptions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
