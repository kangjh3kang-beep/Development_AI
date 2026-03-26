"""KDX 시장 지표 모델.

KDX에서 수집된 시계열 기반의 지역별 부동산 시장 거래 지표, 변동성 데이터 테이블.
"""

import uuid

from sqlalchemy import Float, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class KDXMarketMetric(Base, TenantMixin, TimestampMixin):
    __tablename__ = "kdx_market_metrics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # 지역 코드 (법정동/행정동 코드 또는 KDX 전용 지역 규격)
    region_code: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    # 지표 유형 (예: 'avg_price_per_sqm', 'transaction_volume', 'liquidity_index')
    metric_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # 지표 값
    value: Mapped[float] = mapped_column(Float, nullable=False)

    # 통화 정보 (예: 'KRW', 'USD', 'INDEX')
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="KRW")
