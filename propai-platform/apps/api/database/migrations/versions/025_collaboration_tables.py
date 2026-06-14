"""025 — 협업/회의방(F3) 테이블: project_members · collaborator_invites (+RLS 방어심층)

Revision ID: 025_collaboration_tables
Revises: 024_project_analysis_snapshot
Create Date: 2026-06-14

SP2 프로젝트 회의방 — 팀 멤버(내부) + 외부 협력업체 게스트 초대. app/models/collaboration.py의
ProjectMember/CollaboratorInvite와 1:1. additive·멱등(IF NOT EXISTS) — 기존 흐름 무파괴.

격리 주의: 공용 get_db가 RLS GUC(app.current_tenant)를 미주입하므로(검증됨) RLS는 *방어심층*이고,
런타임 1차 격리는 app-level require_project_member(멤버십 DB조회)가 담당한다. app.current_tenant에는
organization_id가 주입된다는 전제(코드베이스 RLS 관례)로 organization_id 기준 정책을 건다.
"""
from alembic import op

revision = "025_collaboration_tables"
down_revision = "024_project_analysis_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── project_members ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_members (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id),
            organization_id UUID NOT NULL REFERENCES organizations(id),
            user_id UUID REFERENCES users(id),
            project_role VARCHAR(30) NOT NULL DEFAULT 'viewer',
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            invited_by UUID REFERENCES users(id),
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now(),
            CONSTRAINT uq_project_member UNIQUE (project_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_project_members_project ON project_members(project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_project_members_user ON project_members(user_id)")

    # ── collaborator_invites ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS collaborator_invites (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id),
            organization_id UUID NOT NULL REFERENCES organizations(id),
            invite_token VARCHAR(64) NOT NULL UNIQUE,
            email VARCHAR(255) NOT NULL,
            project_role VARCHAR(30) NOT NULL DEFAULT 'external_reviewer',
            scope_categories JSONB DEFAULT '[]'::jsonb,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            expires_at TIMESTAMP NOT NULL,
            invited_by UUID REFERENCES users(id),
            accepted_at TIMESTAMP,
            accepted_user_id UUID REFERENCES users(id),
            created_at TIMESTAMP DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_collaborator_invites_project ON collaborator_invites(project_id)")

    # ── RLS 방어심층(organization_id 기준 테넌트 격리) ──
    for tbl in ("project_members", "collaborator_invites"):
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl}"
        )
        op.execute(
            f"CREATE POLICY {tbl}_tenant_isolation ON {tbl} "
            "USING (organization_id = current_setting('app.current_tenant', true)::uuid)"
        )


def downgrade() -> None:
    # 신규 테이블이므로 다운그레이드에서 안전하게 제거(데이터 보존 대상 아님).
    op.execute("DROP TABLE IF EXISTS collaborator_invites")
    op.execute("DROP TABLE IF EXISTS project_members")
