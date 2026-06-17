"""r0_5: 시트역할 배정 + 의미요소 테이블.

Revision ID: 0003_r0_5
Revises: 0002_r0
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

revision = "0003_r0_5"
down_revision = "0002_r0"
branch_labels = None
depends_on = None

SCHEMA = "review"

_TABLES = ("sheet_role_assignment", "semantic_element")


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
        "sheet_role_assignment",
        *_common(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("sheet_id", sa.String(128), nullable=False),
        sa.Column("role", sa.String(32), nullable=True),
        sa.Column("isolated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("method", JSONB(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("flags", JSONB(), nullable=True),
        sa.Column("provenance", JSONB(), nullable=True),
        schema=SCHEMA,
    )
    op.create_table(
        "semantic_element",
        *_common(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("element_id", sa.String(128), nullable=False),
        sa.Column("semantic_type", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("identity_status", sa.String(16), nullable=True),
        sa.Column("source_sheets", JSONB(), nullable=True),
        sa.Column("provenance", JSONB(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table, schema=SCHEMA)
