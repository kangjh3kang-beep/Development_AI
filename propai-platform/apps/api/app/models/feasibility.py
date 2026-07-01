"""수지분석 고도화 v2 모델 — 22개 테이블 (프로젝트/입력/결과/조합원/일정)."""

import uuid
from datetime import datetime

from app.models.base import AuditMixin, SoftDeleteMixin
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base

# ── 수지분석 프로젝트 ──

class FeasibilityProject(SoftDeleteMixin, AuditMixin, Base):
    """수지분석 프로젝트 — 1개 부동산 개발 사업."""
    __tablename__ = "feasibility_projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    development_type = Column(String(10), nullable=False, comment="M01~M15")
    region_code = Column(String(10), nullable=True, comment="시군구 코드")
    land_category = Column(String(20), nullable=True, comment="forest/farmland/land")
    status = Column(String(30), default="draft", comment="draft/active/archived")
    config = Column(JSON, default={}, comment="프로젝트 설정")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FeasibilityVersion(SoftDeleteMixin, Base):
    """수지분석 버전 — 입력/결과 스냅샷."""
    __tablename__ = "feasibility_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feasibility_project_id = Column(
        UUID(as_uuid=True), ForeignKey("feasibility_projects.id"), nullable=False, index=True
    )
    version_number = Column(Integer, nullable=False, default=1)
    label = Column(String(200), nullable=True, comment="사용자 레이블")
    is_current = Column(Boolean, default=True)
    parent_version_id = Column(UUID(as_uuid=True), nullable=True, comment="이전 버전 FK")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_fv_project_version", "feasibility_project_id", "version_number", unique=True),
    )


# ── 수입 ──

class RevenueInput(Base):
    """수입 입력 — 분양/임대/부대수입 총괄."""
    __tablename__ = "feasibility_revenue_inputs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False, index=True)
    total_households = Column(Integer, default=0, comment="총 세대수")
    total_gfa_sqm = Column(Numeric(14, 2), default=0, comment="총 연면적 m²")
    sale_ratio = Column(Numeric(5, 4), default=1.0, comment="분양 비율 (0~1)")
    rental_ratio = Column(Numeric(5, 4), default=0.0, comment="임대 비율 (0~1)")
    avg_sale_price_per_pyeong = Column(Numeric(14, 0), default=0, comment="평균 분양가 원/평")
    avg_rental_deposit_per_pyeong = Column(Numeric(14, 0), default=0, comment="평균 임대보증금 원/평")
    avg_monthly_rent_per_pyeong = Column(Numeric(10, 0), default=0, comment="평균 월세 원/평")
    config = Column(JSON, default={})


class RevenueItem(Base):
    """수입 항목 — 동/호별 또는 용도별 세부."""
    __tablename__ = "feasibility_revenue_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    revenue_input_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_revenue_inputs.id"), nullable=False)
    category = Column(String(50), nullable=False, comment="sale/rental/ancillary/union_allotment")
    sub_category = Column(String(100), nullable=True, comment="아파트/상가/오피스텔 등")
    unit_count = Column(Integer, default=0)
    area_sqm = Column(Numeric(12, 2), default=0)
    unit_price_won = Column(Numeric(16, 0), default=0)
    total_won = Column(Numeric(20, 0), default=0)
    note = Column(Text, nullable=True)


# ── 토지비 ──

class LandCostInput(Base):
    """토지비 입력."""
    __tablename__ = "feasibility_land_cost_inputs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False, index=True)
    total_land_area_sqm = Column(Numeric(14, 2), default=0)
    official_land_price_per_sqm = Column(Numeric(14, 0), default=0, comment="공시지가 원/m²")
    land_price_multiplier = Column(Numeric(6, 4), default=1.0, comment="감정가/공시지가 배율")
    land_category = Column(String(20), default="land", comment="forest/farmland/land")
    house_count = Column(Integer, default=0, comment="주택수 (취득세 중과 판단)")
    is_adjusted_area = Column(Boolean, default=False)
    config = Column(JSON, default={})


class LandCostItem(Base):
    """토지비 항목 — 매입비, 보상비, 취득세 등."""
    __tablename__ = "feasibility_land_cost_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    land_cost_input_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_land_cost_inputs.id"), nullable=False)
    category = Column(String(50), nullable=False, comment="purchase/compensation/tax/conversion")
    item_name = Column(String(200), nullable=False)
    amount_won = Column(Numeric(20, 0), default=0)
    rate = Column(Numeric(10, 6), nullable=True, comment="적용 세율/비율")
    note = Column(Text, nullable=True)


# ── 공사비 ──

class ConstructionCostInput(Base):
    """공사비 입력."""
    __tablename__ = "feasibility_construction_cost_inputs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False, index=True)
    total_gfa_sqm = Column(Numeric(14, 2), default=0)
    direct_cost_per_sqm = Column(Numeric(12, 0), default=0, comment="직접공사비 원/m²")
    indirect_cost_ratio = Column(Numeric(5, 4), default=0.15, comment="간접공사비 비율")
    cost_index_year = Column(Integer, nullable=True, comment="건설물가지수 기준연도")
    cost_index_value = Column(Numeric(8, 4), default=1.0, comment="건설물가지수 보정계수")
    config = Column(JSON, default={})


