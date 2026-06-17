"""r3: 룰 의존 DAG + 3값 판정 + 매핑 — rule/rule_edge/finding/mapping_assignment.

Revision ID: 0006_r3
Revises: 0005_r2
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

revision = "0006_r3"
down_revision = "0005_r2"
branch_labels = None
depends_on = None

SCHEMA = "review"

_TABLES = ("rule", "rule_edge", "finding", "mapping_assignment")


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
        "rule",
        *_common(),
        sa.Column("rule_id", sa.String(64), nullable=False, unique=True),
        sa.Column("target_variable", sa.String(128), nullable=True),
        sa.Column("comparator", sa.String(8), nullable=True),
        sa.Column("relaxations", JSONB(), nullable=True),
        sa.Column("basis_article", sa.String(128), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "rule_edge",
        *_common(),
        sa.Column("rule_id", sa.String(64), nullable=False),
        sa.Column("depends_on_rule_id", sa.String(64), nullable=False),
        schema=SCHEMA,
    )
    op.create_table(
        "finding",
        *_common(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("rule_id", sa.String(64), nullable=False),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("conditional_relaxations", JSONB(), nullable=True),
        sa.Column("requires_committee", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("composite_confidence", sa.Float(), nullable=True),
        sa.Column("gated_status", sa.String(16), nullable=True),
        sa.Column("conflicts", JSONB(), nullable=True),
        sa.Column("basis_article", sa.String(128), nullable=True),
        sa.Column("measured_value", sa.Numeric(), nullable=True),
        sa.Column("limit_value", sa.Numeric(), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "mapping_assignment",
        *_common(),
        sa.Column("source_criterion", sa.String(256), nullable=True),
        sa.Column("standard_item", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("silent_pass", sa.Boolean(), server_default="false", nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table, schema=SCHEMA)
