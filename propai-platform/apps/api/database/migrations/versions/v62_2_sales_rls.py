"""v62 sales — RLS(행수준 보안) 활성화 (★적용 보류: 스모크 검증 후 수동 적용)

Revision ID: v62_2_sales_rls
Revises: v62_1_sales_tables
Create Date: 2026-06-03

deps_sales 가 요청마다 set_config('app.site_id'|'app.org_path'|'app.role', ..., true) 를
주입하므로, 본 리비전으로 sales_*/mh_* 테이블에 site 정책(+조직경로 정책)을 적용한다.

★주의(미적용 사유): Supabase 연결 role 이 테이블 소유자/서비스 role 이면 RLS 를 우회하므로
FORCE ROW LEVEL SECURITY 가 필요하고, transaction pooler 에서 set_config(is_local=true) 가
요청 트랜잭션 전체에 전파되는지 검증이 선행돼야 한다. 미검증 상태로 켜면 전 sales 접근이
차단될 수 있어, 통합 스모크(엔드포인트 1왕복) 통과 후 수동 적용한다.
현재 테넌트 격리는 app 계층(CRUDBase.list 의 site_id 필터)에서 1차 강제됨.
"""
from alembic import op

revision = "v62_2_sales_rls"
down_revision = "v62_1_sales_tables"
branch_labels = None
depends_on = None

_ENABLE = r"""
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables
           WHERE schemaname='public' AND (tablename LIKE 'sales\_%' OR tablename LIKE 'mh\_%')
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', r.tablename);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY;', r.tablename);
    EXECUTE format('DROP POLICY IF EXISTS p_site ON %I;', r.tablename);
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name=r.tablename AND column_name='site_id') THEN
      EXECUTE format($f$CREATE POLICY p_site ON %I USING (
          site_id = current_setting('app.site_id', true)::uuid
          OR current_setting('app.role', true) = 'SUPERADMIN');$f$, r.tablename);
    END IF;
  END LOOP;
  DROP POLICY IF EXISTS p_org ON sales_org_nodes;
  CREATE POLICY p_org ON sales_org_nodes USING (
    current_setting('app.role', true) IN ('AGENCY','DEVELOPER','SUPERADMIN')
    OR path <@ current_setting('app.org_path', true)::ltree );
END $$;
"""

_DISABLE = r"""
DO $$ DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables
           WHERE schemaname='public' AND (tablename LIKE 'sales\_%' OR tablename LIKE 'mh\_%')
  LOOP EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY;', r.tablename); END LOOP;
END $$;
"""


def upgrade() -> None:
    op.execute(_ENABLE)


def downgrade() -> None:
    op.execute(_DISABLE)
