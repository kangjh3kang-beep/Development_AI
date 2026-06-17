"""r2: 공급/소비 분리 — 원천문서/룰후보/미러/HITL/수집잡/인용점검 테이블.

Revision ID: 0005_r2
Revises: 0004_r1_5
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

revision = "0005_r2"
down_revision = "0004_r1_5"
branch_labels = None
depends_on = None

SCHEMA = "review"

_TABLES = (
    "source_document",
    "rule_candidate",
    "mirror_snapshot",
    "hitl_task",
    "harvest_job",
    "citation_check",
)


def _common() -> list[sa.Column]:
    return [
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "source_document",
        *_common(),
        sa.Column("doc_id", sa.String(128), nullable=False, unique=True),
        sa.Column("tier", sa.String(16), nullable=False),
        sa.Column("uri", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("jurisdiction", sa.String(64), nullable=True),
        sa.Column("title", sa.String(256), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "rule_candidate",
        *_common(),
        sa.Column("candidate_id", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(16), server_default="DRAFT", nullable=False),
        sa.Column("target_variable", sa.String(128), nullable=True),
        sa.Column("content", JSONB(), nullable=True),
        sa.Column("source_doc_id", sa.String(128), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("jurisdiction", sa.String(64), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "mirror_snapshot",
        *_common(),
        sa.Column("snapshot_id", sa.String(64), nullable=False),
        sa.Column("jurisdiction", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=True),
        sa.Column("rules", JSONB(), nullable=True),
        sa.Column("active_candidate_ids", JSONB(), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "hitl_task",
        *_common(),
        sa.Column("task_id", sa.String(128), nullable=False, unique=True),
        sa.Column("candidate_id", sa.String(128), nullable=True),
        sa.Column("usage_freq", sa.Float(), nullable=True),
        sa.Column("imminent", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sla_due_day", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "harvest_job",
        *_common(),
        sa.Column("jurisdiction", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "citation_check",
        *_common(),
        sa.Column("citation_ref", sa.String(256), nullable=True),
        sa.Column("matched", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("method", sa.String(16), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("checked_date", sa.Date(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table, schema=SCHEMA)
