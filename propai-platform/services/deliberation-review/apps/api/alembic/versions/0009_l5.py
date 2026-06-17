"""l5: 검증 계층 — verification_result/claim_evidence_link/reconcile_log.

Revision ID: 0009_l5
Revises: 0008_l4
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

revision = "0009_l5"
down_revision = "0008_l4"
branch_labels = None
depends_on = None

SCHEMA = "review"

_TABLES = ("verification_result", "claim_evidence_link", "reconcile_log")


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
        "verification_result",
        *_common(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("citation_ref", sa.String(256), nullable=True),
        sa.Column("passed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("checks", JSONB(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "claim_evidence_link",
        *_common(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("claim", sa.Text(), nullable=True),
        sa.Column("evidence_refs", JSONB(), nullable=True),
        sa.Column("supported", sa.Boolean(), server_default="false", nullable=False),
        schema=SCHEMA,
    )
    op.create_table(
        "reconcile_log",
        *_common(),
        sa.Column("citation_ref", sa.String(256), nullable=True),
        sa.Column("live_reconciled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("mismatch", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("detail", JSONB(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table, schema=SCHEMA)
