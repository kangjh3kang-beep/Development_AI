"""디지털 트윈 이상 감지 기록 모델 (G114)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class DigitalTwinAnomaly(Base, TenantMixin, TimestampMixin):
    __tablename__ = "digital_twin_anomalies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True,
    )
    sensor_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="센서 유형 (temperature, vibration, humidity, power 등)",
    )
    anomaly_score: Mapped[float] = mapped_column(
        Float, nullable=False,
        comment="IsolationForest 이상 점수 (-1=이상, 1=정상)",
    )
    is_anomaly: Mapped[bool] = mapped_column(
        nullable=False, default=False,
    )
    data_points_used: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="모델 학습에 사용된 데이터 포인트 수",
    )
    feature_values_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="입력 피처 벡터",
    )
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="info",
        comment="심각도 (info, warning, critical)",
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
