"""[Q] 청약/당첨/예비/선착순/무순위 모델 (5)."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base
from apps.api.database.models.sales._mixins import PKMixin, SiteMixin, TimestampMixin


class SalesSubscriptionAnnouncement(Base, PKMixin, SiteMixin, TimestampMixin):
    __tablename__ = "sales_subscription_announcements"
    round_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_rounds.id"))
    announce_no: Mapped[str | None] = mapped_column(String(40))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    apply_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    apply_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contract_start: Mapped[date | None] = mapped_column()
    contract_end: Mapped[date | None] = mapped_column()
    rules: Mapped[dict | None] = mapped_column(JSONB)  # 가점만점/특공비율/순위요건/물량(파라미터)
    status: Mapped[str] = mapped_column(String(20), server_default="DRAFT")  # DRAFT/OPEN/DRAWN/CLOSED


class SalesSubscriptionApplication(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_subscription_applications"
    announcement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_subscription_announcements.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    unit_type_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_unit_types.id"))
    supply_class: Mapped[str] = mapped_column(String(10), server_default="GENERAL")  # GENERAL/SPECIAL
    special_type: Mapped[str | None] = mapped_column(String(30))
    rank: Mapped[int | None] = mapped_column(Integer)
    gajeom_score: Mapped[float | None] = mapped_column(Numeric(8, 2))
    channel: Mapped[str | None] = mapped_column(String(30))  # CHEONGYAKHOME/SELF
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    eligibility: Mapped[str] = mapped_column(String(12), server_default="PENDING")  # PENDING/OK/INELIGIBLE
    result: Mapped[str | None] = mapped_column(String(10))  # WIN/RESERVE/FAIL


class SalesSubscriptionWinner(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_subscription_winners"
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_subscription_applications.id"))
    unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_unit_inventory.id"))
    win_type: Mapped[str | None] = mapped_column(String(10))  # GENERAL/SPECIAL/RESERVE/FCFS/UNRANKED
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    contract_due: Mapped[date | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(12), server_default="NOTIFIED")  # NOTIFIED/CONTRACTED/FORFEITED


class SalesSubscriptionReserveQueue(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_subscription_reserve_queue"
    announcement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_subscription_announcements.id"))
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_subscription_applications.id"))
    unit_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reserve_no: Mapped[int | None] = mapped_column(Integer)
    promoted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class SalesUnrankedOffer(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_unranked_offers"
    round_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_unit_inventory.id"))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    channel: Mapped[str | None] = mapped_column(String(30))
    claimed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
