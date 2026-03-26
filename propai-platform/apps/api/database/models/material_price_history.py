"""Material price history model for v53 cost intelligence."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class MaterialPriceHistory(Base, TenantMixin, TimestampMixin):
    """Persist monthly material price snapshots."""

    __tablename__ = "material_price_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    material_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    material_name: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    region_code: Mapped[str] = mapped_column(String(20), nullable=False, default="KR")
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    source_name: Mapped[str] = mapped_column(String(60), nullable=False, default="kcci-simulated")
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    unit_price_krw: Mapped[float] = mapped_column(Float, nullable=False)
    price_index: Mapped[float] = mapped_column(Float, nullable=False)
    mom_change_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    yoy_change_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
