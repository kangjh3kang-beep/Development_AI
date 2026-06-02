"""add user_project_store table (사용자별 프로젝트/분석 동기화 KV)

Revision ID: 022_user_project_store
Revises: 021_g2b_bid_analysis
Create Date: 2026-06-03

프론트 localStorage 상태(프로젝트 목록+분석 스냅샷)를 사용자 계정에 JSON으로
보관해 기기 무관 동기화를 지원한다. 단순 KV(user_id PK + jsonb).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "022_user_project_store"
down_revision = "021_g2b_bid_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_project_store",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("user_project_store")
