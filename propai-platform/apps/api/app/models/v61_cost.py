"""v61 BIM 공사비 도메인 ORM 모델 — CostWorkType, MaterialUnitPrice, BimQuantity,
CostCalculationSheet, ProgressBilling, LegalRateHistory, StandardPriceUpdate."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID

from app.core.database import Base


class CostWorkType(Base):
    """공종 분류 (건축/기계/전기/조경/토목 계층)."""
    __tablename__ = "cost_work_types"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    work_code = Column(String(20), nullable=False)
    work_name = Column(String(200), nullable=False)
    parent_code = Column(String(20), nullable=True)
    work_level = Column(Integer, default=1)
    work_category = Column(String(50), nullable=False, comment="건축/기계/전기/조경/토목")
    work_division = Column(String(50), nullable=True)
    unit = Column(String(20), nullable=True)
    is_subtotal = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class MaterialUnitPrice(Base):
    """자재 단가 (2026 표준품셈 기준)."""
    __tablename__ = "material_unit_prices"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    material_code = Column(String(50), nullable=False, index=True)
    material_name = Column(String(300), nullable=False)
    spec = Column(String(300), nullable=True)
    unit = Column(String(20), nullable=False)
    material_price = Column(Numeric(18, 2), default=0, comment="재료비 단가")
    labor_price = Column(Numeric(18, 2), default=0, comment="노무비 단가")
    expense_price = Column(Numeric(18, 2), default=0, comment="경비 단가")
    price_basis_year = Column(Integer, default=2026)
    price_source = Column(String(100), default="표준품셈2025")
    region = Column(String(50), default="경기도")
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    is_current = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BimQuantity(Base):
    """BIM IFC 물량 산출 (공종코드 매핑)."""
    __tablename__ = "bim_quantities"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    ifc_global_id = Column(String(100), nullable=True, index=True)
    ifc_object_type = Column(String(100), nullable=True)
    ifc_object_name = Column(String(300), nullable=True)
    work_code = Column(String(20), nullable=True)
    floor_level = Column(String(50), nullable=True)
    zone = Column(String(100), nullable=True)
    quantity = Column(Numeric(18, 4), default=0)
    unit = Column(String(20), nullable=True)
    quantity_formula = Column(Text, nullable=True)
    extraction_method = Column(String(50), default="AI_AUTO")
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CostCalculationSheet(Base):
    """원가계산서 (법정요율 적용)."""
    __tablename__ = "cost_calculation_sheets"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    work_category = Column(String(50), nullable=False, comment="건축/기계/전기/조경/토목")
    direct_material_cost = Column(Numeric(18, 2), default=0)
    indirect_material_cost = Column(Numeric(18, 2), default=0)
    direct_labor_cost = Column(Numeric(18, 2), default=0)
    indirect_labor_cost = Column(Numeric(18, 2), default=0)
    direct_expense = Column(Numeric(18, 2), default=0)
    industrial_acc_ins = Column(Numeric(18, 2), default=0, comment="산재보험 3.50%")
    employment_ins = Column(Numeric(18, 2), default=0, comment="고용보험 0.90%")
    health_ins = Column(Numeric(18, 2), default=0, comment="건강보험 3.595%")
    pension_ins = Column(Numeric(18, 2), default=0, comment="국민연금 4.75%")
    lcare_ins = Column(Numeric(18, 2), default=0, comment="장기요양 0.4724%")
    retirement_fund = Column(Numeric(18, 2), default=0, comment="퇴직공제부금 2.10%")
    safety_health_cost = Column(Numeric(18, 2), default=0, comment="안전보건관리비 2.07%")
    env_preserve_cost = Column(Numeric(18, 2), default=0, comment="환경보전비 0.16%")
    general_mgmt_cost = Column(Numeric(18, 2), default=0, comment="일반관리비 5.50%")
    profit_amount = Column(Numeric(18, 2), default=0, comment="이윤 15.00%")
    vat_amount = Column(Numeric(18, 2), default=0, comment="부가가치세 10%")
    total_project_cost = Column(Numeric(18, 2), default=0)
    applied_rates_snapshot = Column(JSON, default={})
    rates_applied_date = Column(Date, nullable=True)
    calc_at = Column(DateTime, default=datetime.utcnow)


class ProgressBilling(Base):
    """기성 + EVM (SPI/CPI)."""
    __tablename__ = "progress_billings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    billing_no = Column(Integer, nullable=False)
    period_from = Column(Date, nullable=True)
    period_to = Column(Date, nullable=True)
    work_entries = Column(JSON, default=[])
    planned_value = Column(Numeric(18, 2), default=0)
    earned_value = Column(Numeric(18, 2), default=0)
    actual_cost = Column(Numeric(18, 2), default=0)
    evm_spi = Column(Float, nullable=True, comment="SPI = EV/PV")
    evm_cpi = Column(Float, nullable=True, comment="CPI = EV/AC")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class LegalRateHistory(Base):
    """법정요율 변경 이력."""
    __tablename__ = "legal_rate_histories"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rate_category = Column(String(50), nullable=False, index=True)
    rate_value = Column(Numeric(8, 6), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    gov_notice_no = Column(String(100), nullable=True)
    gov_notice_url = Column(Text, nullable=True)
    source_api = Column(String(200), nullable=True)
    applied_to = Column(Integer, default=0, comment="적용 프로젝트 수")
    created_at = Column(DateTime, default=datetime.utcnow)


class StandardPriceUpdate(Base):
    """표준단가 갱신 추적."""
    __tablename__ = "standard_price_updates"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    price_period = Column(String(20), nullable=False, comment="2026H1, 2026H2 등")
    update_type = Column(String(30), nullable=False, comment="품셈/시장단가")
    gov_notice_no = Column(String(100), nullable=True)
    effective_from = Column(Date, nullable=True)
    price_count = Column(Integer, default=0)
    source_url = Column(Text, nullable=True)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