class ConstructionCostItem(Base):
    """공사비 항목 — 직접/간접/설계/감리/부대."""
    __tablename__ = "feasibility_construction_cost_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    construction_cost_input_id = Column(
        UUID(as_uuid=True), ForeignKey("feasibility_construction_cost_inputs.id"), nullable=False
    )
    category = Column(String(50), nullable=False, comment="direct/indirect/design/supervision/ancillary")
    item_name = Column(String(200), nullable=False)
    amount_won = Column(Numeric(20, 0), default=0)
    unit_price_won = Column(Numeric(14, 0), nullable=True)
    quantity = Column(Numeric(14, 2), nullable=True)
    note = Column(Text, nullable=True)


# ── 금융비 ──

class FinanceCostInput(Base):
    """금융비 입력 — 브릿지/본PF/중도금 3단계."""
    __tablename__ = "feasibility_finance_cost_inputs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False, index=True)
    bridge_loan_amount = Column(Numeric(20, 0), default=0, comment="브릿지론 원")
    bridge_rate = Column(Numeric(6, 4), default=0.06, comment="브릿지 금리")
    bridge_months = Column(Integer, default=12, comment="브릿지 기간 (월)")
    pf_loan_amount = Column(Numeric(20, 0), default=0, comment="본PF 원")
    pf_rate = Column(Numeric(6, 4), default=0.045, comment="본PF 금리")
    pf_months = Column(Integer, default=30, comment="본PF 기간 (월)")
    midpay_loan_amount = Column(Numeric(20, 0), default=0, comment="중도금 대출 원")
    midpay_rate = Column(Numeric(6, 4), default=0.04, comment="중도금 금리")
    midpay_months = Column(Integer, default=18, comment="중도금 기간 (월)")
    config = Column(JSON, default={})


class FinanceCostItem(Base):
    """금융비 항목 — 이자/수수료/보증료."""
    __tablename__ = "feasibility_finance_cost_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    finance_cost_input_id = Column(
        UUID(as_uuid=True), ForeignKey("feasibility_finance_cost_inputs.id"), nullable=False
    )
    category = Column(String(50), nullable=False, comment="bridge/pf/midpay/guarantee/fee")
    item_name = Column(String(200), nullable=False)
    principal_won = Column(Numeric(20, 0), default=0)
    rate = Column(Numeric(6, 4), nullable=True)
    months = Column(Integer, nullable=True)
    amount_won = Column(Numeric(20, 0), default=0)
    note = Column(Text, nullable=True)


# ── 기타 비용 ──

class OtherCostInput(Base):
    """기타경비 입력."""
    __tablename__ = "feasibility_other_cost_inputs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False, index=True)
    marketing_cost_won = Column(Numeric(20, 0), default=0, comment="분양홍보비")
    management_cost_won = Column(Numeric(20, 0), default=0, comment="사업관리비")
    reserve_cost_won = Column(Numeric(20, 0), default=0, comment="예비비")
    config = Column(JSON, default={})


class OtherCostItem(Base):
    """기타경비 항목."""
    __tablename__ = "feasibility_other_cost_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    other_cost_input_id = Column(
        UUID(as_uuid=True), ForeignKey("feasibility_other_cost_inputs.id"), nullable=False
    )
    item_name = Column(String(200), nullable=False)
    amount_won = Column(Numeric(20, 0), default=0)
    note = Column(Text, nullable=True)


# ── 제세공과금 ──

class TaxCostItem(Base):
    """제세공과금 항목 — 38종 세금 개별 기록."""
    __tablename__ = "feasibility_tax_cost_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False, index=True)
    stage = Column(String(20), nullable=False, comment="acquisition/construction/sale/disposal")
    tax_code = Column(String(10), nullable=False, comment="A01~D06")
    tax_name = Column(String(100), nullable=False)
    base_amount_won = Column(Numeric(20, 0), default=0, comment="과세표준")
    rate = Column(Numeric(10, 6), nullable=True)
    calculated_amount_won = Column(Numeric(20, 0), default=0)
    is_applicable = Column(Boolean, default=True)
    note = Column(Text, nullable=True)


# ── 수지 합산 결과 ──

class FeasibilitySummary(Base):
    """수지분석 합산 결과 + 등급 판정."""
    __tablename__ = "feasibility_summaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False, unique=True)
    total_revenue_won = Column(Numeric(20, 0), default=0)
    total_land_cost_won = Column(Numeric(20, 0), default=0)
    total_construction_cost_won = Column(Numeric(20, 0), default=0)
    total_finance_cost_won = Column(Numeric(20, 0), default=0)
    total_other_cost_won = Column(Numeric(20, 0), default=0)
    total_tax_cost_won = Column(Numeric(20, 0), default=0)
    total_cost_won = Column(Numeric(20, 0), default=0)
    net_profit_won = Column(Numeric(20, 0), default=0)
    profit_rate = Column(Numeric(8, 4), default=0, comment="수익률 %")
    roi = Column(Numeric(8, 4), default=0, comment="투자수익률 %")
    irr = Column(Numeric(8, 4), nullable=True, comment="내부수익률 %")
    npv_won = Column(Numeric(20, 0), nullable=True, comment="순현재가치")
    grade = Column(String(2), default="F", comment="A/B/C/D/E/F")
    calculated_at = Column(DateTime, default=datetime.utcnow)


