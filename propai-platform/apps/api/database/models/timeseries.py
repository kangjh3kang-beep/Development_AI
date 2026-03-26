"""TimescaleDB 시계열 모델.

IoT 탄소 센서와 드론 탐지 이벤트를 시계열로 저장한다.
Alembic 마이그레이션 후 하이퍼테이블로 변환한다.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base


class IoTCarbonSensor(Base):
    """IoT 탄소 센서 시계열 데이터.

    TimescaleDB 하이퍼테이블로 변환 대상.
    time 컬럼 기준 자동 파티셔닝.
    """
    __tablename__ = "iot_carbon_sensors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    sensor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    co2_ppm: Mapped[float | None] = mapped_column(Float, nullable=True)
    pm25: Mapped[float | None] = mapped_column(Float, nullable=True, comment="PM2.5 (μg/m³)")
    pm10: Mapped[float | None] = mapped_column(Float, nullable=True, comment="PM10 (μg/m³)")
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True, comment="온도 (°C)")
    humidity: Mapped[float | None] = mapped_column(Float, nullable=True, comment="습도 (%)")
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DroneDetectionEvent(Base):
    """드론 하자 탐지 이벤트 시계열.

    TimescaleDB 하이퍼테이블로 변환 대상.
    MQTT(EMQX)로 수신된 실시간 탐지 결과를 저장한다.
    """
    __tablename__ = "drone_detection_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    inspection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("drone_inspections.id"), nullable=True
    )
    defect_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="EMERGENCY | HIGH | MEDIUM | LOW"
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    gps_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_alt: Mapped[float | None] = mapped_column(Float, nullable=True)
