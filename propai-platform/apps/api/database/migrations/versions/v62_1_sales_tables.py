"""v62 분양관리 ERP + 모델하우스 데스크 — 66 테이블 + 확장/특수인덱스 (4헤드 병합)

Revision ID: v62_1_sales_tables
Revises: (merge) 019_spatial, 015_patch_s06_backup_logs, 021_v62_design_tables, 022_user_project_store
Create Date: 2026-06-03

기존 alembic 히스토리가 4개 헤드로 분기되어 `upgrade head`가 불가능했던 상태를
본 머지 리비전으로 단일 헤드로 통합하면서 sales_*/mh_* 66 테이블을 함께 생성한다.

설계 결정(사용자 승인):
- TimescaleDB 미지원(Supabase) → sales_site_summary/sales_unit_status_log/mh_visit_stats 는
  일반 테이블 + (site_id, ts DESC) 인덱스로 대체. create_hypertable 미사용.
- 테이블 생성은 모델 메타데이터(단일 진실원천) 기반 create_all 로 수행(수기 create_table 오류 제거).
- RLS 정책 적용(ENABLE ROW LEVEL SECURITY)은 set_config 주입(deps_sales, Part2) 완료 후
  별도 리비전에서 활성화한다. 본 리비전은 스키마/확장/인덱스까지만.
"""
from alembic import op

revision = "v62_1_sales_tables"
down_revision = (
    "019_spatial",
    "015_patch_s06_backup_logs",
    "021_v62_design_tables",
    "022_user_project_store",
)
branch_labels = None
depends_on = None


def _sales_tables():
    from apps.api.database.models.base import Base
    import apps.api.database.models.sales  # noqa: F401  (66 모델 등록)
    return [t for n, t in Base.metadata.sorted_tables
            if n.startswith("sales_") or n.startswith("mh_")]


def upgrade() -> None:
    bind = op.get_bind()
    # 확장: ltree(조직 경로), pg_trgm(이름 유사검색), pgcrypto(gen_random_uuid 보장)
    op.execute("CREATE EXTENSION IF NOT EXISTS ltree;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    from apps.api.database.models.base import Base
    tables = _sales_tables()
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)

    # ── 특수 인덱스 ──
    op.execute("CREATE INDEX IF NOT EXISTS idx_org_path ON sales_org_nodes USING gist (path);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_staff_name_trgm ON sales_staff USING gin (name gin_trgm_ops);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_staff_phone ON sales_staff_phone_index (site_id, phone_e164);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_customer_phone ON sales_customers (site_id, phone_e164);")
    # 1호 1지번(동/호) 유니크 — 소프트삭제 제외
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_unit_dongho "
        "ON sales_unit_inventory (site_id, dong, ho) WHERE deleted_at IS NULL;"
    )
    # 시계열 대체 테이블 시간 인덱스(하이퍼테이블 대신)
    op.execute("CREATE INDEX IF NOT EXISTS idx_site_summary_ts ON sales_site_summary (site_id, ts DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_unit_status_log_ts ON sales_unit_status_log (site_id, ts DESC);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mh_visit_stats_ts ON mh_visit_stats (site_id, ts DESC);")
    # 아웃박스 미발행분 조회 가속(동기 투영 폴링/배치)
    op.execute("CREATE INDEX IF NOT EXISTS idx_outbox_pending ON sales_harness_outbox (status) WHERE status = 'PENDING';")


def downgrade() -> None:
    bind = op.get_bind()
    from apps.api.database.models.base import Base
    tables = list(reversed(_sales_tables()))
    Base.metadata.drop_all(bind=bind, tables=tables, checkfirst=True)
