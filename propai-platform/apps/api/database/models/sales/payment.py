"""[U] 수납/가상계좌/연체이자 모델 (3). 자금이체 미수행 — 입금 '기록·대사'만."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base
from apps.api.database.models.sales._mixins import PKMixin, SiteMixin


class SalesVirtualAccount(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_virtual_accounts"
    contract_ext_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_contracts_ext.id"))
    bank: Mapped[str | None] = mapped_column(String(40))
    va_number_enc: Mapped[str | None] = mapped_column(String(255))  # HMAC 블라인드 인덱스(평문 미저장)
    holder: Mapped[str | None] = mapped_column(String(120))
    pool_ref: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # 신탁/대리사무 계좌풀
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    status: Mapped[str] = mapped_column(String(12), server_default="ACTIVE")


class SalesPayment(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_payments"
    contract_ext_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_contracts_ext.id"))
    installment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_contract_installments.id"))
    method: Mapped[str | None] = mapped_column(String(12))  # VA/TRANSFER/CARD/LOAN
    amount: Mapped[int | None] = mapped_column(Numeric(16, 0))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    matched: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    raw_ref: Mapped[str | None] = mapped_column(String(120))


class SalesOverdueInterest(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_overdue_interest"
    installment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_contract_installments.id"))
    overdue_days: Mapped[int | None] = mapped_column(Integer)
    rate: Mapped[float | None] = mapped_column(Numeric(7, 4))
    amount: Mapped[int | None] = mapped_column(Numeric(16, 0))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
