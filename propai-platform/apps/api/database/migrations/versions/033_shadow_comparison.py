"""033 — 중심엔진 수렴 관측: shadow_comparison(플랫폼 vs 엔진 판정 divergence)

Revises: 032_deliberation_binding
Create Date: 2026-06-18

설계 §6 shadow 병존의 관측 계층. 도메인 분석을 엔진으로 이관하기 전, 플랫폼 자체 판정과 엔진 판정의
divergence를 적재해 일치율 관측 후 authoritative 승격(운영 무중단). DDL은 shadow_service._DDL/_IDX와 1:1
(self-contained, 031/032 선례). additive·멱등(IF NOT EXISTS)이라 런타임 _ensure와 공존.
"""
from alembic import op

revision = "033_shadow_comparison"
down_revision = "032_deliberation_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS shadow_comparison (
            id text PRIMARY KEY,
            tenant_id text NOT NULL,
            domain text NOT NULL,
            input_hash text,
            platform_verdict text,
            engine_verdict text,
            matched boolean NOT NULL,
            divergence_score double precision NOT NULL,
            quant_rel_err double precision,
            detail jsonb,
            created_at timestamptz DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_shadow_domain "
        "ON shadow_comparison(tenant_id, domain, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_shadow_domain")
    op.execute("DROP TABLE IF EXISTS shadow_comparison")
