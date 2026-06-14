"""v62 자가성장 엔진 Phase 3 — platform_settings(자가치유 L0/L1 설정 테이블, 정본).

Revision ID: v62_6_platform_settings
Revises: v62_5_self_growth_tables
Create Date: 2026-06-14

platform_settings: 임계값 일시조정·피처플래그용 key/value 저장소.
- threshold_relax(외부API 전면장애 시 rate-limit/timeout 임계 일시상향) 등
  L0/L1 자동조치가 TTL 만료 자동원복 가능한 설정을 기록한다.
- ttl_expires_at 만료 시 get_setting 헬퍼가 None 반환(논리적 만료, prune 와 무관).

down_revision 은 Phase 1 텔레메트리 테이블(v62_5_self_growth_tables)에 연결.
schema_guard.ensure_schema 가 부팅 멱등 안전망을 별도 제공(정본은 이 마이그레이션).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v62_6_platform_settings"
down_revision = "v62_5_self_growth_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "platform_settings" in insp.get_table_names():
        return
    op.create_table(
        "platform_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=False, server_default=sa.text("'global'")),
        sa.Column("ttl_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    # (key, scope) 단일성 — upsert 키. 동일 scope 내 key 1행.
    op.create_index("uq_ps_key_scope", "platform_settings", ["key", "scope"], unique=True)
    op.create_index("idx_ps_ttl", "platform_settings", ["ttl_expires_at"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "platform_settings" not in insp.get_table_names():
        return
    op.drop_index("idx_ps_ttl", table_name="platform_settings")
    op.drop_index("uq_ps_key_scope", table_name="platform_settings")
    op.drop_table("platform_settings")
