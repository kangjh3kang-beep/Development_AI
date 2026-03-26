"""알림 규칙 모델.

모니터링 메트릭 기반 알림 조건 및 발송 대상을 정의한다.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class AlertRule(Base, TenantMixin, TimestampMixin):
    __tablename__ = "alert_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(
        String(200), nullable=False,
        comment="알림 규칙 이름",
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="규칙 설명",
    )
    metric_name: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        comment="감시 대상 메트릭명 (monitoring_metrics.metric_name과 매칭)",
    )
    condition: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="조건 연산자 (gt, gte, lt, lte, eq, ne)",
    )
    threshold: Mapped[float] = mapped_column(
        Float, nullable=False,
        comment="알림 발동 임계값",
    )
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="warning",
        comment="심각도 (info, warning, critical)",
    )
    evaluation_window_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=300,
        comment="평가 윈도우 (초). 이 기간 내 조건 충족 시 알림 발동",
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
        comment="연속 위반 횟수 도달 시 알림 발동",
    )
    notification_channels: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment='알림 채널 설정 (예: {"slack": "#ops", "email": ["admin@..."]})',
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="규칙 활성 여부",
    )
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="마지막 알림 발동 시각",
    )
    cooldown_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=600,
        comment="알림 재발동 방지 쿨다운 (초)",
    )
