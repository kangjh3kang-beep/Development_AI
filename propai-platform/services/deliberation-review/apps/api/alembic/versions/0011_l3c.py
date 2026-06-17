"""l3c: 정성 평가 — qual_assessment/rubric_citation/qual_cache.

Revision ID: 0011_l3c
Revises: 0010_l6
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

revision = "0011_l3c"
down_revision = "0010_l6"
branch_labels = None
depends_on = None

SCHEMA = "review"

_TABLES = ("qual_assessment", "rubric_citation", "qual_cache")


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
        "qual_assessment",
        *_common(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("item", sa.String(128), nullable=True),
        sa.Column("grade", sa.String(16), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("is_grade", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("asserts_legal_verdict", sa.Boolean(), server_default="false", nullable=False),
        schema=SCHEMA,
    )
    op.create_table(
        "rubric_citation",
        *_common(),
        sa.Column("qual_assessment_id", UUID(as_uuid=True), nullable=True),
        sa.Column("rubric_item", sa.String(256), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("effective", sa.Boolean(), server_default="true", nullable=False),
        schema=SCHEMA,
    )
    op.create_table(
        "qual_cache",
        *_common(),
        sa.Column("cache_key", sa.String(64), nullable=False, unique=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("result", JSONB(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table, schema=SCHEMA)
