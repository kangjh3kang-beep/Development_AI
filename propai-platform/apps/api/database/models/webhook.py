"""웹훅 구독 모델.

테넌트가 특정 이벤트(프로젝트 완료, AVM 결과 등)에 대해 웹훅 URL을 등록한다.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class Webhook(Base, TenantMixin, TimestampMixin):
    __tablename__ = "webhooks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(
        String(2000), nullable=False, comment="웹훅 수신 URL"
    )
    secret: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="HMAC-SHA256 서명 시크릿"
    )
    events: Mapped[list | None] = mapped_column(
        ARRAY(String(100)), nullable=True,
        comment="구독 이벤트 목록 (예: project.completed, avm.estimated)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="웹훅 설명"
    )

    # 관계
    deliveries = relationship("WebhookDelivery", back_populates="webhook", lazy="selectin")
