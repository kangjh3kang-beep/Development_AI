"""INC-14 reconcile 완결: mirror_snapshot.content_hash(라이브 본문 diff 기준) +
analysis_run.input_payload(동일입력 재실행 보존).

Revision ID: 0015_reconcile_content_hash
Revises: 0014_mirror_snapshot_uniq
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0015_reconcile_content_hash"
down_revision = "0014_mirror_snapshot_uniq"
branch_labels = None
depends_on = None

SCHEMA = "review"


def upgrade() -> None:
    # 둘 다 nullable — legacy 행(해시/입력 미기록) 보존, reconcile가 None을 표면화(무음 단정 금지).
    op.add_column("mirror_snapshot", sa.Column("content_hash", sa.String(64), nullable=True),
                  schema=SCHEMA)
    op.add_column("analysis_run", sa.Column("input_payload", JSONB(), nullable=True),
                  schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("analysis_run", "input_payload", schema=SCHEMA)
    op.drop_column("mirror_snapshot", "content_hash", schema=SCHEMA)
