"""Part F asset intelligence models."""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class AssetIntelligenceSnapshot(Base, TenantMixin, TimestampMixin):
    __tablename__ = "asset_intelligence_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    composite_score: Mapped[float] = mapped_column(nullable=False)
    grade: Mapped[str] = mapped_column(String(20), nullable=False)
    adjusted_value_krw: Mapped[float] = mapped_column(nullable=False)
    component_scores_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)


class CapexOptimizationResult(Base, TenantMixin, TimestampMixin):
    __tablename__ = "capex_optimization_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asset_intelligence_snapshots.id"),
        nullable=False,
        index=True,
    )
    strategy_name: Mapped[str] = mapped_column(String(120), nullable=False)
    expected_roi: Mapped[float] = mapped_column(nullable=False)
    payback_months: Mapped[int] = mapped_column(nullable=False)
    recommendations_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
