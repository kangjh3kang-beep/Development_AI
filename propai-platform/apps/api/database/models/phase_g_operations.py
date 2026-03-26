"""Part G auction intelligence and contractor network models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class AuctionListing(Base, TenantMixin, TimestampMixin):
    """Persist auction listing data and deterministic analysis outputs."""

    __tablename__ = "auction_listings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    auction_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    case_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    court_name: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    property_type: Mapped[str] = mapped_column(String(40), nullable=False)
    appraised_value_krw: Mapped[float] = mapped_column(Float, nullable=False)
    minimum_bid_krw: Mapped[float] = mapped_column(Float, nullable=False)
    bid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    auction_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="scheduled"
    )
    analysis_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Contractor(Base, TenantMixin, TimestampMixin):
    """Persist contractor and specialist network data."""

    __tablename__ = "contractors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    business_number: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    specialties_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
