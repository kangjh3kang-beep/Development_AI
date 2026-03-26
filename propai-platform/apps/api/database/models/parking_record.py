"""스마트 주차 기록 모델 (G119)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class ParkingRecord(Base, TenantMixin, TimestampMixin):
    __tablename__ = "parking_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True,
    )
    camera_id: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="주차장 카메라 식별자",
    )
    plate_number: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="인식된 차량 번호판",
    )
    raw_ocr_text: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="OCR 원본 출력 (정규식 검증 전)",
    )
    zone: Mapped[str | None] = mapped_column(
        String(30), nullable=True,
        comment="주차 구역 (A-1, B-2 등)",
    )
    event_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="entry",
        comment="이벤트 유형 (entry, exit)",
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
