"""analysis_run: 분석 실행 영속화(결과 JSONB + 조회 키).

Revision ID: 0012_analysis_run
Revises: 0011_l3c
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

revision = "0012_analysis_run"
down_revision = "0011_l3c"
branch_labels = None
depends_on = None

SCHEMA = "review"


def upgrade() -> None:
    op.create_table(
        "analysis_run",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("result", JSONB(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("analysis_run", schema=SCHEMA)
