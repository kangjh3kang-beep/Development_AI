"""회원 시스템(가입 동의·비밀번호 재설정·이메일 인증·탈퇴) 스키마.

2026-07-15 회원 시스템 확정 스펙(§2):
- users 컬럼 6종 추가(email_verified·email_verified_at·deleted_at·withdrawn_reason·
  phone·password_changed_at).
- 이메일 전역 유니크(users_email_key) → **부분 유니크** `ux_users_email_active`
  (`WHERE deleted_at IS NULL`) 전환 — 탈퇴 30일 유예 후 동일 이메일 재가입 허용.
  이메일 단독 조회용 일반 인덱스(ix_users_email) 병설.
- 신규 테이블 3종: password_reset_tokens(30분·1회용), email_verification_tokens(24h),
  user_consents(약관·개인정보 동의 이력 — 필수/선택 분리).

downgrade 주의: 전역 유니크 복원은 탈퇴-재가입으로 동일 이메일이 중복 존재하면
실패한다(운영에서 downgrade는 데이터 정리 후 수행 — 정직한 제약).

Revision ID: 042_member_account_system
Revises: v62_8_run_execution
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "042_member_account_system"
down_revision: str | None = "v62_8_run_execution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _one_time_token_columns() -> list[sa.Column]:
    """1회용 토큰 테이블 공통 컬럼(원문 미저장 — SHA-256 해시만)."""
    return [
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_ip", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]


def upgrade() -> None:
    # ── 1. users 컬럼 추가 ──
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("users", sa.Column("withdrawn_reason", sa.String(500), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(32), nullable=True))
    op.add_column(
        "users",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── 2. 이메일 전역 유니크 → 활성 계정 부분 유니크 ──
    # 001에서 unique=True 컬럼 정의로 생성된 제약명은 PG 기본 규칙상 users_email_key.
    # (환경별 편차 대비 IF EXISTS — 없으면 no-op, 침묵 실패 아님: 아래 부분 유니크가 대체 제약)
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key")
    op.execute("DROP INDEX IF EXISTS users_email_key")
    op.create_index(
        "ux_users_email_active",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # ── 3. 신규 테이블 ──
    op.create_table("password_reset_tokens", *_one_time_token_columns())
    op.create_table("email_verification_tokens", *_one_time_token_columns())
    op.create_table(
        "user_consents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("consent_type", sa.String(50), nullable=False),
        sa.Column("agreed", sa.Boolean(), nullable=False),
        sa.Column("policy_version", sa.String(20), nullable=False),
        sa.Column(
            "agreed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("user_consents")
    op.drop_table("email_verification_tokens")
    op.drop_table("password_reset_tokens")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ux_users_email_active", table_name="users")
    # 전역 유니크 복원 — 탈퇴-재가입 중복 이메일이 있으면 실패(정직: 데이터 정리 후 수행).
    op.create_unique_constraint("users_email_key", "users", ["email"])

    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "phone")
    op.drop_column("users", "withdrawn_reason")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email_verified")
