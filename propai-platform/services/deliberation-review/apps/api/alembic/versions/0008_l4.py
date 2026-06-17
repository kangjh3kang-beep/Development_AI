"""l4: 유사사례 — precedent_case/precedent_match/precedent_stat.

Revision ID: 0008_l4
Revises: 0007_l3b
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

revision = "0008_l4"
down_revision = "0007_l3b"
branch_labels = None
depends_on = None

SCHEMA = "review"

_TABLES = ("precedent_case", "precedent_match", "precedent_stat")


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
        "precedent_case",
        *_common(),
        sa.Column("case_id", sa.String(128), nullable=False, unique=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("jurisdiction", sa.String(64), nullable=True),
        sa.Column("decision_type", sa.String(32), nullable=True),
        sa.Column("issue_labels", JSONB(), nullable=True),
        sa.Column("conditions", JSONB(), nullable=True),
        sa.Column("decided_date", sa.Date(), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "precedent_match",
        *_common(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("issue", sa.String(128), nullable=True),
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=True),
        sa.Column("is_candidate", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "precedent_stat",
        *_common(),
        sa.Column("issue", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("n", sa.Integer(), nullable=True),
        sa.Column("distribution", JSONB(), nullable=True),
        sa.Column("common_conditions", JSONB(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table, schema=SCHEMA)
