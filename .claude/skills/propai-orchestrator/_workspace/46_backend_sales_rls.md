# Phase 0 — 분양(sales) RLS 보안토대 (Backend)

## 1. 신규/변경 파일 · 엔드포인트 · 마운트
- 신규 `apps/api/app/services/sales/sales_rls_bootstrap.py`
  - `ensure_sales_rls(db, *, only_table=None, dry_run=False) -> dict`
  - `rls_status(db) -> dict`
  - `disable_sales_rls(db) -> dict`
- 신규 `apps/api/app/routers/admin_sales_rls.py` (admin 게이팅, prefix `/api/v1/admin/sales-rls`)
  - `GET  /status`   → rls_status
  - `POST /apply`    body `{only_table?, dry_run?}` → ensure_sales_rls (admin만)
  - `POST /rollback` → disable_sales_rls (admin만)
- 변경 `apps/api/main.py` : admin_secrets 마운트 직후 try/except 블록으로 admin_sales_rls 라우터 마운트(동일 패턴).

세션: 엔드포인트는 기존 `apps.api.database.session.get_db` Depends 사용(analysis_ledger/admin_secrets와 동일 패턴). 서비스는 주입된 `db`(AsyncSession)로 동작.

## 2. 정책 USING 절 (v62_2 일치 · FORCE 제외)
- p_site:
  `(site_id = nullif(current_setting('app.site_id', true),'')::uuid OR current_setting('app.role', true) = 'SUPERADMIN')`
  - v62_2 와 동일 의미. ★`nullif(...,'')` 가드 추가(빈문자열→NULL 캐스트 에러 방지). deps_sales 가 `set_config('app.site_id', str(site_id), true)` 주입과 정합.
- p_org (sales_org_nodes):
  `(current_setting('app.role', true) IN ('AGENCY','DEVELOPER','SUPERADMIN') OR path <@ current_setting('app.org_path', true)::ltree)`
  - v62_2 그대로.
- ★FORCE ROW LEVEL SECURITY 미적용 — ENABLE 만. 앱 DB role=postgres(bypassrls=True) 라 ENABLE 만으로 앱 쿼리 무중단 우회, PostgREST anon/authenticated 표면만 보호. 생성 SQL/반환 `force:false` 로 검증.

## 3. 멱등성 · site_id 동적조회
- 멱등: 각 테이블 `ALTER TABLE ENABLE ROW LEVEL SECURITY`(반복 무해) + `DROP POLICY IF EXISTS p_site/p_org` + `CREATE POLICY`. 반복 호출 안전.
- site_id 동적조회: information_schema.columns 에서 `column_name='site_id'` AND `table_name LIKE 'sales\_%' OR 'mh\_%'` AND BASE TABLE 만 조회 → 그 테이블에만 p_site 적용. site_id 미보유 테이블엔 정책 미적용(에러 방지). p_org 는 sales_org_nodes 1개에만.
- only_table(카나리): site_id 보유 테이블이면 p_site, sales_org_nodes 면 p_org(+site_id 보유 시 p_site 동시), 그 외엔 skipped(에러 없이).
- dry_run: information_schema 조회만 수행, DDL 미실행·미커밋, 생성 SQL 을 `dry_sql` 로 반환.

## 4. rls_status / rollback
- rls_status: pg_class.relrowsecurity/relforcerowsecurity + pg_policy 카운트로 sales_/mh_ 테이블별 `{rls_enabled, rls_forced, policy_count}` + 집계(total/rls_enabled/with_policy/forced).
- disable_sales_rls(롤백 1콜): 전 sales_/mh_ BASE TABLE 에 `DROP POLICY IF EXISTS p_site/p_org` + `DISABLE ROW LEVEL SECURITY`.

## 5. 로컬검증 (실DB 미연결 · 구문/로직)
- AST 구문: 두 신규 파일 + main.py OK.
- 라우터: 3개 라우트 정확 등록 (`/status` GET, `/apply` POST, `/rollback` POST), admin 게이팅·CurrentUser import 해소(repo root + apps.api.*).
- dry_run 로직(fake DB, information_schema만 모킹):
  - 생성 SQL 에 `FORCE ROW LEVEL SECURITY` 없음. `force:false`.
  - ENABLE 수 = site_id 테이블 수 + org 1.
  - p_site/p_org USING 절이 위 문자열과 정확 일치.
  - 카나리: site 테이블→applied 1, org→org_applied, 비-site→skipped(무에러).
  - 비-dry: DDL 실행 후 commit, FORCE 없음.
  - rollback: DISABLE + DROP, count 정확.
- 실DB 변경 없음(엔드포인트만, 오케스트레이터가 카나리부터 호출).

## 6. 커밋
`feat(sales-rls): Phase0 RLS 부트스트랩(ENABLE+p_site/p_org 멱등)·관리자 적용/상태/롤백 엔드포인트`
(해시는 보고 본문 참조)

## 7. 오케스트레이터 적용 가이드
1. 먼저 상태 확인: `GET /api/v1/admin/sales-rls/status` (전 sales_/mh_ rowsecurity 0 확인).
2. dry_run 으로 생성 SQL 검토: `POST /apply {"dry_run": true}` → dry_sql·force:false·정책 USING 확인.
3. 카나리 1테이블만 실적용: `POST /apply {"only_table": "sales_payments"}` (추천: 쓰기빈번·site_id 보유, 영향 격리 쉬운 테이블).
   - 검증 쿼리(앱 우회 확인): 앱 정상 동작 무중단(postgres bypassrls). PostgREST 표면에서
     `SET app.site_id='<다른site>'; SELECT * FROM sales_payments;` → 0행,
     `SET app.role='SUPERADMIN'; SELECT ...` → 전행. `SET app.site_id='<해당site>'` → 해당행만.
   - status 재확인: 해당 테이블 rls_enabled=true, policy_count=1, rls_forced=false.
4. 카나리 OK 시 전체 적용: `POST /apply {}` (only_table 생략).
5. 이상 시 즉시 롤백: `POST /rollback` (전 테이블 DISABLE+DROP, 무중단).

추천 카나리 테이블: `sales_payments` 또는 `sales_contracts`(site_id 보유·트랜잭션 명확). `sales_org_nodes` 는 p_org+p_site 동시 적용되므로 단독 카나리보다 site 테이블 1개 우선 권장.
