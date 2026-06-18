"""v62 sales — RLS(행수준 보안) 활성화 (★정본: ENABLE+FORCE + fail-closed 정책)

Revision ID: v62_2_sales_rls
Revises: v62_1_sales_tables
Create Date: 2026-06-03

deps_sales 가 요청마다 set_config('app.site_id'|'app.org_path'|'app.role', ..., true) 를
주입하므로, 본 리비전으로 sales_*/mh_* 테이블에 site 정책(+조직경로 정책)을 적용한다.
본 마이그레이션이 RLS 정책의 정본(定本)이며, 런타임 부트스트랩
(app/services/sales/sales_rls_bootstrap.py)은 동일 정책을 멱등 재현하는 보완 경로다.

★ENABLE+FORCE 둘 다 적용한다:
  - ENABLE 만으로는 테이블 소유자/BYPASSRLS role 이 정책을 우회한다.
  - FORCE 로 소유자 쿼리도 정책을 거치게 한다.
  - ★실효 전제(인프라=deploy-pending): 앱이 DB에 접속하는 role 은 'BYPASSRLS 아님'이어야
    한다. BYPASSRLS role(예: 슈퍼유저/서비스 role)로 접속하면 FORCE 여부와 무관하게
    정책이 무시되므로, 앱 전용 non-bypassrls role 분리 후에야 세션기반 격리가 실강제된다.

★fail-closed(3치논리 가드): USING 절을 nullif 로 감싸 세션변수 미설정/빈문자열을 NULL 로
만든다. 'NULL OR NULL = NULL' → 행 비노출(전부 거부)이며, 빈문자열의 '::uuid|::ltree 캐스트
에러' 도 함께 방지한다. 런타임 부트스트랩의 USING 절(_P_SITE_USING/_P_ORG_USING)과 1:1 일치.

★ENABLE+FORCE 적용범위 = '정책이 실제 생기는 테이블'에만 한정한다(★앱 전체 브릭 방지):
  - p_site 대상 = site_id 보유 sales_/mh_ 테이블.
  - p_org  대상 = sales_org_nodes.
  - 정책 0개 테이블(site_id 미보유·org 아님: 예 sales_commission_holdback,
    sales_contract_installments, sales_staff_documents, mh_inventory_txns 등)에는
    ENABLE/FORCE 를 적용하지 않는다. FORCE+정책0 이면 non-bypassrls role 에서
    PostgreSQL RLS 규칙상 '전 행 거부'(소유자 포함)되어 앱 전체가 404 로 브릭되기 때문이다.
  - 즉 'ENABLE+FORCE 를 거는 테이블'과 '정책을 거는 테이블'을 단일 기준(site_id 보유 +
    sales_org_nodes)으로 일치시킨다. 런타임 부트스트랩(sales_rls_bootstrap.py)의
    적용범위와 1:1 정합.

★p_org 는 RESTRICTIVE(AS RESTRICTIVE) 다: sales_org_nodes 는 p_site(PERMISSIVE)와 p_org 가
함께 걸린다. p_org 가 PERMISSIVE 면 둘이 OR 결합돼 role-IN 광역분기가 p_site 의 현장 스코프를
무력화(타 현장 조직노드 노출)한다. RESTRICTIVE 로 AND 결합하고 USING 절에 현장 스코프
(site_id 일치)도 직접 강제해 '현장 + 조직경로/역할' 둘 다 만족해야만 노출되게 한다.

배포 주의: transaction pooler 에서 set_config(is_local=true) 가 요청 트랜잭션 전체에
전파되는지, 앱 role 이 non-bypassrls 인지 통합 스모크로 확인한 뒤 운영 적용한다
(샌드박스에서는 라이브 행노출 검증 불가 = deploy-pending). 1차 테넌트 격리는 app 계층
(CRUDBase.list 의 site_id 필터)에서 보조 강제됨.
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
    -- ★ENABLE+FORCE 는 site_id 보유 테이블(=p_site 가 실제 생기는 테이블)에만 적용한다.
    --   정책 0개 테이블에 FORCE 를 걸면 non-bypassrls role 에서 '전 행 거부'로 앱이 브릭된다.
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name=r.tablename AND column_name='site_id') THEN
      EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', r.tablename);
      EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY;', r.tablename);
      EXECUTE format('DROP POLICY IF EXISTS p_site ON %I;', r.tablename);
      EXECUTE format($f$CREATE POLICY p_site ON %I USING (
          site_id = nullif(current_setting('app.site_id', true),'')::uuid
          OR current_setting('app.role', true) = 'SUPERADMIN');$f$, r.tablename);
    END IF;
  END LOOP;
  -- sales_org_nodes 는 site_id 도 보유하므로 위 루프에서 ENABLE+FORCE+p_site 가 이미 적용됨.
  -- 추가로 p_org 를 RESTRICTIVE(AND 결합)로 걸어 현장 스코프 무력화를 차단한다.
  DROP POLICY IF EXISTS p_org ON sales_org_nodes;
  CREATE POLICY p_org ON sales_org_nodes AS RESTRICTIVE USING (
    (site_id = nullif(current_setting('app.site_id', true),'')::uuid
     OR current_setting('app.role', true) = 'SUPERADMIN')
    AND (current_setting('app.role', true) IN ('AGENCY','DEVELOPER','SUPERADMIN')
         OR path <@ nullif(current_setting('app.org_path', true),'')::ltree) );
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
