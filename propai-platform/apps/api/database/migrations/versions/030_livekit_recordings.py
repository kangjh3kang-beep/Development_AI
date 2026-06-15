"""030 — LiveKit 녹화 메타 테이블: livekit_recordings (+RLS 방어심층)

Revision ID: 030_livekit_recordings
Revises: 029_review_comments
Create Date: 2026-06-15

LiveKit Phase 3 화상회의 녹화(Egress→S3) 메타. app/models/livekit.py의 Recording와 1:1. 실파일은 S3,
본 테이블엔 메타+s3_key만. additive·멱등(IF NOT EXISTS). organization_id 기준 RLS(025~ 동일 패턴).
"""
from alembic import op

revision = "030_livekit_recordings"
down_revision = "029_review_comments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS livekit_recordings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id),
            organization_id UUID NOT NULL REFERENCES organizations(id),
            room VARCHAR(128) NOT NULL,
            egress_id VARCHAR(128),
            s3_key VARCHAR(512),
            status VARCHAR(20) NOT NULL DEFAULT 'recording',
            started_by UUID REFERENCES users(id),
            started_at TIMESTAMP DEFAULT now(),
            ended_at TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_livekit_recordings_project ON livekit_recordings(project_id)")

    op.execute("ALTER TABLE livekit_recordings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE livekit_recordings FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS livekit_recordings_tenant_isolation ON livekit_recordings")
    op.execute(
        "CREATE POLICY livekit_recordings_tenant_isolation ON livekit_recordings "
        "USING (organization_id = current_setting('app.current_tenant', true)::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS livekit_recordings")
