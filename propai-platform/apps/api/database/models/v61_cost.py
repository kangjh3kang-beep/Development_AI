"""v61 BIM 공사비 도메인 ORM 모델.

CostWorkType, MaterialUnitPrice, BimQuantity, CostCalculationSheet,
ProgressBilling, LegalRateHistory, StandardPriceUpdate.

database/models/base.py 의 Base + TenantMixin 을 사용하여
tenant_id 를 자동 포함한다.
BimQuantity 만 TimestampMixin 적용 (updated_at 존재), 나머지는 created_at 직접 정의.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


# ---------------------------------------------------------------------------
# CostWorkType
# ---------------------------------------------------------------------------
class CostWorkType(Base, TenantMixin):
    """공종 분류 (건축/기계/전기/조경/토목 계층)."""

    __tablename__ = "cost_work_types"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True,
    )
    work_code: Mapped[str] = mapped_column(String(20), nullable=False)
    work_name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    work_level: Mapped[int] = mapped_column(Integer, default=1)
    work_category: Mapped[str] = mapped_column(String(50), nullable=False, comment="건축/기계/전기/조경/토목")
    work_division: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_subtotal: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ---------------------------------------------------------------------------
# MaterialUnitPrice
# ---------------------------------------------------------------------------
class MaterialUnitPrice(Base, TenantMixin):
    """자재 단가 (2026 표준품셈 기준)."""

    __tablename__ = "material_unit_prices"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    material_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    material_name: Mapped[str] = mapped_column(String(300), nullable=False)
    spec: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    material_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="재료비 단가")
    labor_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="노무비 단가")
    expense_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="경비 단가")
    price_basis_year: Mapped[int] = mapped_column(Integer, default=2026)
    price_source: Mapped[str] = mapped_column(String(100), default="표준품셈2025")
    region: Mapped[str] = mapped_column(String(50), default="경기도")
    valid_from: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ---------------------------------------------------------------------------
# BimQuantity  (updated_at 존재 -> TimestampMixin 사용)
# ---------------------------------------------------------------------------
class BimQuantity(Base, TenantMixin, TimestampMixin):
    """BIM IFC 물량 산출 (공종코드 매핑)."""

    __tablename__ = "bim_quantities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True,
    )
    ifc_global_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    ifc_object_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ifc_object_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    work_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    floor_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    zone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    quantity_formula: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(50), default="AI_AUTO")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------------------
# CostCalculationSheet
# ---------------------------------------------------------------------------
class CostCalculationSheet(Base, TenantMixin):
    """원가계산서 (법정요율 적용)."""

    __tablename__ = "cost_calculation_sheets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False,
    )
    work_category: Mapped[str] = mapped_column(String(50), nullable=False, comment="건축/기계/전기/조경/토목")
    direct_material_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    indirect_material_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    direct_labor_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    indirect_labor_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    direct_expense: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    industrial_acc_ins: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="산재보험 3.50%")
    employment_ins: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="고용보험 0.90%")
    health_ins: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="건강보험 3.595%")
    pension_ins: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="국민연금 4.75%")
    lcare_ins: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="장기요양 0.4724%")
    retirement_fund: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="퇴직공제부금 2.10%")
    safety_health_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="안전보건관리비 2.07%")
    env_preserve_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="환경보전비 0.16%")
    general_mgmt_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="일반관리비 5.50%")
    profit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="이윤 15.00%")
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="부가가치세 10%")
    total_project_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    applied_rates_snapshot: Mapped[Any] = mapped_column(JSON, default={})
    rates_applied_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    calc_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ---------------------------------------------------------------------------
# ProgressBilling
# ---------------------------------------------------------------------------
class ProgressBilling(Base, TenantMixin):
    """기성 + EVM (SPI/CPI)."""

    __tablename__ = "progress_billings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False,
    )
    billing_no: Mapped[int] = mapped_column(Integer, nullable=False)
    period_from: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    period_to: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    work_entries: Mapped[Any] = mapped_column(JSON, default=[])
    planned_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    earned_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    actual_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    evm_spi: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="SPI = EV/PV")
    evm_cpi: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="CPI = EV/AC")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ---------------------------------------------------------------------------
# LegalRateHistory
# ---------------------------------------------------------------------------
class LegalRateHistory(Base, TenantMixin):
    """법정요율 변경 이력."""

    __tablename__ = "legal_rate_histories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rate_category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    rate_value: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    gov_notice_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gov_notice_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_api: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    applied_to: Mapped[int] = mapped_column(Integer, default=0, comment="적용 프로젝트 수")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ---------------------------------------------------------------------------
# StandardPriceUpdate
# ---------------------------------------------------------------------------
class StandardPriceUpdate(Base, TenantMixin):
    """표준단가 갱신 추적."""

    __tablename__ = "standard_price_updates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    price_period: Mapped[str] = mapped_column(String(20), nullable=False, comment="2026H1, 2026H2 등")
    update_type: Mapped[str] = mapped_column(String(30), nullable=False, comment="품셈/시장단가")
    gov_notice_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    effective_from: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    price_count: Mapped[int] = mapped_column(Integer, default=0)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
