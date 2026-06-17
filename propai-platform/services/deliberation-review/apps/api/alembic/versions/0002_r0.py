"""r0: 정규변수/원장/preflight/관할/스냅샷/감사/해소파라미터 테이블.

Revision ID: 0002_r0
Revises: 0001_base
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

revision = "0002_r0"
down_revision = "0001_base"
branch_labels = None
depends_on = None

SCHEMA = "review"

_TABLES = (
    "canonical_variable",
    "quantity_ledger",
    "preflight_context",
    "jurisdiction",
    "regulation_snapshot",
    "audit_record",
    "resolution_parameter",
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
        "canonical_variable",
        *_common(),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("basis_article", sa.String(128), nullable=True),
        sa.Column("allowed_sources", JSONB(), nullable=True),
        sa.Column("required_for_rules", JSONB(), nullable=True),
        sa.Column("required", sa.Boolean(), server_default="false", nullable=False),
        schema=SCHEMA,
    )
    op.create_table(
        "quantity_ledger",
        *_common(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("variable_name", sa.String(128), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("source_sheet", sa.String(128), nullable=True),
        sa.Column("method", sa.String(16), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("conflicts", JSONB(), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "preflight_context",
        *_common(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("pnu", sa.String(32), nullable=True),
        sa.Column("jurisdiction", JSONB(), nullable=True),
        sa.Column("base_date", sa.Date(), nullable=True),
        sa.Column("scale", JSONB(), nullable=True),
        sa.Column("blocked", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("assumed_fields", JSONB(), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "jurisdiction",
        *_common(),
        sa.Column("pnu", sa.String(32), nullable=False),
        sa.Column("sido_code", sa.String(8), nullable=True),
        sa.Column("sigungu_code", sa.String(16), nullable=True),
        sa.Column("zones", JSONB(), nullable=True),
        sa.Column("stricter_applied", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("source", sa.String(16), nullable=True),
        sa.Column("assumed", sa.Boolean(), server_default="false", nullable=False),
        schema=SCHEMA,
    )
    op.create_table(
        "regulation_snapshot",
        *_common(),
        sa.Column("snapshot_id", sa.String(64), nullable=False, unique=True),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("ruleset_version", sa.String(64), nullable=False),
        sa.Column("calc_rule_version", sa.String(64), nullable=False),
        schema=SCHEMA,
    )
    op.create_table(
        "audit_record",
        *_common(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("layer", sa.String(32), nullable=True),
        sa.Column("decision_ref", sa.String(128), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "resolution_parameter",
        *_common(),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table, schema=SCHEMA)
