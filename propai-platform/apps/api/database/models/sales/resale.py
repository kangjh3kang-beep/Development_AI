"""[V] 실거래신고/전매제한 모델 (3)."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base
from apps.api.database.models.sales._mixins import PKMixin, SiteMixin


class SalesRealtxReport(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_realtx_reports"
    contract_ext_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_contracts_ext.id"))
    provider: Mapped[str] = mapped_column(String(16), server_default="MOLIT_IRTS")
    report_no: Mapped[str | None] = mapped_column(String(60))
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[date | None] = mapped_column()  # 신고기한(파라미터, 현행 법령 재확인)
    status: Mapped[str] = mapped_column(String(12), server_default="PENDING")  # PENDING/SUBMITTED/ACCEPTED/CORRECTED
    payload: Mapped[dict | None] = mapped_column(JSONB)


class SalesResaleRestriction(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_resale_restrictions"
    unit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    round_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    restriction_type: Mapped[str | None] = mapped_column(String(30))
    start_at: Mapped[date | None] = mapped_column()
    months: Mapped[int | None] = mapped_column(Integer)  # 기간(파라미터)
    basis_note: Mapped[str | None] = mapped_column(String(200))


class SalesResaleTransfer(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_resale_transfers"
    contract_ext_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_contracts_ext.id"))
    from_customer: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    to_customer: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    transfer_type: Mapped[str | None] = mapped_column(String(12))  # RESALE/NAME_CHANGE
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    allowed: Mapped[bool | None] = mapped_column(Boolean)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(200))
