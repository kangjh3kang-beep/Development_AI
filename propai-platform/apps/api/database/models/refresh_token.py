"""리프레시 토큰 모델.

JWT 리프레시 토큰을 DB에 저장하여 토큰 무효화(revoke)를 지원한다.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, TimestampMixin


class RefreshToken(Base, TimestampMixin):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, comment="SHA-256 해시된 토큰"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="만료 시각"
    )
    is_revoked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="무효화 여부"
    )
    device_info: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="접속 디바이스/IP 정보"
    )

    # 관계
    user = relationship("User", backref="refresh_tokens")
