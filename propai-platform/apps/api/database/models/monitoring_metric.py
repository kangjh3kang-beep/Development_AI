"""모니터링 메트릭 모델.

시스템 성능 지표(CPU, 메모리, 디스크, 네트워크)를 시계열로 기록한다.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base


class MonitoringMetric(Base):
    __tablename__ = "monitoring_metrics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    host: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
        comment="수집 대상 호스트명 또는 서비스명",
    )
    metric_name: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        comment="메트릭명 (cpu_usage, memory_usage, disk_io 등)",
    )
    metric_value: Mapped[float] = mapped_column(
        Float, nullable=False,
        comment="측정값",
    )
    unit: Mapped[str] = mapped_column(
        String(30), nullable=False, default="percent",
        comment="단위 (percent, bytes, ms 등)",
    )
    threshold_warning: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="경고 임계값",
    )
    threshold_critical: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="위험 임계값",
    )
    labels: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="추가 레이블 (key=value 쌍, 쉼표 구분)",
    )
    http_status_code: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="HTTP 상태 코드 (엔드포인트 모니터링 시)",
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="메트릭 수집 시각",
    )
