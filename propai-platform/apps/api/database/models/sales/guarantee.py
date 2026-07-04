"""[T] 분양보증(HUG)/신탁 모델 (2)."""

import uuid
from datetime import date

from sqlalchemy import Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base
from apps.api.database.models.sales._mixins import PKMixin, SiteMixin


class SalesGuaranteePolicy(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_guarantee_policies"
    guarantor: Mapped[str | None] = mapped_column(String(12))   # HUG/SGI/TRUST
    policy_no: Mapped[str | None] = mapped_column(String(60))
    type: Mapped[str | None] = mapped_column(String(20))        # SALE_GUARANTEE/TRUST_MGMT/AGENCY_AFFAIR
    coverage: Mapped[int | None] = mapped_column(Numeric(16, 0))
    period_start: Mapped[date | None] = mapped_column()
    period_end: Mapped[date | None] = mapped_column()
    conditions: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(12), server_default="ACTIVE")


class SalesTrustAccount(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_trust_accounts"
    trustee: Mapped[str | None] = mapped_column(String(80))
    account_alias: Mapped[str | None] = mapped_column(String(80))   # 식별정보는 보안저장/별칭
    purpose: Mapped[str | None] = mapped_column(String(20))         # SALE_PROCEEDS/EXPENSE
    linked_va_pool: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(12), server_default="ACTIVE")
