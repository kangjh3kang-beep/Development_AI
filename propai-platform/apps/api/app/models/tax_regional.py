"""세금/지역 모델 — 229개 시군구, 38종 세금코드, 법령변경 추적."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Region(Base):
    """시군구 지역 — 229개 행정구역."""
    __tablename__ = "regions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(10), unique=True, nullable=False, comment="행정구역코드")
    sido_name = Column(String(20), nullable=False)
    sigungu_name = Column(String(50), nullable=False)
    is_capital_area = Column(Boolean, default=False, comment="수도권 여부")
    is_metropolitan = Column(Boolean, default=False, comment="광역시 여부")
    is_adjusted_area = Column(Boolean, default=False, comment="조정대상지역 여부")
    latitude = Column(Numeric(10, 7), nullable=True)
    longitude = Column(Numeric(10, 7), nullable=True)


class RegionTaxRate(Base):
    """지역별 세율 — 시군구별 세금 오버라이드."""
    __tablename__ = "region_tax_rates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id = Column(UUID(as_uuid=True), ForeignKey("regions.id"), nullable=False, index=True)
    tax_code = Column(String(10), nullable=False, comment="A01~D06")
    rate = Column(Numeric(10, 6), nullable=False)
    effective_from = Column(DateTime, nullable=False)
    effective_to = Column(DateTime, nullable=True)
    legal_basis = Column(String(300), nullable=True)


class TaxCode(Base):
    """세금 코드 마스터 — 38종 세금 정의."""
    __tablename__ = "tax_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(10), unique=True, nullable=False, comment="A01~D06")
    name = Column(String(200), nullable=False)
    stage = Column(String(20), nullable=False, comment="acquisition/construction/sale/disposal")
    description = Column(Text, nullable=True)
    default_rate = Column(Numeric(10, 6), nullable=True)
    is_active = Column(Boolean, default=True)


class TaxCalculationResult(Base):
    """세금 계산 결과 — 프로젝트별 38종 일괄 결과."""
    __tablename__ = "tax_calculation_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False, index=True)
    tax_code = Column(String(10), nullable=False)
    base_amount_won = Column(Numeric(20, 0), default=0)
    rate_applied = Column(Numeric(10, 6), nullable=True)
    amount_won = Column(Numeric(20, 0), default=0)
    is_exempt = Column(Boolean, default=False)
    exemption_reason = Column(Text, nullable=True)
    calculated_at = Column(DateTime, default=datetime.utcnow)


class DevelopmentTypeTaxMapping(Base):
    """개발유형별 세금 매핑 — M01~M15 × 38종."""
    __tablename__ = "development_type_tax_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    development_type = Column(String(10), nullable=False, comment="M01~M15")
    tax_code = Column(String(10), nullable=False)
    is_required = Column(Boolean, default=True, comment="필수 여부")
    is_conditional = Column(Boolean, default=False, comment="조건부 여부")
    condition_rule = Column(Text, nullable=True, comment="적용 조건 설명")


class AdjustedArea(Base):
    """조정대상지역 — 지정/해제 이력."""
    __tablename__ = "adjusted_areas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id = Column(UUID(as_uuid=True), ForeignKey("regions.id"), nullable=False, index=True)
    designated_at = Column(DateTime, nullable=False)
    released_at = Column(DateTime, nullable=True)
    gazette_number = Column(String(100), nullable=True, comment="관보 번호")


class TaxExemption(Base):
    """세금 감면 규정."""
    __tablename__ = "tax_exemptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tax_code = Column(String(10), nullable=False)
    exemption_name = Column(String(200), nullable=False)
    exemption_rate = Column(Numeric(6, 4), nullable=False, comment="감면율 0~1")
    conditions = Column(JSON, default={}, comment="적용 조건")
    legal_basis = Column(String(300), nullable=True)
    effective_from = Column(DateTime, nullable=False)
    effective_to = Column(DateTime, nullable=True)


class LawChange(Base):
    """법령변경 추적 — 세법/부동산법 개정 감시."""
    __tablename__ = "law_changes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    law_name = Column(String(300), nullable=False)
    change_type = Column(String(30), nullable=False, comment="enacted/amended/repealed")
    summary = Column(Text, nullable=False)
    affected_tax_codes = Column(JSON, default=[], comment="영향받는 세금 코드")
    effective_date = Column(DateTime, nullable=False)
    gazette_url = Column(Text, nullable=True)
    detected_at = Column(DateTime, default=datetime.utcnow)


class LawChangeAlert(Base):
    """법령변경 알림."""
    __tablename__ = "law_change_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    law_change_id = Column(UUID(as_uuid=True), ForeignKey("law_changes.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    is_read = Column(Boolean, default=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
