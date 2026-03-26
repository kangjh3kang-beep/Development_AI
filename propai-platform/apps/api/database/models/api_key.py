"""API 키 모델.

테넌트별 외부 API 접근용 키를 관리한다.
키는 SHA-256 해시로 저장하며, 평문은 생성 시 1회만 노출한다.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class APIKey(Base, TenantMixin, TimestampMixin):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="API 키 이름 (식별용)"
    )
    key_prefix: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="키 앞 8자 (pk_xxxxxxxx)"
    )
    key_hash: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, comment="SHA-256 해시된 키"
    )
    scopes: Mapped[list | None] = mapped_column(
        ARRAY(String(100)), nullable=True,
        comment="허용 스코프 (예: avm:read, project:write)",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="만료 시각 (NULL=무기한)"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="마지막 사용 시각"
    )

    # 관계
    tenant = relationship("Tenant", backref="api_keys")
