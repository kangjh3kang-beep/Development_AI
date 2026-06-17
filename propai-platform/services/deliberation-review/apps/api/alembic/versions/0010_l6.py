"""l6: 산출물 — review_report/report_item/recommendation.

Revision ID: 0010_l6
Revises: 0009_l5
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

revision = "0010_l6"
down_revision = "0009_l5"
branch_labels = None
depends_on = None

SCHEMA = "review"

_TABLES = ("review_report", "report_item", "recommendation")


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
        "review_report",
        *_common(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("section_counts", JSONB(), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "report_item",
        *_common(),
        sa.Column("report_id", UUID(as_uuid=True), nullable=True),
        sa.Column("item_id", sa.String(128), nullable=True),
        sa.Column("title", sa.String(256), nullable=True),
        sa.Column("verdict", sa.String(32), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("evidence", JSONB(), nullable=True),
        sa.Column("confidence_grade", sa.String(16), nullable=True),
        sa.Column("basis_article", sa.String(128), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "recommendation",
        *_common(),
        sa.Column("report_item_id", UUID(as_uuid=True), nullable=True),
        sa.Column("target_variable", sa.String(128), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("basis_article", sa.String(128), nullable=True),
        sa.Column("grounded", sa.Boolean(), server_default="false", nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table, schema=SCHEMA)
