"""permit_process_run 테이블(인·허가/심의 프로세스 결과 영속)."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

revision = "0016_permit_process"
down_revision = "0015_reconcile_content_hash"
branch_labels = None
depends_on = None
SCHEMA = "review"


def upgrade() -> None:
    op.create_table(
        "permit_process_run",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("spec_id", sa.String(64), nullable=False),
        sa.Column("spec_version", sa.String(64), nullable=False),
        sa.Column("analysis_run_id", sa.String(64), nullable=True),
        sa.Column("overall_conformance", sa.String(16), nullable=True),
        sa.Column("overall_verification", sa.String(16), nullable=True),
        sa.Column("result", JSONB, nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_permit_process_run_project", "permit_process_run",
                    ["project_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_permit_process_run_project", table_name="permit_process_run", schema=SCHEMA)
    op.drop_table("permit_process_run", schema=SCHEMA)
