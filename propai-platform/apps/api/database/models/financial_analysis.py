"""재무 분석 모델.

NPV, IRR, 회수 기간 등 사업성 분석 결과를 저장한다.
"""

import uuid

from sqlalchemy import Float, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class FinancialAnalysis(Base, TenantMixin, TimestampMixin):
    __tablename__ = "financial_analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    npv: Mapped[float] = mapped_column(Float, nullable=False, comment="순현재가치 (원)")
    irr: Mapped[float] = mapped_column(Float, nullable=False, comment="내부수익률")
    payback_period_months: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="회수 기간 (월)"
    )
    total_investment: Mapped[float] = mapped_column(Float, nullable=False, comment="총 투자비")
    total_revenue: Mapped[float] = mapped_column(Float, nullable=False, comment="총 수입")
    risk_score: Mapped[float] = mapped_column(
        Float, nullable=False, comment="리스크 점수 (0~1)"
    )
    scenario_name: Mapped[str | None] = mapped_column(nullable=True, comment="시나리오명")
    assumptions: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="분석 가정"
    )
    cash_flow_yearly: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="연도별 현금 흐름"
    )

    # 관계
    project = relationship("Project", back_populates="financial_analyses")
