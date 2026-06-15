"""027 — project_documents.purpose 컬럼(analysis/storage 구분)

Revision ID: 027_collaboration_doc_purpose
Revises: 026_collaboration_documents
Create Date: 2026-06-14

SP4 자료교환 강화 — 분석용(8엔진 대상, DXF/IFC 제한)과 저장·공유용(무제한)을 구분. additive 컬럼
추가(IF NOT EXISTS·기본값 'storage')로 기존 행 하위호환. project_documents 외 무변경.
"""
from alembic import op

revision = "027_collaboration_doc_purpose"
down_revision = "026_collaboration_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE project_documents "
        "ADD COLUMN IF NOT EXISTS purpose VARCHAR(20) NOT NULL DEFAULT 'storage'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE project_documents DROP COLUMN IF EXISTS purpose")
