"""r1_5: 법정 산정값 + 산정규칙/규칙셋/파라미터 테이블.

Revision ID: 0004_r1_5
Revises: 0003_r0_5
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

revision = "0004_r1_5"
down_revision = "0003_r0_5"
branch_labels = None
depends_on = None

SCHEMA = "review"

_TABLES = ("legal_quantity", "calc_rule", "calc_rule_set", "calc_param")


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
        "legal_quantity",
        *_common(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("variable_id", sa.String(128), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("calc_trace", JSONB(), nullable=True),
        sa.Column("calc_rule_version", sa.String(64), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "calc_rule",
        *_common(),
        sa.Column("rule_id", sa.String(64), nullable=False, unique=True),
        sa.Column("target_variable", sa.String(128), nullable=False),
        sa.Column("exclusion_logic_ref", sa.String(128), nullable=True),
        sa.Column("params", JSONB(), nullable=True),
        sa.Column("basis_article", sa.String(128), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "calc_rule_set",
        *_common(),
        sa.Column("set_id", sa.String(64), nullable=True),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("params", JSONB(), nullable=True),
        sa.Column("ruleset_version", sa.String(64), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "calc_param",
        *_common(),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("basis_article", sa.String(128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table, schema=SCHEMA)
