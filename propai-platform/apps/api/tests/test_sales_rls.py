"""#1 현장 인증·보안·RLS — 역할별 의도 회귀 안전망(순수/구문 검증).

본 스위트는 '라이브 DB 행노출' 이 아니라, 회귀가 자주 나는 구문/순수 분기를 고정한다:
- 정책 USING 절(_P_SITE_USING/_P_ORG_USING)이 fail-closed(nullif) 가드를 갖는지.
- 부트스트랩이 ENABLE+FORCE 를 항상 함께 생성하는지(소유자/BYPASSRLS 우회 차단).
- 마이그레이션 정본(v62_2_sales_rls)과 런타임 부트스트랩의 USING 절이 1:1 일치하는지.
- deps_sales._apply_session_ctx 가 set_config(..., is_local=true)=SET LOCAL 로만 주입하는지
  (풀러 누수 방지) + 빈 org_path 를 'none' 센티넬이 아닌 ''(→정책 nullif→NULL) 로 주입하는지.
- sales_crypto: 평문 미저장·timing-safe verify(hmac.compare_digest).

★deploy-pending(샌드박스 불가) = skip: 실제 RLS 행노출(FORCE 실효·풀러 세션 누수)은 라이브
PostgreSQL + non-bypassrls role 이 있어야 검증 가능하다. 해당 테스트는 명시적 skip 마크.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.api import deps_sales  # noqa: E402
from app.core import sales_crypto  # noqa: E402
from app.services.sales import sales_rls_bootstrap as boot  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# 가짜 async DB — 실행된 SQL/파라미터를 기록(구문/주입 검증용, 라이브 DB 불필요).
# ──────────────────────────────────────────────────────────────────────────────
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


from sqlalchemy.orm import Session as _OrmSession  # noqa: E402


class _FakeDB:
    """sales_rls_bootstrap / _apply_session_ctx 가 쓰는 execute/commit/sync_session 만 흉내낸다.

    site_tables: _fetch_site_tables 가 받는 site_id 보유 테이블 목록.
    executed:    실행된 (sql_text, params) 튜플 기록.
    sync_session: _apply_session_ctx 가 after_begin 리스너 등록·컨텍스트 보관에 쓰는 객체.
                  실제 SQLAlchemy Session(바인드 없음) — 이벤트 등록만 가능하면 되고 쿼리는
                  본 가짜 db.execute 가 받으므로 Session 으로 실행하지 않는다.
    """

    def __init__(self, site_tables=None):
        self._site_tables = site_tables or []
        self.executed: list[tuple[str, dict | None]] = []
        self.committed = 0
        self.sync_session = _OrmSession()

    async def execute(self, statement, params=None):
        sql = str(getattr(statement, "text", statement))
        self.executed.append((sql, params))
        # _fetch_site_tables 의 SELECT 만 행을 돌려주면 됨.
        if "column_name = 'site_id'" in sql:
            return _FakeResult([(t,) for t in self._site_tables])
        return _FakeResult([])

    async def commit(self):
        self.committed += 1


# ──────────────────────────────────────────────────────────────────────────────
# (b) 정책 USING 절 — fail-closed(3치논리) 가드.
# ──────────────────────────────────────────────────────────────────────────────
def test_p_site_using_has_nullif_failclosed_guard():
    """app.site_id 미설정/빈문자열 → nullif 로 NULL → 'site_id = NULL' = NULL → 행 비노출."""
    s = boot._P_SITE_USING
    assert "nullif(current_setting('app.site_id', true),'')::uuid" in s
    # 빈문자열을 그대로 ::uuid 캐스트하면 에러 → 반드시 nullif 로 감싸야 함.
    assert "current_setting('app.site_id', true)::uuid" not in s
    # SUPERADMIN 우회 분기 존재(미설정 role 은 NULL → 통과 안 함 = fail-closed).
    assert "current_setting('app.role', true) = 'SUPERADMIN'" in s


def test_p_org_using_has_nullif_failclosed_guard():
    """app.org_path 미설정/빈문자열 → nullif 로 NULL → 'path <@ NULL' = NULL → 행 비노출."""
    s = boot._P_ORG_USING
    assert "nullif(current_setting('app.org_path', true),'')::ltree" in s
    # 빈문자열을 그대로 ::ltree 캐스트하면 에러 → 반드시 nullif 로 감싸야 함.
    assert "current_setting('app.org_path', true)::ltree" not in s
    assert "current_setting('app.role', true) IN ('AGENCY','DEVELOPER','SUPERADMIN')" in s


# ──────────────────────────────────────────────────────────────────────────────
# (a) ENABLE+FORCE 를 항상 함께 생성(소유자/BYPASSRLS 우회 차단).
# ──────────────────────────────────────────────────────────────────────────────
def test_site_statements_emit_enable_and_force():
    stmts = boot._site_statements("sales_units")
    joined = "\n".join(stmts)
    assert 'ALTER TABLE "sales_units" ENABLE ROW LEVEL SECURITY;' in stmts
    assert 'ALTER TABLE "sales_units" FORCE ROW LEVEL SECURITY;' in stmts
    # 멱등: 정책은 DROP IF EXISTS 후 CREATE.
    assert 'DROP POLICY IF EXISTS p_site ON "sales_units";' in stmts
    assert 'CREATE POLICY p_site ON "sales_units"' in joined
    # ENABLE 이 FORCE 보다 먼저(둘 다 존재).
    assert stmts.index('ALTER TABLE "sales_units" ENABLE ROW LEVEL SECURITY;') < stmts.index(
        'ALTER TABLE "sales_units" FORCE ROW LEVEL SECURITY;'
    )


def test_org_statements_emit_enable_and_force():
    stmts = boot._org_statements()
    assert 'ALTER TABLE "sales_org_nodes" ENABLE ROW LEVEL SECURITY;' in stmts
    assert 'ALTER TABLE "sales_org_nodes" FORCE ROW LEVEL SECURITY;' in stmts
    assert 'DROP POLICY IF EXISTS p_org ON "sales_org_nodes";' in stmts


def test_quote_ident_blocks_injection():
    """식별자 인용 — 큰따옴표 이스케이프(방어적)."""
    assert boot._quote_ident('a"b') == '"a""b"'
    assert boot._quote_ident("sales_units") == '"sales_units"'


# ──────────────────────────────────────────────────────────────────────────────
# (a/d) ensure_sales_rls — dry_run(구문 생성)·실행(advisory lock·commit) 검증.
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ensure_dry_run_generates_force_and_no_commit():
    db = _FakeDB(site_tables=["sales_units", "sales_contracts"])
    res = await boot.ensure_sales_rls(db, dry_run=True)
    assert res["force"] is True
    assert res["dry_run"] is True
    assert set(res["applied"]) == {"sales_units", "sales_contracts"}
    assert res["org_applied"] is True
    sql_all = "\n".join(res["dry_sql"])
    assert "FORCE ROW LEVEL SECURITY" in sql_all
    assert sql_all.count("FORCE ROW LEVEL SECURITY") >= 3  # 2 site + 1 org
    # dry_run 은 실행/lock/commit 하지 않음(SELECT site_tables 1회만 실행됨).
    assert db.committed == 0
    assert not any("pg_advisory_xact_lock" in s for s, _ in db.executed)


@pytest.mark.asyncio
async def test_ensure_apply_takes_advisory_lock_and_commits():
    db = _FakeDB(site_tables=["sales_units"])
    res = await boot.ensure_sales_rls(db, dry_run=False)
    assert res["force"] is True
    # race 제거용 advisory lock 획득(트랜잭션 종료 시 자동 해제).
    assert any("pg_advisory_xact_lock" in s for s, _ in db.executed)
    # FORCE DDL 이 실제 실행됨.
    assert any("FORCE ROW LEVEL SECURITY" in s for s, _ in db.executed)
    assert db.committed == 1


@pytest.mark.asyncio
async def test_ensure_only_table_canary_skips_unknown():
    db = _FakeDB(site_tables=["sales_units"])
    res = await boot.ensure_sales_rls(db, only_table="not_a_sales_table", dry_run=True)
    # site_id 미보유 & org 아님 → 에러 대신 skip(은폐 아님, 명시 skip).
    assert "not_a_sales_table" in res["skipped"]
    assert res["applied"] == []


# ──────────────────────────────────────────────────────────────────────────────
# (c) deps_sales._apply_session_ctx — SET LOCAL(is_local=true)·fail-closed 정합.
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_apply_session_ctx_uses_set_local_true():
    """모든 주입이 set_config(..., true) = SET LOCAL 이어야 풀러 누수가 없다."""
    db = _FakeDB()
    await deps_sales._apply_session_ctx(
        db, site_id="11111111-1111-1111-1111-111111111111", org_path="root.agency", role="AGENCY"
    )
    set_calls = [(s, p) for s, p in db.executed if "set_config" in s]
    assert len(set_calls) == 3
    # is_local=true 만 사용(절대 false 없음).
    for sql, _ in set_calls:
        assert "set_config(:k, :v, true)" in sql
    keys = {p["k"] for _, p in set_calls}
    assert keys == {"app.site_id", "app.org_path", "app.role"}
    by_key = {p["k"]: p["v"] for _, p in set_calls}
    assert by_key["app.site_id"] == "11111111-1111-1111-1111-111111111111"
    assert by_key["app.org_path"] == "root.agency"
    assert by_key["app.role"] == "AGENCY"


@pytest.mark.asyncio
async def test_apply_session_ctx_empty_orgpath_is_blank_not_none_sentinel():
    """빈 org_path 는 ''(→정책 nullif→NULL=fail-closed) 로 주입. 과거 'none' 센티넬 회귀 차단."""
    db = _FakeDB()
    await deps_sales._apply_session_ctx(db, site_id="sid", org_path="", role="DEVELOPER")
    by_key = {p["k"]: p["v"] for s, p in db.executed if "set_config" in s}
    assert by_key["app.org_path"] == ""        # 'none' 아님
    assert by_key["app.org_path"] != "none"


@pytest.mark.asyncio
async def test_apply_session_ctx_falsy_inputs_blank():
    """site_id/role 미설정도 '' 로 주입(정책에서 NULL→fail-closed)."""
    db = _FakeDB()
    await deps_sales._apply_session_ctx(db, site_id=None, org_path=None, role="")
    by_key = {p["k"]: p["v"] for s, p in db.executed if "set_config" in s}
    assert by_key["app.site_id"] == ""
    assert by_key["app.org_path"] == ""
    assert by_key["app.role"] == ""


# ──────────────────────────────────────────────────────────────────────────────
# (a) 마이그레이션 정본 ↔ 런타임 부트스트랩 USING 절 1:1 정합(불일치 회귀 차단).
# ──────────────────────────────────────────────────────────────────────────────
def _read_migration_sql() -> str:
    here = os.path.dirname(__file__)
    path = os.path.join(
        here, "..", "database", "migrations", "versions", "v62_2_sales_rls.py"
    )
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_migration_has_force_and_failclosed_guards():
    sql = _read_migration_sql()
    assert "FORCE ROW LEVEL SECURITY" in sql
    # 정본도 nullif 가드(fail-closed) 적용.
    assert "nullif(current_setting('app.site_id', true),'')::uuid" in sql
    assert "nullif(current_setting('app.org_path', true),'')::ltree" in sql
    # 가드 없는 직접 캐스트가 남아있으면 회귀(빈문자열 캐스트 에러/노출 위험).
    assert "current_setting('app.site_id', true)::uuid" not in sql
    assert "current_setting('app.org_path', true)::ltree" not in sql


def test_migration_and_bootstrap_use_same_predicate_fragments():
    """정본·런타임이 동일 술어(site_id 비교, role-IN, path<@)를 쓰는지(드리프트 방지)."""
    sql = _read_migration_sql()
    # site 술어 핵심 조각.
    assert "site_id = nullif(current_setting('app.site_id', true),'')::uuid" in sql
    assert "site_id = nullif(current_setting('app.site_id', true),'')::uuid" in boot._P_SITE_USING
    # org 술어 핵심 조각.
    assert "current_setting('app.role', true) IN ('AGENCY','DEVELOPER','SUPERADMIN')" in sql
    assert (
        "current_setting('app.role', true) IN ('AGENCY','DEVELOPER','SUPERADMIN')"
        in boot._P_ORG_USING
    )
    assert "path <@ nullif(current_setting('app.org_path', true),'')::ltree" in sql
    assert "path <@ nullif(current_setting('app.org_path', true),'')::ltree" in boot._P_ORG_USING


# ──────────────────────────────────────────────────────────────────────────────
# (e) sales_crypto — 평문 미저장·결정적 블라인드 인덱스·timing-safe verify.
# ──────────────────────────────────────────────────────────────────────────────
def test_encrypt_is_deterministic_and_not_plaintext():
    a = sales_crypto.encrypt("110-1234-5678")
    b = sales_crypto.encrypt("110-1234-5678")
    assert a == b                       # 결정적(조회/대사 가능).
    assert a != "110-1234-5678"         # 평문 미저장.
    assert len(a) == 64                 # SHA-256 hexdigest.


def test_encrypt_none_is_empty():
    assert sales_crypto.encrypt(None) == ""


def test_verify_is_timing_safe_and_correct():
    blind = sales_crypto.encrypt("acct-9999")
    assert sales_crypto.verify("acct-9999", blind) is True
    assert sales_crypto.verify("acct-0000", blind) is False
    assert sales_crypto.verify(None, blind) is False
    assert sales_crypto.verify("acct-9999", None) is False


def test_decrypt_unsupported_returns_none():
    assert sales_crypto.decrypt("anything") is None


# ──────────────────────────────────────────────────────────────────────────────
# (1) 마이그레이션 정본 — FORCE 를 '정책 0개 테이블'에 적용하지 않음(앱 브릭 landmine 제거).
#     site_id 보유 테이블에만 ENABLE+FORCE+p_site 가 걸리는 구조여야 한다.
# ──────────────────────────────────────────────────────────────────────────────
def test_migration_force_only_inside_site_id_guard():
    """ENABLE/FORCE 가 site_id 보유 가드(IF EXISTS) 안에서만 실행돼야 한다.

    과거 회귀: FOR 루프 최상단에서 전 sales_/mh_ 테이블에 무차별 ENABLE+FORCE 를 걸어
    정책 0개 테이블이 FORCE+정책0 → 전 행 거부(앱 브릭)였다. 가드 밖 무차별 적용 차단.
    """
    sql = _read_migration_sql()
    # FORCE 는 등장하되, IF EXISTS(site_id) 가드 블록 '뒤'에 위치해야 한다(가드 안에서 실행).
    assert "FORCE ROW LEVEL SECURITY" in sql
    guard = "WHERE table_name=r.tablename AND column_name='site_id'"
    assert guard in sql
    # 가드보다 먼저 나오는 FORCE 가 있으면(=루프 상단 무차별 적용) 회귀.
    first_guard = sql.index(guard)
    first_force = sql.index("FORCE ROW LEVEL SECURITY")
    assert first_force > first_guard, "FORCE 가 site_id 가드보다 먼저 = 무차별 FORCE-all 회귀"
    # 루프 본문에서 가드 밖 ENABLE(=무차별)이 없어야 함: ENABLE 도 가드 뒤에 위치.
    assert sql.index("ENABLE ROW LEVEL SECURITY") > first_guard


def test_migration_p_org_is_restrictive_with_site_scope():
    """p_org 가 RESTRICTIVE 이고 USING 절에 현장 스코프(site_id 일치)를 직접 강제해야 한다.

    PERMISSIVE 면 p_site 와 OR 결합돼 role-IN 광역분기가 현장격리를 무력화(타 현장 노출).
    """
    sql = _read_migration_sql()
    assert "CREATE POLICY p_org ON sales_org_nodes AS RESTRICTIVE" in sql
    # p_org USING 에 site_id 스코프가 AND 로 들어가야 함.
    assert "site_id = nullif(current_setting('app.site_id', true),'')::uuid" in sql
    # role-IN 광역분기는 여전히 존재하나 site 스코프와 AND 결합(OR 단독 무력화 차단).
    assert "current_setting('app.role', true) IN ('AGENCY','DEVELOPER','SUPERADMIN')" in sql


def test_bootstrap_p_org_is_restrictive_and_site_scoped():
    """런타임 부트스트랩의 _org_statements 가 RESTRICTIVE + site 스코프 USING 을 생성하는지."""
    stmts = boot._org_statements()
    joined = "\n".join(stmts)
    assert "CREATE POLICY p_org ON \"sales_org_nodes\" AS RESTRICTIVE" in joined
    # USING 절에 site_id 스코프(현장 강제)가 포함.
    assert "site_id = nullif(current_setting('app.site_id', true),'')::uuid" in boot._P_ORG_USING
    # 현장 스코프 AND 역할/조직경로 — 두 조건이 AND 로 결합.
    assert " AND " in boot._P_ORG_USING


def test_force_scope_matches_policy_scope_in_bootstrap():
    """부트스트랩 FORCE 적용범위 == 정책 적용범위(정책 0개 테이블에 FORCE 미적용).

    _site_statements/_org_statements 만 FORCE 를 방출하며, 둘 다 정책(p_site/p_org)을
    함께 방출한다 → FORCE 가 걸리는 테이블은 반드시 정책이 있는 테이블이다.
    """
    site_stmts = boot._site_statements("sales_units")
    assert any("FORCE ROW LEVEL SECURITY" in s for s in site_stmts)
    assert any("CREATE POLICY p_site" in s for s in site_stmts)
    org_stmts = boot._org_statements()
    assert any("FORCE ROW LEVEL SECURITY" in s for s in org_stmts)
    assert any("CREATE POLICY p_org" in s for s in org_stmts)


@pytest.mark.asyncio
async def test_ensure_does_not_force_policyless_tables():
    """ensure_sales_rls: site_id 미보유 & org 아닌 테이블엔 FORCE/ENABLE 가 방출되지 않는다.

    site_tables 에 없는 테이블(=정책 0개)은 dry_sql 어디에도 ALTER TABLE 가 없어야 한다.
    """
    db = _FakeDB(site_tables=["sales_units"])  # 정책 대상은 sales_units + sales_org_nodes 뿐.
    res = await boot.ensure_sales_rls(db, dry_run=True)
    sql_all = "\n".join(res["dry_sql"])
    # 정책 0개 테이블 예시는 어디에도 나오지 않아야 함.
    for policyless in ("sales_commission_holdback", "sales_contract_installments", "mh_inventory_txns"):
        assert policyless not in sql_all
    # FORCE 가 등장한 모든 ALTER 대상은 sales_units 또는 sales_org_nodes 뿐.
    force_lines = [ln for ln in res["dry_sql"] if "FORCE ROW LEVEL SECURITY" in ln]
    for ln in force_lines:
        assert ('"sales_units"' in ln) or ('"sales_org_nodes"' in ln)


# ──────────────────────────────────────────────────────────────────────────────
# (3) commit 후 자동 재주입 — _apply_session_ctx 가 ctx 보관 + after_begin 리스너 등록.
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_apply_session_ctx_stores_ctx_and_registers_listener():
    """주입값을 sync_session.info 에 보관하고 리스너 1회 등록(commit 후 재주입 토대)."""
    db = _FakeDB()
    await deps_sales._apply_session_ctx(db, site_id="sid-1", org_path="root.a", role="AGENCY")
    info = db.sync_session.info
    stored = info[deps_sales._INFO_CTX_KEY]
    assert stored["app.site_id"] == "sid-1"
    assert stored["app.org_path"] == "root.a"
    assert stored["app.role"] == "AGENCY"
    # 리스너 등록 가드 플래그가 켜져야 함(중복 등록 방지).
    assert info[deps_sales._INFO_LISTENER_KEY] is True


@pytest.mark.asyncio
async def test_apply_session_ctx_listener_registered_once():
    """같은 세션에 두 번 주입해도 리스너는 1회만 등록(멱등)."""
    db = _FakeDB()
    await deps_sales._apply_session_ctx(db, site_id="sid-1", org_path="", role="DEVELOPER")
    # 2회차: 컨텍스트만 갱신, 리스너 재등록 없음(가드).
    await deps_sales._apply_session_ctx(db, site_id="sid-2", org_path="", role="DEVELOPER")
    assert db.sync_session.info[deps_sales._INFO_CTX_KEY]["app.site_id"] == "sid-2"
    assert db.sync_session.info[deps_sales._INFO_LISTENER_KEY] is True


def test_set_config_sync_reinjects_set_local():
    """동기 재주입 헬퍼가 set_config(..., true)=SET LOCAL 3종을 connection 에 실행하는지."""
    calls: list[tuple[str, dict | None]] = []

    class _Conn:
        def execute(self, statement, params=None):
            calls.append((str(getattr(statement, "text", statement)), params))

    values = {"app.site_id": "sid", "app.org_path": "", "app.role": "AGENCY"}
    deps_sales._set_config_sync(_Conn(), values)
    assert len(calls) == 3
    for sql, _ in calls:
        assert "set_config(:k, :v, true)" in sql  # SET LOCAL 의미 유지(풀러 누수 없음).
    assert {p["k"] for _, p in calls} == {"app.site_id", "app.org_path", "app.role"}


@pytest.mark.asyncio
async def test_sales_ctx_reapply_uses_single_helper():
    """SalesCtx.reapply(db) 가 _apply_session_ctx 를 경유해 동일 3종을 재주입한다."""
    db = _FakeDB()
    ctx = deps_sales.SalesCtx("sid-9", "root.b", "MEMBER", user=object())
    await ctx.reapply(db)
    by_key = {p["k"]: p["v"] for s, p in db.executed if "set_config" in s}
    assert by_key == {"app.site_id": "sid-9", "app.org_path": "root.b", "app.role": "MEMBER"}


# ──────────────────────────────────────────────────────────────────────────────
# (4) sales_ctx 멤버십 조회 — soft-deleted 노드 제외(deleted_at.is_(None)) 일원화.
# ──────────────────────────────────────────────────────────────────────────────
def test_sales_ctx_membership_filters_soft_deleted():
    """sales_ctx 의 SalesOrgNode 멤버십 조회 소스에 deleted_at.is_(None) 필터가 있어야 한다.

    누락 시 soft-deleted 노드가 RLS 세션변수+SalesCtx 를 부여받는 격리 위험(MEDIUM).
    _resolve_role/my_sites 와 동일 기준으로 일원화.
    """
    import inspect

    src = inspect.getsource(deps_sales.sales_ctx)
    assert "SalesOrgNode.deleted_at.is_(None)" in src
    assert "SalesOrgNode.active.is_(True)" in src  # 기존 필터 보존(무회귀).


# ──────────────────────────────────────────────────────────────────────────────
# (d) deploy-pending — 라이브 RLS 행노출/풀러 누수/FORCE 실효(샌드박스 불가) = skip.
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.skip(
    reason="deploy-pending: 라이브 PostgreSQL + non-bypassrls role 필요(샌드박스 불가). "
    "FORCE 실효·세션변수 풀러 누수·정책 행노출은 운영 환경에서 통합 스모크로 검증."
)
def test_live_rls_row_isolation_force_effective():  # pragma: no cover
    """[deploy-pending] 다른 site_id 세션변수로는 타 현장 행이 0건이어야 한다(FORCE 실효)."""
    raise AssertionError("requires live DB")


@pytest.mark.skip(
    reason="deploy-pending: pgbouncer/asyncpg 트랜잭션 풀러에서 SET LOCAL 누수 없음(다음 "
    "요청에 app.* 미전파)을 라이브로 검증해야 함(샌드박스 불가)."
)
def test_live_session_var_no_pooler_leak():  # pragma: no cover
    """[deploy-pending] 커넥션 재사용 시 직전 요청의 app.site_id 가 남지 않아야 한다."""
    raise AssertionError("requires live pooler")
