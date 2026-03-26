"""테넌트 모델.

멀티테넌트 SaaS 구조의 최상위 엔티티.
encryption_key_id는 AWS KMS 키 참조용.
"""

import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="free", nullable=False)
    encryption_key_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="AWS KMS 암호화 키 ID"
    )

    # 관계
    users = relationship("User", back_populates="tenant", lazy="selectin")
    projects = relationship("Project", back_populates="tenant", lazy="selectin")
