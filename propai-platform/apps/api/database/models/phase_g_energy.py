"""Part G KEPCO cache and energy certification models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class KepcoRateCache(Base, TenantMixin, TimestampMixin):
    __tablename__ = "kepco_rate_cache"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    contract_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    energy_rate_krw_per_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    base_charge_krw_per_kw: Mapped[float] = mapped_column(Float, nullable=False)
    fuel_adjustment_krw_per_kwh: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    effective_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class EnergyCertificationRecord(Base, TenantMixin, TimestampMixin):
    __tablename__ = "energy_certifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    energy_grade: Mapped[str] = mapped_column(String(20), nullable=False)
    zeb_grade: Mapped[str] = mapped_column(String(20), nullable=False)
    annual_energy_demand_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    annual_renewable_generation_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    energy_independence_rate: Mapped[float] = mapped_column(Float, nullable=False)
    bems_saving_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    bems_saving_kwh: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recommendations_json: Mapped[list | None] = mapped_column(JSON, nullable=True)


class EnergyCertScore(Base, TenantMixin, TimestampMixin):
    __tablename__ = "energy_cert_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    certification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("energy_certifications.id"),
        nullable=False,
        index=True,
    )
    score_name: Mapped[str] = mapped_column(String(60), nullable=False)
    score_value: Mapped[float] = mapped_column(Float, nullable=False)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
