"""사용자 모델.

JWT 인증과 RBAC 역할을 관리한다.
비밀번호는 bcrypt로 해싱한다(routers/auth.py `_hash_password`).

회원 시스템(2026-07 확정 정책):
- `deleted_at IS NOT NULL` = 탈퇴(소프트 삭제) 계정 — 모든 인증 경로에서 차단.
- 이메일 유니크는 **활성 계정에만** 적용(부분 유니크 인덱스 `ux_users_email_active`)
  → 탈퇴 30일 유예 후 동일 이메일 재가입 허용(확정 정책 §7-1).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class User(Base, TenantMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        # 활성(미탈퇴) 계정에만 이메일 유니크 — 탈퇴 계정은 30일 유예 후 재가입 허용.
        Index(
            "ux_users_email_active",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # 로그인 등 이메일 단독 조회용 일반 인덱스(부분 인덱스는 조건 불일치 시 미사용).
        Index("ix_users_email", "email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="viewer", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    oauth_provider: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="OAuth 제공자 (kakao, google 등)"
    )
    oauth_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="OAuth 제공자 사용자 ID"
    )

    # ── 회원 계정 수명주기(2026-07 회원 시스템) ──
    email_verified: Mapped[bool] = mapped_column(
        default=False, nullable=False, server_default=text("false"),
        comment="이메일 인증 완료 여부",
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="탈퇴(소프트 삭제) 시각 — NULL=활성. NOT NULL이면 전 인증 경로 차단",
    )
    withdrawn_reason: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="탈퇴 사유(선택 수집, 통계용)"
    )
    phone: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="휴대전화(선택). E.164 권장"
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="마지막 비밀번호 변경/재설정 시각",
    )

    # 관계
    tenant = relationship("Tenant", back_populates="users")
