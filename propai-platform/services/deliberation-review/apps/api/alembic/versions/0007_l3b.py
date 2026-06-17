"""l3b: 공학 시뮬 지표 + 시뮬 파라미터 — sim_metric/sim_param.

Revision ID: 0007_l3b
Revises: 0006_r3
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

revision = "0007_l3b"
down_revision = "0006_r3"
branch_labels = None
depends_on = None

SCHEMA = "review"

_TABLES = ("sim_metric", "sim_param")


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
        "sim_metric",
        *_common(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("metric_id", sa.String(64), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=True),
        sa.Column("unit", sa.String(16), nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("method_trace", JSONB(), nullable=True),
        sa.Column("flags", JSONB(), nullable=True),
        sa.Column("required_value", sa.Numeric(), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "sim_param",
        *_common(),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("unit", sa.String(16), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("basis_article", sa.String(128), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table, schema=SCHEMA)
