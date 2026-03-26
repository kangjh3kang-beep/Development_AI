"""Phase E lease abstraction and IFRS16 models."""

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class LeaseAbstraction(Base, TenantMixin, TimestampMixin):
    __tablename__ = "lease_abstractions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    source_document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    lease_type: Mapped[str] = mapped_column(String(60), nullable=False)
    area_sqm: Mapped[float] = mapped_column(Float, nullable=False)
    deposit_krw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    monthly_rent_krw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    start_date: Mapped[datetime | None] = mapped_column(nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(nullable=True)
    critical_terms_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    abstraction_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class LeaseIFRS16Schedule(Base, TenantMixin, TimestampMixin):
    __tablename__ = "lease_ifrs16_schedules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    lease_abstraction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lease_abstractions.id"),
        nullable=False,
        index=True,
    )
    discount_rate: Mapped[float] = mapped_column(Float, nullable=False)
    lease_term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    rou_asset_krw: Mapped[float] = mapped_column(Float, nullable=False)
    lease_liability_krw: Mapped[float] = mapped_column(Float, nullable=False)
    payment_schedule_json: Mapped[list] = mapped_column(JSON, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