# ── 조합원 ──

class UnionMember(Base):
    """조합원 정보 (M01/M02/M04 등 조합 사업용)."""
    __tablename__ = "feasibility_union_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feasibility_project_id = Column(
        UUID(as_uuid=True), ForeignKey("feasibility_projects.id"), nullable=False, index=True
    )
    name = Column(String(100), nullable=True)
    parcel_area_sqm = Column(Numeric(12, 2), default=0)
    appraised_value_won = Column(Numeric(20, 0), default=0, comment="감정가")
    proportional_value_won = Column(Numeric(20, 0), default=0, comment="비례율적용가")
    allotment_area_sqm = Column(Numeric(12, 2), default=0, comment="배정 면적")
    contribution_won = Column(Numeric(20, 0), default=0, comment="분담금")
    refund_won = Column(Numeric(20, 0), default=0, comment="환급금")


class UnionContribution(Base):
    """조합원별 분담금 상세."""
    __tablename__ = "feasibility_union_contributions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_union_members.id"), nullable=False)
    item_name = Column(String(200), nullable=False)
    amount_won = Column(Numeric(20, 0), default=0)
    phase = Column(String(20), nullable=True, comment="phase0~phase4")


# ── Phase 일정/자금 ──

class PhaseSchedule(Base):
    """Phase별 일정 (Phase0 토지매입 ~ Phase4 청산)."""
    __tablename__ = "feasibility_phase_schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False, index=True)
    phase_code = Column(String(10), nullable=False, comment="phase0~phase4")
    phase_name = Column(String(100), nullable=False)
    start_month = Column(Integer, default=0, comment="시작 월 (0-based)")
    duration_months = Column(Integer, default=0)
    note = Column(Text, nullable=True)


class PhaseFunding(Base):
    """Phase별 자금 조달/집행."""
    __tablename__ = "feasibility_phase_fundings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False, index=True)
    phase_code = Column(String(10), nullable=False)
    funding_source = Column(String(100), nullable=False, comment="자기자본/브릿지/PF/분양대금")
    amount_won = Column(Numeric(20, 0), default=0)
    direction = Column(String(10), nullable=False, comment="inflow/outflow")


# ── 민감도/몬테카를로 결과 ──

class SensitivityResult(Base):
    """민감도 분석 결과."""
    __tablename__ = "feasibility_sensitivity_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False, index=True)
    scenario_name = Column(String(100), nullable=False)
    variable_name = Column(String(100), nullable=False)
    delta_pct = Column(Numeric(6, 2), nullable=False, comment="변동률 %")
    result_profit_rate = Column(Numeric(8, 4), default=0)
    result_npv_won = Column(Numeric(20, 0), default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class MonteCarloResult(Base):
    """몬테카를로 시뮬레이션 결과 요약."""
    __tablename__ = "feasibility_monte_carlo_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False, index=True)
    n_simulations = Column(Integer, default=10_000)
    variables = Column(JSON, default=[], comment="시뮬레이션 변수 목록")
    mean_npv_won = Column(Numeric(20, 0), default=0)
    std_npv_won = Column(Numeric(20, 0), default=0)
    p5_npv_won = Column(Numeric(20, 0), default=0, comment="5% 백분위")
    p50_npv_won = Column(Numeric(20, 0), default=0, comment="중앙값")
    p95_npv_won = Column(Numeric(20, 0), default=0, comment="95% 백분위")
    probability_positive = Column(Numeric(6, 4), default=0, comment="NPV>0 확률")
    convergence_ratio = Column(Numeric(8, 6), nullable=True, comment="σ/μ 수렴비")
    histogram_data = Column(JSON, default=[], comment="히스토그램 빈 데이터")
    created_at = Column(DateTime, default=datetime.utcnow)


# ── 모듈 설정 ──

class ModuleConfig(Base):
    """개발유형별 모듈 설정 (M01~M15)."""
    __tablename__ = "feasibility_module_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False, index=True)
    module_code = Column(String(10), nullable=False, comment="M01~M15")
    module_name = Column(String(100), nullable=False)
    enabled_blocks = Column(JSON, default=[], comment="활성화된 블록 목록")
    params = Column(JSON, default={}, comment="모듈 파라미터")


# ── 수지분석 비교 ──

class FeasibilityComparison(Base):
    """수지분석 비교 — 2개 버전/프로젝트 비교 결과."""
    __tablename__ = "feasibility_comparisons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    version_a_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False)
    version_b_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_versions.id"), nullable=False)
    diff_data = Column(JSON, default={}, comment="항목별 차이")
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
