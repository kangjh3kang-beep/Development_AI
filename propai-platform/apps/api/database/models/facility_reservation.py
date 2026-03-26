"""공유시설 예약 모델 (G115)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class FacilityReservation(Base, TenantMixin, TimestampMixin):
    __tablename__ = "facility_reservations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True,
    )
    facility_name: Mapped[str] = mapped_column(
        String(200), nullable=False,
        comment="시설 이름 (회의실 A, 피트니스 센터 등)",
    )
    reserved_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False,
        comment="예약 사용자 ID",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="confirmed",
        comment="예약 상태 (confirmed, cancelled, completed)",
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="예약 시작 시각",
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="예약 종료 시각",
    )
    notes: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
