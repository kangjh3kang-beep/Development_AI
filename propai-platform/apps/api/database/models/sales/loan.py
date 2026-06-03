"""[S] 중도금 집단대출 모델 (3). 자금이체 미수행 — 실행/상환 '기록'만."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Numeric, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base
from apps.api.database.models.sales._mixins import PKMixin, SiteMixin


class SalesLoanProgram(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_loan_programs"
    bank_name: Mapped[str | None] = mapped_column(String(80))
    agreement_no: Mapped[str | None] = mapped_column(String(60))
    total_tranche: Mapped[int | None] = mapped_column(Numeric(16, 0))
    rate_type: Mapped[str | None] = mapped_column(String(8))   # FIXED/VAR
    base_rate: Mapped[float | None] = mapped_column(Numeric(7, 4))
    spread: Mapped[float | None] = mapped_column(Numeric(7, 4))
    guarantee_type: Mapped[str | None] = mapped_column(String(8))  # HUG/HF/NONE
    ltv_cap: Mapped[float | None] = mapped_column(Numeric(7, 4))    # 파라미터(현행 규제 재확인)
    covered_installments: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(12), server_default="ACTIVE")


class SalesLoanAgreement(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_loan_agreements"
    contract_ext_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_contracts_ext.id"))
    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_loan_programs.id"))
    borrower_customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_amount: Mapped[int | None] = mapped_column(Numeric(16, 0))
    status: Mapped[str] = mapped_column(String(12), server_default="APPLIED")  # APPLIED/APPROVED/EXECUTED/REPAID/DEFAULTED


class SalesLoanDisbursement(Base, PKMixin):
    __tablename__ = "sales_loan_disbursements"
    agreement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_loan_agreements.id"))
    installment_seq: Mapped[int | None] = mapped_column(Integer)
    amount: Mapped[int | None] = mapped_column(Numeric(16, 0))
    disbursed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    repaid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
