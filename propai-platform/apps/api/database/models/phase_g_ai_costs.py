"""Part G AI cost budget models."""

import uuid

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class AICostBudget(Base, TenantMixin, TimestampMixin):
    __tablename__ = "ai_cost_budgets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    monthly_budget_usd: Mapped[float] = mapped_column(Float, nullable=False)
    alert_threshold_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
