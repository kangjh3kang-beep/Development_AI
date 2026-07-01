"""[C] 동/호 (7) + [P] 분양가/차수 (9) 모델."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base
from apps.api.database.models.sales._mixins import PKMixin, SiteMixin, SoftDeleteMixin


# ───────── [C] 동/호 ─────────
class SalesUnitBlock(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_unit_blocks"
    block_name: Mapped[str] = mapped_column(String(40))
    floors: Mapped[int | None] = mapped_column(Integer)
    units_per_floor: Mapped[int | None] = mapped_column(Integer)


class SalesUnitType(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_unit_types"
    type_name: Mapped[str] = mapped_column(String(40))
    exclusive_area: Mapped[float | None] = mapped_column(Numeric(12, 4))
    supply_area: Mapped[float | None] = mapped_column(Numeric(12, 4))
    contract_area: Mapped[float | None] = mapped_column(Numeric(12, 4))
    rooms: Mapped[int | None] = mapped_column(Integer)
    baths: Mapped[int | None] = mapped_column(Integer)


class SalesUnitInventory(Base, PKMixin, SiteMixin, SoftDeleteMixin):
    __tablename__ = "sales_unit_inventory"
    block_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_unit_blocks.id"))
    type_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_unit_types.id"))
    dong: Mapped[str | None] = mapped_column(String(20))
    ho: Mapped[str | None] = mapped_column(String(20))
    floor: Mapped[int | None] = mapped_column(Integer)
    line: Mapped[str | None] = mapped_column(String(10))
    aspect: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), server_default="AVAILABLE")  # AVAILABLE/HOLD/APPLIED/CONTRACTED/CANCELLED
    hold_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    contract_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    round_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class SalesUnitPriceTable(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_unit_price_table"
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_unit_inventory.id"))
    round_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    base_price: Mapped[int | None] = mapped_column(Numeric(16, 0))
    option_price: Mapped[int] = mapped_column(Numeric(16, 0), server_default="0")
    premium: Mapped[int] = mapped_column(Numeric(16, 0), server_default="0")
    total_price: Mapped[int | None] = mapped_column(Numeric(16, 0))
    price_mode: Mapped[str] = mapped_column(String(12), server_default="WEIGHTED")  # WEIGHTED/FIXED
    override_price: Mapped[int | None] = mapped_column(Numeric(16, 0))
    override_reason: Mapped[str | None] = mapped_column(String)
    override_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    override_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    breakdown_ref: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class SalesUnitHold(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_unit_holds"
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_unit_inventory.id"))
    staff_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    held_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SalesUnitStatusLog(Base):
    """동호 상태 전이 로그(이전 TimescaleDB → 일반 테이블 + 시간 인덱스)."""

    __tablename__ = "sales_unit_status_log"
    unit_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, server_default=text("now()"))
    site_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class SalesUnitGeneration(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_unit_generation"
    source_type: Mapped[str] = mapped_column(String(20))  # OUTLINE/DRAWING_UPLOAD/DESIGN_AI
    params: Mapped[dict | None] = mapped_column(JSONB)
    source_ref: Mapped[str | None] = mapped_column(String)
    status: Mapped[str | None] = mapped_column(String(20))
    generated_count: Mapped[int | None] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


# ───────── [P] 분양가/차수 ─────────
class SalesDevTypeProfile(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_dev_type_profile"
    development_type: Mapped[str] = mapped_column(String(30))
    sale_method: Mapped[str] = mapped_column(String(20), server_default="OPEN")  # SUBSCRIPTION/OPEN
    area_basis: Mapped[dict | None] = mapped_column(JSONB)
    unit_price_basis: Mapped[str | None] = mapped_column(String(12))
    vat_policy: Mapped[dict | None] = mapped_column(JSONB)
    naming_rule: Mapped[dict | None] = mapped_column(JSONB)
    attributes: Mapped[dict | None] = mapped_column(JSONB)


class SalesRound(Base, PKMixin, SiteMixin, SoftDeleteMixin):
    __tablename__ = "sales_rounds"
    round_no: Mapped[int | None] = mapped_column(Integer)
    round_type: Mapped[str | None] = mapped_column(String(24))  # LANDOWNER_MEMBER/MEMBER_1ST/.../GENERAL
    sale_type: Mapped[str | None] = mapped_column(String(10))   # UNION/GENERAL
    name: Mapped[str | None] = mapped_column(String(80))
    sort_order: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class SalesPriceBase(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_price_base"
    round_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_rounds.id"))
    type_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_unit_types.id"))
    basis: Mapped[str | None] = mapped_column(String(10))  # PER_AREA/PER_UNIT
    base_unit_price: Mapped[int | None] = mapped_column(Numeric(16, 0))
    base_area_kind: Mapped[str | None] = mapped_column(String(12))
    round_factor: Mapped[float] = mapped_column(Numeric(7, 4), server_default="1")


class SalesPriceWeight(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_price_weights"
    round_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_rounds.id"))
    dimension: Mapped[str | None] = mapped_column(String(10))  # FLOOR/LINE/ASPECT/GROUP/CUSTOM
    match_key: Mapped[str | None] = mapped_column(String(40))
    basis: Mapped[str | None] = mapped_column(String(8))       # RATE/FIXED
    value: Mapped[float | None] = mapped_column(Numeric(16, 4))
    priority: Mapped[int] = mapped_column(Integer, server_default="0")


class SalesPriceGroup(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_price_groups"
    group_name: Mapped[str | None] = mapped_column(String(80))
    selector: Mapped[dict | None] = mapped_column(JSONB)
    basis: Mapped[str | None] = mapped_column(String(8))
    value: Mapped[float | None] = mapped_column(Numeric(16, 4))
    priority: Mapped[int] = mapped_column(Integer, server_default="0")


class SalesPriceGroupMember(Base, PKMixin):
    __tablename__ = "sales_price_group_members"
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_price_groups.id"))
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_unit_inventory.id"))


class SalesPriceComposition(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_price_composition"
    round_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales_rounds.id"))
    component_type: Mapped[str | None] = mapped_column(String(10))  # LAND/BUILD/CUSTOM
    label: Mapped[str | None] = mapped_column(String(80))
    basis: Mapped[str | None] = mapped_column(String(8))
    value: Mapped[float | None] = mapped_column(Numeric(16, 4))
    vat_applicable: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    sort_order: Mapped[int | None] = mapped_column(Integer)


class SalesUnitPriceBreakdown(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_unit_price_breakdown"
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales_unit_inventory.id"))
    round_id: Mapped[uuid.UUID | None] = mapped_column()
    component_type: Mapped[str | None] = mapped_column(String(10))
    label: Mapped[str | None] = mapped_column(String(80))
    amount: Mapped[int | None] = mapped_column(Numeric(16, 0))
    vat_amount: Mapped[int] = mapped_column(Numeric(16, 0), server_default="0")


class SalesPriceGenerationLog(Base, PKMixin, SiteMixin):
    __tablename__ = "sales_price_generation_log"
    round_id: Mapped[uuid.UUID | None] = mapped_column()
    params_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    generated_count: Mapped[int | None] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
