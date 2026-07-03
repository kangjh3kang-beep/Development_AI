"""[W] 수수료 분할지급/유보 모델 (2). 기존 [G] splits/payouts 확장."""

import uuid
from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base
from apps.api.database.models.sales._mixins import PKMixin


class SalesCommissionPayoutSchedule(Base, PKMixin):
    __tablename__ = "sales_commission_payout_schedule"
    split_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_commission_splits.id"))
    milestone: Mapped[str | None] = mapped_column(String(16))   # CONTRACT/MIDDLE/BALANCE/OCCUPANCY
    ratio: Mapped[float | None] = mapped_column(Numeric(7, 4))   # 마일스톤 비율(파라미터)
    planned_at: Mapped[date | None] = mapped_column()
    paid_payout_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(12), server_default="PLANNED")  # PLANNED/PAID/CANCELLED


class SalesCommissionHoldback(Base, PKMixin):
    __tablename__ = "sales_commission_holdback"
    split_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_commission_splits.id"))
    reason: Mapped[str | None] = mapped_column(String(20))      # CANCEL_RISK/DEFECT/POLICY
    amount: Mapped[int | None] = mapped_column(Numeric(16, 0))
    release_condition: Mapped[dict | None] = mapped_column(JSONB)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
