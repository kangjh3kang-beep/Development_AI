"""KDX 텔레메트리 로그 모델.

KDX(한국데이터거래소) 실시간 웹훅 수신 및 이벤트 로깅을 위한 테이블.
"""

import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class KDXTelemetryLog(Base, TenantMixin, TimestampMixin):
    __tablename__ = "kdx_telemetry_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 데이터 발생/수집 출처 (예: 'KDX-API', 'KDX-Webhook', 'PropAI-Spider')
    source: Mapped[str] = mapped_column(String(100), nullable=False)

    # 이벤트 형식 (예: 'transaction', 'listing_update', 'market_anomaly')
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # 데이터 페이로드 (JSON)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    # 처리 상태 (예: 'pending', 'processed', 'failed')
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
