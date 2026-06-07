"""024 — projects.analysis_snapshot 컬럼 추가(프로젝트별 분석 백엔드 단일출처)

Revision ID: 024_project_analysis_snapshot
Revises: 023_user_subscription_columns
Create Date: 2026-06-07

프론트 useProjectContextStore의 ProjectSnapshot(siteAnalysis/designData/costData/
feasibilityData/esgData/complianceData/completedStages/currentStage/analysisResults/
updatedAt) JSON blob을 프로젝트 단위로 영속해 기기간 동기화를 가능케 한다.

ADD COLUMN IF NOT EXISTS / nullable / 백필 없음 → 기존 흐름 무파괴·additive·멱등.
기존 user_project_store(전체 store blob 미러)와 병행 유지(점진 이관).
"""
from alembic import op

revision = "024_project_analysis_snapshot"
down_revision = "023_user_subscription_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS analysis_snapshot jsonb"
    )


def downgrade() -> None:
    # 분석 데이터 보존을 위해 다운그레이드에서 컬럼을 제거하지 않는다(안전·무손실).
    # 필요 시 운영자가 명시적으로 DROP COLUMN 한다.
    pass
