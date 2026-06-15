"""031 — 분석 원장(해시체인) 스키마 정식화: analysis_ledger + analysis_ledger_quota

Revision ID: 031_analysis_ledger
Revises: 030_livekit_recordings
Create Date: 2026-06-15

기존 analysis_ledger_service._ensure()의 런타임 lazy-DDL을 alembic 버전관리로 흡수(무결성 단일화).
DDL은 서비스의 _DDL/_IDX/_QUOTA_DDL과 1:1 동일. additive·멱등(IF NOT EXISTS)이라 기존 lazy-DDL과
충돌 없이 공존. 감사 이벤트도 analysis_type='audit'로 본 테이블 한 곳에 누적(별도 audit 테이블 없음).
"""
from alembic import op

revision = "031_analysis_ledger"
down_revision = "030_livekit_recordings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_ledger (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id TEXT,
            pnu TEXT,
            address_norm TEXT,
            project_id TEXT,
            analysis_type TEXT NOT NULL,
            version INT NOT NULL,
            payload JSONB NOT NULL,
            content_hash TEXT NOT NULL,
            prev_hash TEXT,
            source TEXT,
            created_by TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ledger_chain "
        "ON analysis_ledger(tenant_id, pnu, project_id, analysis_type, version DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ledger_addr "
        "ON analysis_ledger(tenant_id, address_norm, analysis_type, version DESC)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_ledger_quota (
            tenant_id TEXT PRIMARY KEY,
            max_entries INT NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    # 원장은 무결성·계보 자산 — 자동 DROP 금지(데이터 소실 방지). 필요 시 운영자가 수동 처리.
    pass
