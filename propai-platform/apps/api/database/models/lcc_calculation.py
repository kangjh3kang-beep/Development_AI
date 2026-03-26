"""LCC 생애주기비용 산정 모델 (ISO 15686-5).

40년 분석기간 기준 건물 생애주기 비용 산출 결과를 저장한다.
초기 건설비, 유지보수비, 에너지비, 대수선비의 NPV를 포함한다.
"""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class LccCalculation(Base, TenantMixin, TimestampMixin):
    """LCC 생애주기비용 산정 결과 모델."""

    __tablename__ = "lcc_calculations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )

    # 분석 파라미터
    analysis_period_years: Mapped[int] = mapped_column(
        Integer, default=40, nullable=False, comment="분석 기간 (년)"
    )
    nominal_rate: Mapped[float] = mapped_column(
        Float, nullable=False, comment="명목할인율"
    )
    inflation_rate: Mapped[float] = mapped_column(
        Float, nullable=False, comment="물가상승률"
    )
    real_discount_rate: Mapped[float] = mapped_column(
        Float, nullable=False, comment="실질할인율 (Fisher 공식)"
    )

    # 비용 입력값
    initial_construction_cost: Mapped[float] = mapped_column(
        Float, nullable=False, comment="초기 건설비 (원)"
    )
    annual_maintenance_cost: Mapped[float] = mapped_column(
        Float, nullable=False, comment="연간 유지보수비 (원)"
    )
    annual_energy_cost: Mapped[float] = mapped_column(
        Float, nullable=False, comment="연간 에너지비 (원)"
    )
    energy_escalation_rate: Mapped[float] = mapped_column(
        Float, nullable=False, comment="에너지 가격 상승률"
    )

    # NPV 산출 결과
    npv_total: Mapped[float] = mapped_column(
        Float, nullable=False, comment="총 NPV (원)"
    )
    npv_construction: Mapped[float] = mapped_column(
        Float, nullable=False, comment="초기 건설비 NPV (원)"
    )
    npv_maintenance: Mapped[float] = mapped_column(
        Float, nullable=False, comment="유지보수비 NPV (원)"
    )
    npv_energy: Mapped[float] = mapped_column(
        Float, nullable=False, comment="에너지비 NPV (원)"
    )
    npv_repair: Mapped[float] = mapped_column(
        Float, nullable=False, comment="대수선비 NPV (원)"
    )

    # 상세 JSON 데이터
    repair_schedule_json: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="대수선 주기 스케줄"
    )
    alternatives_json: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="대안 비교 결과"
    )
    yearly_cashflow_json: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="연도별 현금흐름"
    )
