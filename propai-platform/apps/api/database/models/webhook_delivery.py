"""웹훅 전송 이력 모델.

각 웹훅 전송 시도의 요청/응답 기록을 저장한다.
재시도 로직의 기반 데이터.
"""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, TimestampMixin


class WebhookDelivery(Base, TimestampMixin):
    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    webhook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("webhooks.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="이벤트 유형 (예: project.completed)"
    )
    payload: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="전송 페이로드"
    )
    status_code: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="HTTP 응답 코드"
    )
    response_body: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="응답 본문 (최대 1KB)"
    )
    duration_ms: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="응답 시간 (ms)"
    )
    attempt: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, comment="시도 횟수"
    )
    success: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="전송 성공 여부"
    )

    # 관계
    webhook = relationship("Webhook", back_populates="deliveries")
