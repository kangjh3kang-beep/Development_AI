"""032 — 중심엔진 통합: engine_run_binding(run_id↔테넌트 결속 + 멱등) 스키마 정식화

Revises: 031_analysis_ledger
Create Date: 2026-06-18

배선 분석(deliberation-wiring-audit)이 확인한 배포 단선 해소: engine_run_binding 테이블이 런타임
binding_service._ensure() lazy-DDL로만 생성돼 `alembic upgrade head`만 돈 신규 배포에는 부재했다.
DDL은 binding_service._DDL/_UX/_IDX와 1:1 동일(self-contained, 031 선례). additive·멱등(IF NOT EXISTS)이라
런타임 _ensure(부팅 1회 가드로 축소)와 충돌 없이 공존. 이 테이블은 중심엔진의 테넌트 소유검증
(교차테넌트 read 차단)+멱등 강제의 유일 계층이므로 마이그레이션 배선이 무결성 단일점.
"""
from alembic import op

revision = "032_deliberation_binding"
down_revision = "031_analysis_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS engine_run_binding (
            run_id text PRIMARY KEY,
            engine_task_id text,
            source text NOT NULL,
            tenant_id text NOT NULL,
            project_id text,
            created_by text,
            input_hash text NOT NULL,
            content_input_hash text NOT NULL,
            snapshot_id text,
            status text,
            result jsonb,
            deterministic boolean NOT NULL DEFAULT true,
            created_at timestamptz DEFAULT now()
        )
        """
    )
    # 구 비-partial 유니크 인덱스가 있으면 제거 후 partial(결정론 run만 dedup) 재생성 — _ensure와 동일.
    op.execute("DROP INDEX IF EXISTS ux_run_binding_idem")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_run_binding_idem_det "
        "ON engine_run_binding(tenant_id, content_input_hash, coalesce(snapshot_id, '')) "
        "WHERE deterministic"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_run_binding_tenant_run "
        "ON engine_run_binding(tenant_id, run_id)"
    )


def downgrade() -> None:
    # 결속/멱등 캐시 — 계보 자산(원장)과 달리 가역 DROP 허용(SSOT 관례: drop_index→drop_table).
    op.execute("DROP INDEX IF EXISTS idx_run_binding_tenant_run")
    op.execute("DROP INDEX IF EXISTS ux_run_binding_idem_det")
    op.execute("DROP TABLE IF EXISTS engine_run_binding")
