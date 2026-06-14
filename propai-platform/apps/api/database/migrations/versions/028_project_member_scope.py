"""028 — project_members.scope_categories 컬럼(외부 협력업체 허용 심의범위 영속)

Revision ID: 028_project_member_scope
Revises: 027_collaboration_doc_purpose
Create Date: 2026-06-14

SP5 보안 — 초대 scope_categories를 수락 시 멤버십에 영속해 외부 협력업체(external_reviewer)의 문서
접근을 허용 카테고리로 제한한다(적대적 리뷰 high 결함 수정). additive 컬럼(IF NOT EXISTS·null=무제한).
"""
from alembic import op

revision = "028_project_member_scope"
down_revision = "027_collaboration_doc_purpose"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE project_members ADD COLUMN IF NOT EXISTS scope_categories JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE project_members DROP COLUMN IF EXISTS scope_categories")
