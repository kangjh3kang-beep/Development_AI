"""Phase E underwriting and LP reporting models."""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class InvestmentUnderwriting(Base, TenantMixin, TimestampMixin):
    __tablename__ = "investment_underwritings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    total_cost_krw: Mapped[float] = mapped_column(Float, nullable=False)
    projected_revenue_krw: Mapped[float] = mapped_column(Float, nullable=False)
    acquisition_price_krw: Mapped[float] = mapped_column(Float, nullable=False)
    equity_krw: Mapped[float] = mapped_column(Float, nullable=False)
    debt_krw: Mapped[float] = mapped_column(Float, nullable=False)
    projected_profit_krw: Mapped[float] = mapped_column(Float, nullable=False)
    profit_margin_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    debt_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    equity_multiple: Mapped[float] = mapped_column(Float, nullable=False)
    jeonse_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(30), nullable=False)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_risks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    assumptions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class LPReport(Base, TenantMixin, TimestampMixin):
    __tablename__ = "lp_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    underwriting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investment_underwritings.id"),
        nullable=False,
        index=True,
    )
    report_title: Mapped[str] = mapped_column(String(255), nullable=False)
    report_version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1")
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    distribution_waterfall_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    generated_by: Mapped[str] = mapped_column(String(100), nullable=False, default="system")


class DataRoomDocument(Base, TenantMixin, TimestampMixin):
    __tablename__ = "data_room_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    underwriting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investment_underwritings.id"),
        nullable=False,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(String(60), nullable=False)
    storage_url: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tags_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    parsed_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
