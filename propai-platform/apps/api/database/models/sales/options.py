"""[R] 유상옵션 모델 (2)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base
from apps.api.database.models.sales._mixins import PKMixin, SiteMixin


class SalesOptionCatalog(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_option_catalog"
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(20))  # FINISH/SYSTEM/APPLIANCE/STRUCTURE
    price: Mapped[int | None] = mapped_column(Numeric(16, 0))
    vat_applicable: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    applicable_type_ids: Mapped[dict | None] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class SalesContractOption(Base, PKMixin):
    __tablename__ = "sales_contract_options"
    contract_ext_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_contracts_ext.id"))
    option_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_option_catalog.id"))
    qty: Mapped[int] = mapped_column(Integer, server_default="1")
    unit_price: Mapped[int | None] = mapped_column(Numeric(16, 0))
    amount: Mapped[int | None] = mapped_column(Numeric(16, 0))
    vat_amount: Mapped[int] = mapped_column(Numeric(16, 0), server_default="0")
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    status: Mapped[str] = mapped_column(String(12), server_default="SELECTED")
