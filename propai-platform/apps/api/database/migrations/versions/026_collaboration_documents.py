"""026 — 회의방 자료교환 테이블: project_documents (+RLS 방어심층)

Revision ID: 026_collaboration_documents
Revises: 025_collaboration_tables
Create Date: 2026-06-14

SP3 프로젝트 회의방 자료교환 — 협력업체 업로드자료. app/models/collaboration.py의 ProjectDocument와
1:1. 실파일은 Supabase 비공개 버킷(서명URL), 본 테이블엔 메타+storage_path만. additive·멱등
(IF NOT EXISTS) — 025(project_members/collaborator_invites) 무변경.

격리 주의: 025와 동일 — 공용 get_db가 RLS GUC(app.current_tenant)를 미주입하므로 RLS는 *방어심층*,
런타임 1차 격리는 app-level require_project_member(멤버십 DB조회)가 담당. organization_id 기준 정책.
"""
from alembic import op

revision = "026_collaboration_documents"
down_revision = "025_collaboration_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── project_documents ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id),
            organization_id UUID NOT NULL REFERENCES organizations(id),
            uploaded_by UUID REFERENCES users(id),
            storage_path VARCHAR(512) NOT NULL,
            file_url VARCHAR(1024),
            original_filename VARCHAR(255) NOT NULL,
            content_type VARCHAR(120),
            size_bytes INTEGER,
            category VARCHAR(30),
            doc_kind VARCHAR(20) NOT NULL DEFAULT 'document',
            audit_status VARCHAR(20),
            audit_summary JSONB,
            review_state VARCHAR(20) NOT NULL DEFAULT 'requested',
            reviewed_by UUID REFERENCES users(id),
            reviewed_at TIMESTAMP,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_project_documents_project ON project_documents(project_id)")

    # ── RLS 방어심층(organization_id 기준 테넌트 격리) — 025와 동일 패턴 ──
    op.execute("ALTER TABLE project_documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE project_documents FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS project_documents_tenant_isolation ON project_documents")
    op.execute(
        "CREATE POLICY project_documents_tenant_isolation ON project_documents "
        "USING (organization_id = current_setting('app.current_tenant', true)::uuid)"
    )


def downgrade() -> None:
    # 신규 테이블이므로 다운그레이드에서 안전하게 제거(데이터 보존 대상 아님).
    op.execute("DROP TABLE IF EXISTS project_documents")
