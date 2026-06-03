"""[D] 계약 (6) + [E] 고객 CRM (6) + [F] 광고 (5) 모델.

주: 스펙의 contracts.id FK는 실제 스키마에 'contracts' 테이블이 없어 평문 UUID(base_contract_id)로 교정.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base
from apps.api.database.models.sales._mixins import PKMixin, SiteMixin, SoftDeleteMixin


# ───────── [D] 청약/계약 ─────────
class SalesApplication(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_applications"
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_unit_inventory.id"))
    round_id: Mapped[uuid.UUID | None] = mapped_column()
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    channel: Mapped[str | None] = mapped_column(String(30))
    priority: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[str | None] = mapped_column(String(20))


class SalesContractExt(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_contracts_ext"
    base_contract_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # FK 미지정: contracts 테이블 부재
    unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_unit_inventory.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    member_node_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_org_nodes.id"))
    round_id: Mapped[uuid.UUID | None] = mapped_column()
    stage: Mapped[str] = mapped_column(String(20), server_default="RESERVED")  # RESERVED/SIGNED/MIDDLE/BALANCE
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_price: Mapped[int | None] = mapped_column(Numeric(16, 0))
    status: Mapped[str] = mapped_column(String(20), server_default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class SalesContractInstallment(Base, PKMixin):
    __tablename__ = "sales_contract_installments"
    contract_ext_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_contracts_ext.id"))
    seq: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str | None] = mapped_column(String(20))
    due_date: Mapped[date | None] = mapped_column()
    amount: Mapped[int | None] = mapped_column(Numeric(16, 0))
    paid_amount: Mapped[int] = mapped_column(Numeric(16, 0), server_default="0")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SalesContractDocument(Base, PKMixin):
    __tablename__ = "sales_contract_documents"
    contract_ext_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_contracts_ext.id"))
    doc_type: Mapped[str | None] = mapped_column(String(40))
    file_uri: Mapped[str | None] = mapped_column(String)
    e_sign_ref: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class SalesContractChange(Base, PKMixin):
    __tablename__ = "sales_contract_changes"
    contract_ext_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_contracts_ext.id"))
    change_type: Mapped[str | None] = mapped_column(String(20))
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String)
    prev_snapshot: Mapped[dict | None] = mapped_column(JSONB)


class SalesEcontractLink(Base, PKMixin):
    __tablename__ = "sales_econtract_links"
    contract_ext_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_contracts_ext.id"))
    provider: Mapped[str] = mapped_column(String(20), server_default="MOLIT_IRTS")
    external_id: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str | None] = mapped_column(String(20))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ───────── [E] 고객 CRM ─────────
class SalesCustomer(Base, PKMixin, SiteMixin, SoftDeleteMixin):
    __tablename__ = "sales_customers"
    name: Mapped[str | None] = mapped_column(String(120))
    phone_e164: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), server_default="LEAD")
    grade: Mapped[str | None] = mapped_column(String(10))
    assigned_node_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_org_nodes.id"))
    first_visit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class SalesCustomerConsent(Base, PKMixin):
    __tablename__ = "sales_customer_consents"
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_customers.id"))
    consent_type: Mapped[str | None] = mapped_column(String(20))  # REQUIRED/MARKETING/THIRD_PARTY
    purpose: Mapped[str | None] = mapped_column(String)
    items: Mapped[dict | None] = mapped_column(JSONB)
    retention: Mapped[str | None] = mapped_column(String(40))
    agreed: Mapped[bool | None] = mapped_column(Boolean)
    esign_uri: Mapped[str | None] = mapped_column(String)
    agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SalesCustomerAssignment(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_customer_assignments"
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_customers.id"))
    staff_node_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_org_nodes.id"))
    assign_type: Mapped[str | None] = mapped_column(String(20))  # DESIGNATED/AUTO/REASSIGN
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class SalesCustomerConsultation(Base, PKMixin):
    __tablename__ = "sales_customer_consultations"
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_customers.id"))
    staff_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    consulted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    channel: Mapped[str | None] = mapped_column(String(20))
    summary: Mapped[str | None] = mapped_column(String)
    next_action: Mapped[str | None] = mapped_column(String(80))
    next_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SalesCustomerCall(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_customer_calls"
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    staff_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    direction: Mapped[str | None] = mapped_column(String(10))
    phone_e164: Mapped[str | None] = mapped_column(String(20))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration: Mapped[int | None] = mapped_column(Integer)
    recording_uri: Mapped[str | None] = mapped_column(String)


class SalesCustomerGradeLog(Base, PKMixin):
    __tablename__ = "sales_customer_grade_log"
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_customers.id"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    from_grade: Mapped[str | None] = mapped_column(String(10))
    to_grade: Mapped[str | None] = mapped_column(String(10))
    by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


# ───────── [F] 광고 ─────────
class SalesAdCampaign(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_ad_campaigns"
    name: Mapped[str | None] = mapped_column(String(120))
    period_start: Mapped[date | None] = mapped_column()
    period_end: Mapped[date | None] = mapped_column()
    budget: Mapped[int | None] = mapped_column(Numeric(16, 0))
    objective: Mapped[str | None] = mapped_column(String(60))


class SalesAdChannel(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_ad_channels"
    channel_type: Mapped[str | None] = mapped_column(String(30))
    vendor: Mapped[str | None] = mapped_column(String(80))
    utm: Mapped[dict | None] = mapped_column(JSONB)
    tracking_phone: Mapped[str | None] = mapped_column(String(20))


class SalesAdSpend(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_ad_spend"
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_ad_campaigns.id"))
    channel_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_ad_channels.id"))
    spend_date: Mapped[date | None] = mapped_column()
    amount: Mapped[int | None] = mapped_column(Numeric(16, 0))


class SalesAdLead(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_ad_leads"
    channel_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_ad_channels.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    utm: Mapped[dict | None] = mapped_column(JSONB)
    converted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class SalesAdCompliance(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_ad_compliance"
    channel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    check_type: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str | None] = mapped_column(String(20))
    evidence_uri: Mapped[str | None] = mapped_column(String)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
