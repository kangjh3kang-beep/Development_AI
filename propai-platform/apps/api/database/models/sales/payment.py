"""[U] 수납/가상계좌/연체이자 모델 (3). 자금이체 미수행 — 입금 '기록·대사'만."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    # 입금 상태머신: PENDING(대기) / MATCHED(대사완료) / UNMATCHED(미대사·수동큐) / REVERSED(취소·반려).
    # 기존 matched(bool) 와 1:1 동기화한다(matched=True ⇔ status=MATCHED). 같은 입금을 두 번
    # 매칭하지 못하도록(이중 충당 방지) MATCHED/REVERSED 는 종료상태로 본다.
    status: Mapped[str] = mapped_column(String(12), server_default="PENDING")
    # 회차지정 충당: 특정 회차(seq)부터 우선 충당하고 싶을 때 지정. None 이면 미납 회차를 seq 오름차순 충당.
    preferred_installment_seq: Mapped[int | None] = mapped_column(Integer)
    # 다회차 충당 내역: 한 입금이 여러 회차에 분산 충당되면 회차별 실제 충당액을 여기 기록한다
    # ([{installment_id, applied_amount}, ...]). 취소(reverse) 시 이 기록대로 회차별 정확히 되돌린다.
    # None(구행)이면 단일 installment_id 폴백(결제 전액 1회차 차감) — 무회귀.
    allocations: Mapped[list | None] = mapped_column(JSONB)
    # ★멱등 DB 게이트: 같은 현장의 같은 거래참조(raw_ref)는 1건만(동시 webhook 재시도 이중 충당 차단).
    #   partial UNIQUE(WHERE raw_ref IS NOT NULL) — raw_ref 없는 수동 입금은 중복 허용. 정본은 035
    #   마이그레이션(uq_pay_site_raw_ref)이며, 여기 선언은 ORM 메타데이터 정합용(같은 이름·술어).
    __table_args__ = (
        Index("uq_pay_site_raw_ref", "site_id", "raw_ref", unique=True,
              postgresql_where=text("raw_ref IS NOT NULL")),
    )


class SalesOverdueInterest(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_overdue_interest"
    installment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_contract_installments.id"))
    overdue_days: Mapped[int | None] = mapped_column(Integer)
    rate: Mapped[float | None] = mapped_column(Numeric(7, 4))
    amount: Mapped[int | None] = mapped_column(Numeric(16, 0))
    # 산정 기준일(날짜). 같은 회차를 같은 날 두 번 산정해도 1건만 남도록 멱등키로 쓴다
    # (site_id, installment_id, calc_date) UNIQUE → 일배치 재실행 시 행 중복누적 방지.
    calc_date: Mapped[date | None] = mapped_column(Date)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
