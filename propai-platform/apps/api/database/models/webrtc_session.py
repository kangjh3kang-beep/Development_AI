"""WebRTC 영상 감리 세션 모델 (G113)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class WebRTCSession(Base, TenantMixin, TimestampMixin):
    __tablename__ = "webrtc_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True,
    )
    initiator_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False,
        comment="세션 개시 사용자 ID",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="waiting",
        comment="세션 상태 (waiting, active, ended, failed)",
    )
    ice_candidates_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="수집된 ICE candidate 목록",
    )
    ice_retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="ICE candidate 전송 재시도 횟수 (B07 패치)",
    )
    sdp_offer: Mapped[str | None] = mapped_column(
        String(5000), nullable=True,
        comment="SDP Offer 문자열",
    )
    sdp_answer: Mapped[str | None] = mapped_column(
        String(5000), nullable=True,
        comment="SDP Answer 문자열",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
