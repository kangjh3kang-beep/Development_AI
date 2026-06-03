"""[G] 수수료 2단 (9) + [H] 모델하우스 데스크 (9) + [I] 하네스 (2) 모델."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base
from apps.api.database.models.sales._mixins import PKMixin, SiteMixin


# ───────── [G] 수수료 2단 ─────────
class SalesCommissionMaster(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_commission_master"
    basis: Mapped[str] = mapped_column(String(24))  # PER_CONTRACT_FIXED/RATE_OF_PRICE/TOTAL_POOL
    fixed_amount: Mapped[int | None] = mapped_column(Numeric(16, 0))
    rate: Mapped[float | None] = mapped_column(Numeric(7, 4))
    pool_total: Mapped[int | None] = mapped_column(Numeric(16, 0))
    set_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    locked: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class SalesCommissionDistribution(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_commission_distribution"
    master_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_commission_master.id"))
    distributor_node_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_org_nodes.id"))
    target_node_type: Mapped[str | None] = mapped_column(String(20))
    target_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    basis: Mapped[str] = mapped_column(String(8))  # FIXED/RATE
    value: Mapped[float | None] = mapped_column(Numeric(16, 4))
    parent_distribution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    set_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer, server_default="1")


class SalesCommissionEvent(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_commission_events"
    contract_ext_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_contracts_ext.id"))
    base_amount: Mapped[int | None] = mapped_column(Numeric(16, 0))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    status: Mapped[str] = mapped_column(String(12), server_default="PENDING")  # PENDING/SPLIT/REVERSED


class SalesCommissionSplit(Base, PKMixin):
    __tablename__ = "sales_commission_splits"
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_commission_events.id"))
    node_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_org_nodes.id"))
    node_type: Mapped[str | None] = mapped_column(String(20))
    basis: Mapped[str | None] = mapped_column(String(8))
    rate: Mapped[float | None] = mapped_column(Numeric(7, 4))
    amount: Mapped[int | None] = mapped_column(Numeric(16, 0))


class SalesCommissionClaim(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_commission_claims"
    split_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_commission_splits.id"))
    claimant_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    claimed_amount: Mapped[int | None] = mapped_column(Numeric(16, 0))
    status: Mapped[str] = mapped_column(String(20), server_default="CLAIMED")
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class SalesCommissionApproval(Base, PKMixin):
    __tablename__ = "sales_commission_approvals"
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_commission_claims.id"))
    approver_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decision: Mapped[str | None] = mapped_column(String(12))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String)


class SalesCommissionPayout(Base, PKMixin):
    __tablename__ = "sales_commission_payouts"
    # claim_id nullable: 지급은 claim 승인 또는 마일스톤 스케줄(claim 없음) 2소스
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_commission_claims.id"), nullable=True)
    gross: Mapped[int | None] = mapped_column(Numeric(16, 0))
    withholding: Mapped[int | None] = mapped_column(Numeric(16, 0))
    net: Mapped[int | None] = mapped_column(Numeric(16, 0))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    method: Mapped[str | None] = mapped_column(String(20))


class SalesCommissionClawback(Base, PKMixin):
    __tablename__ = "sales_commission_clawbacks"
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_commission_events.id"))
    reason: Mapped[str | None] = mapped_column(String(40))
    reversed_amount: Mapped[int | None] = mapped_column(Numeric(16, 0))
    reversed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class SalesCommissionSettlement(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_commission_settlements"
    period: Mapped[str | None] = mapped_column(String(20))
    total_gross: Mapped[int | None] = mapped_column(Numeric(16, 0))
    total_withholding: Mapped[int | None] = mapped_column(Numeric(16, 0))
    total_net: Mapped[int | None] = mapped_column(Numeric(16, 0))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String(20))


# ───────── [H] 모델하우스 데스크 ─────────
class MhDesk(Base, PKMixin, SiteMixin):
    __tablename__ = "mh_desks"
    desk_name: Mapped[str | None] = mapped_column(String(80))
    kiosk_token: Mapped[str | None] = mapped_column(String(80))
    channel_id: Mapped[str | None] = mapped_column(String(120))


class MhVisitor(Base, PKMixin, SiteMixin):
    __tablename__ = "mh_visitors"
    desk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("mh_desks.id"))
    name: Mapped[str | None] = mapped_column(String(120))
    phone_e164: Mapped[str | None] = mapped_column(String(20))
    party_size: Mapped[int | None] = mapped_column(Integer)
    visit_purpose: Mapped[str | None] = mapped_column(String(60))
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    revisit: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class MhVisitConsent(Base, PKMixin):
    __tablename__ = "mh_visit_consents"
    visitor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mh_visitors.id"))
    consent_type: Mapped[str | None] = mapped_column(String(20))
    items: Mapped[dict | None] = mapped_column(JSONB)
    agreed: Mapped[bool | None] = mapped_column(Boolean)
    esign_uri: Mapped[str | None] = mapped_column(String)
    agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MhStaffMatch(Base, PKMixin):
    __tablename__ = "mh_staff_match"
    visitor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mh_visitors.id"))
    input_type: Mapped[str | None] = mapped_column(String(10))
    raw_input: Mapped[str | None] = mapped_column(String)
    matched_staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_staff.id"))
    score: Mapped[float | None] = mapped_column(Numeric(7, 4))
    status: Mapped[str | None] = mapped_column(String(20))
    matched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class MhNotification(Base, PKMixin, SiteMixin):
    __tablename__ = "mh_notifications"
    visitor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    target_staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    channel: Mapped[str | None] = mapped_column(String(12))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String(20))


class MhVisitStat(Base):
    """방문 통계(이전 TimescaleDB → 일반 테이블 + 시간 인덱스)."""

    __tablename__ = "mh_visit_stats"
    site_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    visitors: Mapped[int | None] = mapped_column(Integer)
    by_hour: Mapped[dict | None] = mapped_column(JSONB)
    by_channel: Mapped[dict | None] = mapped_column(JSONB)
    converted: Mapped[int | None] = mapped_column(Integer)


class MhInventoryItem(Base, PKMixin, SiteMixin):
    __tablename__ = "mh_inventory_items"
    item_name: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(30))
    unit: Mapped[str | None] = mapped_column(String(20))
    stock_qty: Mapped[int | None] = mapped_column(Integer)
    min_qty: Mapped[int | None] = mapped_column(Integer)


class MhInventoryTxn(Base, PKMixin):
    __tablename__ = "mh_inventory_txns"
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mh_inventory_items.id"))
    txn_type: Mapped[str | None] = mapped_column(String(8))
    qty: Mapped[int | None] = mapped_column(Integer)
    staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    memo: Mapped[str | None] = mapped_column(String)


class SalesWorkLog(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_work_logs"
    author_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    log_date: Mapped[date | None] = mapped_column()
    content: Mapped[str | None] = mapped_column(String)
    metrics: Mapped[dict | None] = mapped_column(JSONB)


# ───────── [I] 하네스 ─────────
class SalesHarnessOutbox(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_harness_outbox"
    event_type: Mapped[str | None] = mapped_column(String(40))
    aggregate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(12), server_default="PENDING")


class SalesHarnessSubscription(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_harness_subscriptions"
    event_type: Mapped[str | None] = mapped_column(String(40))
    projection_target: Mapped[str | None] = mapped_column(String(60))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
