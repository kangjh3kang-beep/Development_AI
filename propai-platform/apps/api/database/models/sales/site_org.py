"""[A] 현장/조직 모델 (8) — sales_sites 외.

주: 스펙의 organizations.id FK는 실제 스키마에 없어 tenants.id 로 교정.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base
from apps.api.database.models.sales._mixins import (
    CreatedByMixin,
    Ltree,
    PKMixin,
    SiteMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class SalesSite(Base, PKMixin, TimestampMixin, SoftDeleteMixin, CreatedByMixin):
    __tablename__ = "sales_sites"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    site_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    site_name: Mapped[str] = mapped_column(String(200), nullable=False)
    development_type: Mapped[str] = mapped_column(String(30), nullable=False)  # APT/OFFICETEL/KNOWLEDGE_CENTER/HOTEL/RETAIL
    status: Mapped[str] = mapped_column(String(20), server_default="PREP")
    phase: Mapped[str | None] = mapped_column(String(20), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SalesSiteProvisioning(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_site_provisioning"
    step: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    log: Mapped[str | None] = mapped_column(String)
    seeded_from: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class SalesSiteConfig(Base, PKMixin):
    __tablename__ = "sales_site_config"
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_sites.id"), unique=True, nullable=False)
    stage_def: Mapped[dict | None] = mapped_column(JSONB)
    installment_schedule: Mapped[dict | None] = mapped_column(JSONB)
    currency: Mapped[str] = mapped_column(String(3), server_default="KRW")
    withholding_rate: Mapped[float] = mapped_column(Numeric(7, 4), server_default="0.0330")
    masking_policy: Mapped[dict | None] = mapped_column(JSONB)
    pricing_mode: Mapped[str] = mapped_column(String(20), server_default="GENERAL")  # GENERAL/CAP
    delegate_pricing: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class SalesOrgCompany(Base, PKMixin, SiteMixin, SoftDeleteMixin):
    __tablename__ = "sales_org_companies"
    company_type: Mapped[str] = mapped_column(String(20))  # AGENCY/SUBAGENCY/DIRECTOR_BIZ
    biz_reg_no: Mapped[str | None] = mapped_column(String(20))
    company_name: Mapped[str | None] = mapped_column(String(200))
    contract_ref: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    withholding_unit: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class SalesOrgNode(Base, PKMixin, SiteMixin, SoftDeleteMixin):
    __tablename__ = "sales_org_nodes"
    node_type: Mapped[str] = mapped_column(String(20))  # AGENCY/SUBAGENCY/GM_DIRECTOR/DIRECTOR/TEAM_LEADER/MEMBER
    path: Mapped[str] = mapped_column(Ltree, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_org_nodes.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_org_companies.id"))
    display_name: Mapped[str | None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class SalesOrgMembershipHistory(Base, PKMixin):
    __tablename__ = "sales_org_membership_history"
    node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_org_nodes.id"))
    action: Mapped[str | None] = mapped_column(String(20))
    from_path: Mapped[str | None] = mapped_column(Ltree)
    to_path: Mapped[str | None] = mapped_column(Ltree)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class SalesOrgContract(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_org_contracts"
    principal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    scope: Mapped[str | None] = mapped_column(String(40))
    fee_basis: Mapped[dict | None] = mapped_column(JSONB)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SalesSiteSummary(Base):
    """시행사 투영 집계(이전 TimescaleDB 하이퍼테이블 → 일반 테이블 + 시간 인덱스)."""

    __tablename__ = "sales_site_summary"
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_sites.id"), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    visitors: Mapped[int | None] = mapped_column(Integer)
    contracts_cnt: Mapped[int | None] = mapped_column(Integer)
    contract_amt: Mapped[int | None] = mapped_column(Numeric(16, 0))
    sold_ratio: Mapped[float | None] = mapped_column(Numeric(7, 4))
    staff_cnt: Mapped[int | None] = mapped_column(Integer)
    commission_total_set: Mapped[int | None] = mapped_column(Numeric(16, 0))
    commission_paid: Mapped[int | None] = mapped_column(Numeric(16, 0))
    commission_due: Mapped[int | None] = mapped_column(Numeric(16, 0))
