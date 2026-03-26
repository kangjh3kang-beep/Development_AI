"""Monte Carlo 시뮬레이션 결과 모델.

10,000회 이상 확률적 시뮬레이션을 실행하여 산출된
NPV/IRR 분포, VaR, Expected Shortfall 등 리스크 지표를 저장한다.
"""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class MonteCarloResult(Base, TenantMixin, TimestampMixin):
    """Monte Carlo 시뮬레이션 결과 테이블."""

    __tablename__ = "monte_carlo_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )

    # 시뮬레이션 메타
    n_simulations: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="시뮬레이션 반복 횟수"
    )
    scenario_name: Mapped[str] = mapped_column(
        String(200), nullable=False, default="기본 시나리오", comment="시나리오명"
    )

    # NPV 백분위수 (원)
    p10_npv: Mapped[float] = mapped_column(
        Float, nullable=False, comment="NPV 10번째 백분위수"
    )
    p50_npv: Mapped[float] = mapped_column(
        Float, nullable=False, comment="NPV 중앙값 (50번째 백분위수)"
    )
    p90_npv: Mapped[float] = mapped_column(
        Float, nullable=False, comment="NPV 90번째 백분위수"
    )

    # IRR 백분위수
    p10_irr: Mapped[float] = mapped_column(
        Float, nullable=False, comment="IRR 10번째 백분위수"
    )
    p50_irr: Mapped[float] = mapped_column(
        Float, nullable=False, comment="IRR 중앙값 (50번째 백분위수)"
    )
    p90_irr: Mapped[float] = mapped_column(
        Float, nullable=False, comment="IRR 90번째 백분위수"
    )

    # 리스크 지표
    var_95: Mapped[float] = mapped_column(
        Float, nullable=False, comment="95% VaR (하위 5번째 백분위, 절대값)"
    )
    expected_shortfall: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Expected Shortfall (VaR 이하 평균 손실)"
    )

    # 통계 요약
    mean_npv: Mapped[float] = mapped_column(
        Float, nullable=False, comment="NPV 평균"
    )
    std_npv: Mapped[float] = mapped_column(
        Float, nullable=False, comment="NPV 표준편차"
    )

    # JSON 상세
    results_summary_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="시뮬레이션 결과 요약 JSON"
    )
    input_params_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="시뮬레이션 입력 파라미터 JSON"
    )
