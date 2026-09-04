"""회원 계정 보안 토큰·동의 이력 모델(2026-07 회원 시스템).

- PasswordResetToken: 비밀번호 재설정 1회용 토큰(발송 후 30분 유효).
- EmailVerificationToken: 이메일 인증 1회용 토큰(24시간 유효).
- UserConsent: 약관·개인정보 동의 이력(필수/선택 분리 저장 — 개인정보보호법 §22).

보안 불변식:
- 토큰 **원문은 DB에 저장하지 않는다** — SHA-256 hex(64자)만 저장(유출 시 원문 복원 불가).
- `used_at IS NOT NULL` = 사용됨(재사용 차단). 검증은 `expires_at > now AND used_at IS NULL`.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, TimestampMixin


class _OneTimeTokenColumns:
    """1회용 토큰 공통 컬럼(재설정·이메일인증)."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False,
        comment="원문 토큰의 SHA-256 hex — 원문은 이메일 링크에만 존재",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="만료 시각(재설정=발급+30분)"
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="사용 시각(1회용 — 재사용 차단)"
    )
    requested_ip: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="요청 IP(감사)"
    )


class PasswordResetToken(Base, _OneTimeTokenColumns, TimestampMixin):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    user = relationship("User", backref="password_reset_tokens")


class EmailVerificationToken(Base, _OneTimeTokenColumns, TimestampMixin):
    __tablename__ = "email_verification_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    user = relationship("User", backref="email_verification_tokens")


class UserConsent(Base, TimestampMixin):
    """약관·개인정보 동의 이력 — 가입/변경 시점의 동의 사실을 버전과 함께 보존."""

    __tablename__ = "user_consents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    consent_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="terms_of_service | privacy_policy | marketing | third_party",
    )
    agreed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policy_version: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="동의한 약관/방침 버전"
    )
    agreed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user = relationship("User", backref="consents")
