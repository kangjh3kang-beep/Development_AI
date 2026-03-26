"""Part F tenant experience models."""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class TenantTicket(Base, TenantMixin, TimestampMixin):
    __tablename__ = "tenant_tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    unit_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    feedback_text: Mapped[str] = mapped_column(Text, nullable=False)
    requested_action: Mapped[str | None] = mapped_column(Text, nullable=True)


class TenantSentimentScore(Base, TenantMixin, TimestampMixin):
    __tablename__ = "tenant_sentiment_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    tenant_ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_tickets.id"), nullable=True, index=True
    )
    sentiment_score: Mapped[float] = mapped_column(nullable=False)
    sentiment_label: Mapped[str] = mapped_column(String(20), nullable=False)
    ai_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class TenantFinancialHealth(Base, TenantMixin, TimestampMixin):
    __tablename__ = "tenant_financial_health"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    occupancy_rate: Mapped[float] = mapped_column(nullable=False)
    arrears_ratio: Mapped[float] = mapped_column(nullable=False)
    churn_risk_score: Mapped[float] = mapped_column(nullable=False)
    health_grade: Mapped[str] = mapped_column(String(20), nullable=False)
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
