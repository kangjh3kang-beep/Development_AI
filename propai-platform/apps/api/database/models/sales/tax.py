"""[X] 세무(지급명세서/세금계산서) 모델 (2). 산출/기록만 — 홈택스 제출은 어댑터+승인."""

import uuid
from datetime import datetime

from sqlalchemy import Numeric, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base
from apps.api.database.models.sales._mixins import PKMixin, SiteMixin


class SalesTaxInvoice(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_tax_invoices"
    direction: Mapped[str | None] = mapped_column(String(8))    # ISSUE/RECEIVE
    counterparty_biz_no: Mapped[str | None] = mapped_column(String(20))
    supply_amount: Mapped[int | None] = mapped_column(Numeric(16, 0))
    vat_amount: Mapped[int | None] = mapped_column(Numeric(16, 0))
    item: Mapped[str | None] = mapped_column(String(120))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nts_ref: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[str | None] = mapped_column(String(12))


class SalesWithholdingStatement(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_withholding_statements"
    payee_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payee_biz_no: Mapped[str | None] = mapped_column(String(20))
    period: Mapped[str | None] = mapped_column(String(10))
    income_type: Mapped[str | None] = mapped_column(String(10))  # BIZ_3_3/EARNED
    gross: Mapped[int | None] = mapped_column(Numeric(16, 0))
    withholding: Mapped[int | None] = mapped_column(Numeric(16, 0))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nts_ref: Mapped[str | None] = mapped_column(String(60))
