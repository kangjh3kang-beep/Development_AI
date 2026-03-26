"""법적 감사 추적 모델.

불변 감사 로그. 규제 준수를 위해 삭제/수정 불가 (INSERT-ONLY).
"""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class LegalAuditTrail(Base, TenantMixin, TimestampMixin):
    __tablename__ = "legal_audit_trail"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="대상 엔티티 타입 (예: project, escrow)"
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True,
        comment="대상 엔티티 ID"
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="수행 동작 (create | update | delete | approve | reject)"
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="수행자 ID"
    )
    before_state: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="변경 전 상태"
    )
    after_state: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="변경 후 상태"
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="사유")
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
