"""029 — 회의방 의견교환 테이블: review_comments (+RLS 방어심층)

Revision ID: 029_review_comments
Revises: 028_project_member_scope
Create Date: 2026-06-14

SP6 회의방 의견교환(심의 스레드) — app/models/collaboration.py의 ReviewComment와 1:1. 문서/지적별
댓글·답변(parent_id 무제한 중첩), 루트 전용 resolved(문서 review_state와 별개 트랙), 소프트삭제.
additive·멱등(IF NOT EXISTS). RLS는 026과 동일 패턴(organization_id 테넌트 격리, 방어심층 —
공용 get_db가 RLS GUC 미주입이라 런타임 1차 격리는 app-level require_project_member).
"""
from alembic import op

revision = "029_review_comments"
down_revision = "028_project_member_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS review_comments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id),
            organization_id UUID NOT NULL REFERENCES organizations(id),
            document_id UUID NOT NULL REFERENCES project_documents(id),
            parent_id UUID REFERENCES review_comments(id),
            anchor VARCHAR(200),
            author_id UUID REFERENCES users(id),
            body TEXT NOT NULL,
            resolved BOOLEAN NOT NULL DEFAULT false,
            resolved_by UUID REFERENCES users(id),
            resolved_at TIMESTAMP,
            edited BOOLEAN NOT NULL DEFAULT false,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_review_comments_document ON review_comments(document_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_review_comments_project ON review_comments(project_id)")

    # ── RLS 방어심층(organization_id 기준 테넌트 격리) — 026과 동일 패턴 ──
    op.execute("ALTER TABLE review_comments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE review_comments FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS review_comments_tenant_isolation ON review_comments")
    op.execute(
        "CREATE POLICY review_comments_tenant_isolation ON review_comments "
        "USING (organization_id = current_setting('app.current_tenant', true)::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS review_comments")
