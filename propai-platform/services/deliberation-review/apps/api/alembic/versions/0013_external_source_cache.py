"""external_source_cache: 외부 1차출처 응답 캐시(INC-11).

Revision ID: 0013_external_source_cache
Revises: 0012_analysis_run
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

revision = "0013_external_source_cache"
down_revision = "0012_analysis_run"
branch_labels = None
depends_on = None

SCHEMA = "review"


def upgrade() -> None:
    op.create_table(
        "external_source_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("adapter", sa.String(64), nullable=False),
        sa.Column("endpoint", sa.String(512), nullable=False),
        sa.Column("params_hash", sa.String(64), nullable=False),
        sa.Column("payload", JSONB(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("etag", sa.String(256), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
        sa.UniqueConstraint("cache_key", name="uq_external_source_cache_cache_key"),
        schema=SCHEMA,
    )
    op.create_index("ix_external_source_cache_cache_key", "external_source_cache",
                    ["cache_key"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_external_source_cache_cache_key", table_name="external_source_cache", schema=SCHEMA)
    op.drop_table("external_source_cache", schema=SCHEMA)
