"""base: review 스키마 + PostGIS + probe 테이블(공통 믹스인 검증).

Revision ID: 0001_base
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0001_base"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "review"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    # PostGIS는 이미 propai_db에 설치됨 → IF NOT EXISTS는 no-op(권한검사 없음).
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "probe",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(64), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("probe", schema=SCHEMA)
