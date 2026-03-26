"""공사현장 안전 위반 기록 모델 (G116)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class SafetyViolation(Base, TenantMixin, TimestampMixin):
    __tablename__ = "safety_violations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True,
    )
    camera_id: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="RTSP 카메라 식별자",
    )
    violation_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="위반 유형 (helmet_off, vest_off 등)",
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False,
        comment="YOLOv8 감지 신뢰도 (0.0~1.0)",
    )
    bbox_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="감지 바운딩 박스 {x, y, w, h}",
    )
    frame_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="위반 캡처 프레임 저장 경로",
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
