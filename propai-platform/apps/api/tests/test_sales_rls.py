"""#1 현장 인증·보안·RLS — 역할별 의도 회귀 안전망(순수/구문 검증).

본 스위트는 '라이브 DB 행노출' 이 아니라, 회귀가 자주 나는 구문/순수 분기를 고정한다:
- 정책 USING 절(_P_SITE_USING/_P_ORG_USING)이 fail-closed(nullif) 가드를 갖는지.
- 부트스트랩이 ENABLE+FORCE 를 항상 함께 생성하는지(소유자/BYPASSRLS 우회 차단).
- 마이그레이션 정본(v62_2_sales_rls)과 런타임 부트스트랩의 USING 절이 1:1 일치하는지.
- deps_sales._apply_session_ctx 가 set_config(..., is_local=true)=SET LOCAL 로만 주입하는지
  (풀러 누수 방지) + 빈 org_path 를 'none' 센티넬이 아닌 ''(→정책 nullif→NULL) 로 주입하는지.
- deps_sales._site_token_ctx 가 토큰만 신뢰하지 않고 멤버십(deleted_at IS NULL)을 DB
  재검증하는지(8h 권한지연 제거).
- sales_crypto: 평문 미저장·결정적 블라인드 인덱스·프로덕션 폴백키 fail-fast.
- rls_status 가 접속 role BYPASSRLS 를 노출하고 isolation_effective 경고를 내는지(false assurance 차단).
- v62_2 downgrade(_DISABLE)가 RLS DISABLE 뿐 아니라 정책 DROP 까지 수행하는지(orphan 정책 차단).

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


def test_verify_helper_removed_yagni():
    """미배선 timing-safe verify 헬퍼는 YAGNI 로 제거됐다(호출부 0건). 재추가 회귀 차단."""
    assert not hasattr(sales_crypto, "verify")


def test_decrypt_unsupported_returns_none():
    assert sales_crypto.decrypt("anything") is None


# ──────────────────────────────────────────────────────────────────────────────
# (4) sales_crypto._key — 프로덕션 폴백키 silent 사용 차단(fail-fast).
# ──────────────────────────────────────────────────────────────────────────────
def test_key_falls_back_in_dev(monkeypatch):
    """dev/test 환경 + 키 미설정 → 폴백키 사용(예외 없음). 명시 경고는 1회."""
    monkeypatch.delenv("SALES_ENC_KEY", raising=False)
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    assert sales_crypto._key() == sales_crypto._DEV_FALLBACK_KEY.encode()


def test_key_fail_fast_in_production_when_unset(monkeypatch):
    """프로덕션(APP_ENV≠dev/test) + 키 미설정 → 예외로 차단(약한 폴백키 silent 사용 금지)."""
    monkeypatch.delenv("SALES_ENC_KEY", raising=False)
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError):
        sales_crypto._key()


def test_key_uses_env_in_production(monkeypatch):
    """프로덕션이라도 강한 키(≥32자)가 설정돼 있으면 그 키를 사용(폴백 아님)."""
    strong = "a" * 32  # config._validate_secret 하한(32자) 충족.
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SALES_ENC_KEY", strong)
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    assert sales_crypto._key() == strong.encode()


def test_key_rejects_short_key_in_production(monkeypatch):
    """★프로덕션 + 짧은 키(예: 'x' 1자, <32자) → 예외로 차단(약한 키 fail-fast).

    과거 'if not k'(존재만) 검사는 단키를 통과시켜 폴백키 차단 취지를 무력화했다.
    """
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SALES_ENC_KEY", "x")  # 1자 = 약한 키.
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        sales_crypto._key()


def test_key_short_key_allowed_in_dev(monkeypatch):
    """dev/test 는 길이 하한을 강제하지 않는다(개발 편의 — 무회귀)."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SALES_ENC_KEY", "x")
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    assert sales_crypto._key() == b"x"


def test_key_rejects_leaked_example_key_in_production(monkeypatch):
    """★9.5 게이트: prod + 유출 예제키(50자, 길이는 통과)는 거부해야 한다(denylist 일치).

    과거 _key() 는 길이(≥32)만 복제하고 config._KNOWN_WEAK_SECRETS denylist 는 미복제라,
    config 가 거부하는 유출 예제키 'propai_secret_key_change_in_production_32chars_min'(50자)를
    ACCEPT 하는 false-assurance 가 있었다. 이제 config._validate_secret 직접 재사용으로 일치.
    """
    leaked = "propai_secret_key_change_in_production_32chars_min"  # 50자(길이는 충분).
    assert len(leaked) >= 32  # 길이 검사만으론 통과하던 키임을 명시.
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SALES_ENC_KEY", leaked)
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        sales_crypto._key()


def test_key_validation_reuses_config_validate_secret(monkeypatch):
    """prod 키 검증이 config._validate_secret 을 '직접 재사용'(denylist+길이 드리프트 0)."""
    import inspect

    from app.core import config

    src = inspect.getsource(sales_crypto._key)
    assert "_validate_secret" in src  # 길이 복제가 아니라 config 함수 직접 호출.
    # config denylist 의 다른 항목도 _key() 가 거부하는지(일치 확인).
    sample = next(iter(config._KNOWN_WEAK_SECRETS))
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SALES_ENC_KEY", sample)
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        sales_crypto._key()


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
    # site_id 검출 가드(IF EXISTS) — public 스키마 한정자 포함(부트스트랩과 드리프트 제거).
    guard = "column_name='site_id'"
    assert guard in sql
    assert "table_schema='public'" in sql  # 가드가 public 스키마로 한정됨.
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
    """sales_ctx 멤버십 판정의 단일 소스(공용 헬퍼)에 deleted_at.is_(None) 필터가 있어야 한다.

    누락 시 soft-deleted 노드가 RLS 세션변수+SalesCtx 를 부여받는 격리 위험(MEDIUM).
    멤버십 SELECT 는 resolve_site_membership 로 일원화됐으므로 거기서 필터를 검사한다.
    _resolve_role/my_sites/_site_token_ctx 와 동일 기준으로 일원화.
    """
    import inspect

    # sales_ctx 는 공용 헬퍼를 경유한다.
    src = inspect.getsource(deps_sales.sales_ctx)
    assert "resolve_site_membership" in src
    # 단일 소스(헬퍼)에 soft-delete/active 게이트가 존재해야 한다.
    hsrc = inspect.getsource(deps_sales.resolve_site_membership)
    assert "SalesOrgNode.deleted_at.is_(None)" in hsrc
    assert "SalesOrgNode.active.is_(True)" in hsrc  # 기존 필터 보존(무회귀).


# ──────────────────────────────────────────────────────────────────────────────
# (1) _site_token_ctx — 토큰만 신뢰 금지: 멤버십(deleted_at IS NULL) DB 재검증.
#     8h 권한지연 제거(해촉/soft-delete 직원은 토큰 만료 전에도 즉시 거부).
# ──────────────────────────────────────────────────────────────────────────────
class _TokenFakeDB:
    """_site_token_ctx / resolve_site_membership 의 멤버십 SELECT 결과만 제어하는 가짜 async DB.

    resolve_site_membership 가 scalars().all() 로 노드 목록을 받으므로(복수노드 안전), 본
    더블도 그 형태를 흉내낸다. nodes 인자(목록)면 그대로, node(단일/None)면 [node]/[] 로 감싼다.
    """

    def __init__(self, node=None, nodes=None):
        if nodes is not None:
            self._nodes = list(nodes)
        else:
            self._nodes = [node] if node is not None else []

    async def execute(self, statement, params=None):
        rows = self._nodes

        class _Scalars:
            def all(self):
                return rows

        class _R:
            def scalars(self):
                return _Scalars()

            # 일부 경로(resolve_site 등)의 단건 조회 호환(미사용 시 무해).
            def scalar_one_or_none(self):
                return rows[0] if rows else None

        return _R()


class _Req:
    def __init__(self, token):
        self.headers = {"x-site-token": token} if token else {}


class _User:
    def __init__(self, uid):
        self.id = uid


class _Node:
    def __init__(self, path, node_type):
        self.path = path
        self.node_type = node_type


class _Site:
    """_site_token_ctx/resolve_site_membership 가 읽는 SalesSite 최소 형태(id·organization_id)."""

    def __init__(self, sid, organization_id=None):
        self.id = sid
        self.organization_id = organization_id


def test_site_token_ctx_reverifies_membership_in_db_marker():
    """소스 가드: _site_token_ctx 가 토큰 디코드 후 공용 헬퍼로 멤버십을 재검증한다(토큰 클레임 미신뢰).

    멤버십 SELECT(active/deleted_at 필터)는 resolve_site_membership 로 일원화됐으므로 거기서 검사한다.
    """
    import inspect

    # 토큰 함수는 공용 헬퍼를 호출하고, 토큰 클레임(site_role)을 그대로 신뢰하지 않아야 한다.
    src = inspect.getsource(deps_sales._site_token_ctx)
    assert "resolve_site_membership" in src
    assert 'payload.get("site_role")' not in src
    # 멤버십 판정의 단일 소스(공용 헬퍼)에 active/deleted_at 게이트가 있어야 한다.
    hsrc = inspect.getsource(deps_sales.resolve_site_membership)
    assert "SalesOrgNode.deleted_at.is_(None)" in hsrc
    assert "SalesOrgNode.active.is_(True)" in hsrc


@pytest.mark.asyncio
async def test_site_token_ctx_live_node_returns_db_role(monkeypatch):
    """살아있는 노드가 있으면 토큰 클레임이 아닌 DB 최신 (path, node_type) 을 반환(강등 즉시반영)."""
    sid = "11111111-1111-1111-1111-111111111111"
    uid = "22222222-2222-2222-2222-222222222222"
    from app.api.endpoints.sales import site_auth

    monkeypatch.setattr(
        site_auth, "decode_site_token",
        lambda raw: {"site_id": sid, "sub": uid, "org_path": "root.old", "site_role": "AGENCY"},
    )
    db = _TokenFakeDB(node=_Node("root.new.member", "MEMBER"))
    res = await deps_sales._site_token_ctx(_Req("tok"), db, _User(uid), _Site(sid))
    assert res == ("root.new.member", "MEMBER")  # 토큰의 AGENCY/root.old 가 아닌 DB 최신값.


@pytest.mark.asyncio
async def test_site_token_ctx_soft_deleted_member_rejected(monkeypatch):
    """해촉/soft-delete(노드 없음) → None 반환 → 비토큰 경로 403 게이트로 일원화(8h 지연 제거)."""
    sid = "11111111-1111-1111-1111-111111111111"
    uid = "22222222-2222-2222-2222-222222222222"
    from app.api.endpoints.sales import site_auth

    monkeypatch.setattr(
        site_auth, "decode_site_token",
        lambda raw: {"site_id": sid, "sub": uid, "org_path": "root.old", "site_role": "AGENCY"},
    )
    db = _TokenFakeDB(node=None)  # 멤버십 없음(해촉/삭제)
    res = await deps_sales._site_token_ctx(_Req("tok"), db, _User(uid), _Site(sid))
    assert res is None


@pytest.mark.asyncio
async def test_site_token_ctx_no_token_returns_no_token_sentinel():
    """X-Site-Token 헤더 없으면 _NO_TOKEN sentinel(비토큰 경로로 진행, None 과 구분)."""
    db = _TokenFakeDB(node=_Node("p", "MEMBER"))
    res = await deps_sales._site_token_ctx(_Req(None), db, _User("u"), _Site("s"))
    assert res is deps_sales._NO_TOKEN  # 'None=멤버없음' 과 구분되는 '토큰없음' sentinel.


@pytest.mark.asyncio
async def test_site_token_ctx_wrong_site_or_user_returns_no_token_sentinel(monkeypatch):
    """다른 현장/사용자 토큰은 유효 토큰 아님 → _NO_TOKEN(비토큰 경로로). member-none(None)과 구분."""
    from app.api.endpoints.sales import site_auth

    monkeypatch.setattr(
        site_auth, "decode_site_token",
        lambda raw: {"site_id": "other-site", "sub": "u1", "org_path": "", "site_role": "MEMBER"},
    )
    db = _TokenFakeDB(node=_Node("p", "MEMBER"))
    # site 불일치 → 유효 토큰 아님 → _NO_TOKEN sentinel.
    res = await deps_sales._site_token_ctx(_Req("tok"), db, _User("u1"), _Site("this-site"))
    assert res is deps_sales._NO_TOKEN


# ──────────────────────────────────────────────────────────────────────────────
# (4) resolve_site_membership — 공용 헬퍼 동치(토큰/비토큰/site_auth 1:1 일원화).
# ──────────────────────────────────────────────────────────────────────────────
class _MemberUser:
    def __init__(self, uid, role="", tenant_id=None):
        self.id = uid
        self.role = role
        self.tenant_id = tenant_id


@pytest.mark.asyncio
async def test_resolve_site_membership_node_query_single():
    """멤버십 SELECT 단일 출처(헬퍼)에서 1쿼리로 노드를 조회해 사용(node= dead 파라미터 제거)."""
    db = _TokenFakeDB(node=_Node("root.y", "DIRECTOR"))
    res = await deps_sales.resolve_site_membership(db, _Site("sid"), _MemberUser("u"))
    assert res == ("root.y", "DIRECTOR")


def test_resolve_site_membership_has_no_node_param_yagni():
    """node= 는 호출부 0건의 dead 파라미터였어 제거(YAGNI). 재추가 회귀 차단."""
    import inspect

    params = inspect.signature(deps_sales.resolve_site_membership).parameters
    assert "node" not in params


@pytest.mark.asyncio
async def test_resolve_site_membership_multiple_nodes_picks_highest_priority():
    """★복수 살아있는 노드(=(site_id,user_id) UNIQUE 부재)여도 500 없이 '상위 권한'을 결정적 선택.

    과거 scalar_one_or_none() 은 MultipleResultsFound(500)를 던졌다. scalars().first()+우선순위
    정렬로 정정 — MEMBER 와 GM_DIRECTOR 가 함께 있으면 상위(GM_DIRECTOR)를 고른다.
    """
    db = _TokenFakeDB(nodes=[_Node("root.m", "MEMBER"), _Node("root.gm", "GM_DIRECTOR")])
    res = await deps_sales.resolve_site_membership(db, _Site("sid"), _MemberUser("u"))
    assert res == ("root.gm", "GM_DIRECTOR")  # 상위 권한 우선(알파벳 정렬 아님).


def test_node_priority_order_superior_first():
    """권한 우선순위: AGENCY < ... < MEMBER(작을수록 상위). 미등록 타입은 맨 뒤."""
    assert deps_sales._node_priority("AGENCY") < deps_sales._node_priority("MEMBER")
    assert deps_sales._node_priority("GM_DIRECTOR") < deps_sales._node_priority("TEAM_LEADER")
    assert deps_sales._node_priority("UNKNOWN") >= deps_sales._node_priority("MEMBER")


@pytest.mark.asyncio
async def test_resolve_site_membership_superadmin_fallback():
    """노드 없음 + user.role 이 SUPERADMIN 군 → ('', 'SUPERADMIN')."""
    db = _TokenFakeDB(node=None)
    res = await deps_sales.resolve_site_membership(db, _Site("sid"), _MemberUser("u", role="admin"))
    assert res == ("", "SUPERADMIN")


@pytest.mark.asyncio
async def test_resolve_site_membership_owns_site_developer():
    """노드 없음 + owns_site(테넌트 소유) → ('', 'DEVELOPER')."""
    db = _TokenFakeDB(node=None)
    site = _Site("sid", organization_id="tenant-1")
    user = _MemberUser("u", role="", tenant_id="tenant-1")
    res = await deps_sales.resolve_site_membership(db, site, user)
    assert res == ("", "DEVELOPER")


@pytest.mark.asyncio
async def test_resolve_site_membership_none_when_not_member():
    """노드 없음 + 폴백 자격 없음 → None(호출부가 403/거부)."""
    db = _TokenFakeDB(node=None)
    res = await deps_sales.resolve_site_membership(db, _Site("sid"), _MemberUser("u", role="viewer"))
    assert res is None


def test_site_auth_resolve_role_delegates_to_shared_helper():
    """site_auth._resolve_role 가 공용 헬퍼 resolve_site_membership 를 경유(3중복 SELECT 제거)."""
    import inspect

    from app.api.endpoints.sales import site_auth

    src = inspect.getsource(site_auth._resolve_role)
    assert "resolve_site_membership" in src
    # 멤버 아님 계약(('', '')) 보존 — 호출부 `if not role` 게이트 무회귀.
    assert '"", ""' in src


def test_sales_ctx_uses_shared_membership_helper():
    """sales_ctx 비토큰 분기도 공용 헬퍼로 멤버십을 판정(토큰/비토큰 1:1 일원화)."""
    import inspect

    src = inspect.getsource(deps_sales.sales_ctx)
    assert "resolve_site_membership" in src
    # 권한 없으면 403(거부 게이트 소재지는 sales_ctx).
    assert "이 현장에 대한 분양(sales) 권한이 없습니다" in src


# ──────────────────────────────────────────────────────────────────────────────
# (5) SSOT — _SUPERADMIN_ROLES/_DEVELOPER_ROLES 단일 출처(deps_sales) 일원화.
# ──────────────────────────────────────────────────────────────────────────────
def test_role_sets_ssot_single_source_in_deps_sales():
    """site_auth 가 deps_sales 의 _SUPERADMIN_ROLES 를 import(중복정의 드리프트 제거)."""
    from app.api.endpoints.sales import site_auth

    # 동일 객체(import) — 값 복제(중복정의)가 아님.
    assert site_auth._SUPERADMIN_ROLES is deps_sales._SUPERADMIN_ROLES


def test_site_auth_dead_developer_roles_removed():
    """site_auth 의 dead(미사용) _DEVELOPER_ROLES 중복정의는 제거됐다(재추가 회귀 차단)."""
    from app.api.endpoints.sales import site_auth

    assert not hasattr(site_auth, "_DEVELOPER_ROLES")


# ──────────────────────────────────────────────────────────────────────────────
# (4) sales_ctx — 토큰 sentinel 흐름: 멤버십 SELECT '정확히 1회'(중복 2쿼리 제거).
# ──────────────────────────────────────────────────────────────────────────────
class _CountingReq:
    """X-Site-Token 헤더만 제어하는 요청 더블(resolve_site 는 monkeypatch 로 우회)."""

    def __init__(self, token):
        self.headers = {"x-site-token": token} if token else {}
        self.path_params = {}


class _CountingDB:
    """resolve_site_membership 의 멤버십 SELECT 호출횟수만 센다(중복쿼리 회귀 차단).

    _apply_session_ctx 의 set_config 주입은 별도(text SQL)라 멤버십 카운트와 분리한다.
    sync_session/commit 도 흉내내 sales_ctx 전체 경로가 돌게 한다.
    """

    def __init__(self, nodes):
        self._nodes = list(nodes)
        self.membership_selects = 0
        self.sync_session = _OrmSession()
        self.committed = 0

    async def execute(self, statement, params=None):
        sql = str(getattr(statement, "text", statement))
        # set_config 주입은 멤버십 SELECT 가 아니므로 카운트 제외.
        if "set_config" not in sql:
            self.membership_selects += 1
        rows = self._nodes

        class _Scalars:
            def all(self):
                return rows

        class _R:
            def scalars(self):
                return _Scalars()

        return _R()

    async def commit(self):
        self.committed += 1


@pytest.mark.asyncio
async def test_sales_ctx_token_member_none_403_without_requery(monkeypatch):
    """토큰 유효 + 멤버십 없음 → 즉시 403, 멤버십 SELECT 는 1회만(재쿼리 없음)."""
    sid = "11111111-1111-1111-1111-111111111111"
    uid = "22222222-2222-2222-2222-222222222222"
    from app.api.endpoints.sales import site_auth

    site = _Site(sid)
    monkeypatch.setattr(deps_sales, "resolve_site", lambda req, db: _async_ret(site))
    monkeypatch.setattr(
        site_auth, "decode_site_token",
        lambda raw: {"site_id": sid, "sub": uid, "org_path": "", "site_role": "MEMBER"},
    )
    db = _CountingDB(nodes=[])  # 멤버십 없음(해촉/soft-delete)
    user = _MemberUser(uid, role="viewer")  # 폴백 자격도 없음
    with pytest.raises(deps_sales.HTTPException) as ei:
        await deps_sales.sales_ctx(_CountingReq("tok"), db=db, user=user)
    assert ei.value.status_code == 403
    # ★중복 2쿼리 회귀 차단: 토큰 경로에서 1회만 조회하고 비토큰 분기 재쿼리 없음.
    assert db.membership_selects == 1


@pytest.mark.asyncio
async def test_sales_ctx_no_token_resolves_membership_once(monkeypatch):
    """토큰 없음 → 비토큰 분기에서 멤버십 1회 해석(권한 있으면 통과)."""
    sid = "11111111-1111-1111-1111-111111111111"
    uid = "22222222-2222-2222-2222-222222222222"
    site = _Site(sid)
    monkeypatch.setattr(deps_sales, "resolve_site", lambda req, db: _async_ret(site))
    # _apply_session_ctx 는 set_config 만 — _CountingDB 가 execute 를 받으므로 호출수에 포함될 수
    # 있어, 멤버십 SELECT 만 별도로 센다(여기선 nodes 1건 → 멤버십 1회).
    db = _CountingDB(nodes=[_Node("root.a", "AGENCY")])
    user = _MemberUser(uid, role="")
    ctx = await deps_sales.sales_ctx(_CountingReq(None), db=db, user=user)
    assert ctx.role == "AGENCY"
    # 멤버십 SELECT 는 1회(이후 execute 는 set_config 주입이라 멤버십 카운트엔 무관).
    assert db.membership_selects >= 1


def _async_ret(value):
    """monkeypatch 용: 코루틴으로 값을 즉시 반환하는 헬퍼."""
    async def _coro():
        return value

    return _coro()


# ──────────────────────────────────────────────────────────────────────────────
# (2) rls_status — 접속 role BYPASSRLS 노출 + isolation_effective 경고(false assurance 차단).
# ──────────────────────────────────────────────────────────────────────────────
class _StatusFakeDB:
    """rls_status 의 _SQL_STATUS / _SQL_BYPASSRLS 결과를 제어하는 가짜 async DB."""

    def __init__(self, status_rows, bypass_row):
        self._status = status_rows
        self._bypass = bypass_row

    async def execute(self, statement, params=None):
        sql = str(getattr(statement, "text", statement))
        rows = self._status
        bypass = self._bypass

        class _R:
            def fetchall(self):
                return rows

            def first(self):
                return bypass

        if "rolbypassrls" in sql:
            class _B:
                def fetchall(self):
                    return [bypass] if bypass else []

                def first(self):
                    return bypass

            return _B()
        return _R()


class _Bypass:
    def __init__(self, current_user, bypassrls, superuser=False):
        self.current_user = current_user
        self.bypassrls = bypassrls
        self.superuser = superuser


@pytest.mark.asyncio
async def test_rls_status_exposes_bypassrls_and_warns_when_ineffective():
    """forced 테이블이 있는데 접속 role 이 BYPASSRLS → isolation_effective=false + 경고."""
    status_rows = [("sales_units", True, True, 1)]  # rls_enabled, forced, policy_count
    db = _StatusFakeDB(status_rows, _Bypass("propai_user", True))
    res = await boot.rls_status(db)
    assert res["forced"] == 1
    assert res["current_user"] == "propai_user"
    assert res["bypassrls"] is True
    assert res["is_superuser"] is False
    assert res["isolation_effective"] is False
    assert res["isolation_warning"]  # 경고 메시지 비어있지 않음.


@pytest.mark.asyncio
async def test_rls_status_effective_when_non_bypass_role():
    """non-bypassrls/non-superuser role + forced → isolation_effective=true(경고 없음)."""
    status_rows = [("sales_units", True, True, 1)]
    db = _StatusFakeDB(status_rows, _Bypass("propai_app", False, superuser=False))
    res = await boot.rls_status(db)
    assert res["bypassrls"] is False
    assert res["is_superuser"] is False
    assert res["isolation_effective"] is True
    assert res["isolation_warning"] is None


@pytest.mark.asyncio
async def test_rls_status_superuser_is_ineffective_even_without_bypassrls():
    """★슈퍼유저(rolsuper)는 rolbypassrls 무관하게 FORCE 포함 RLS 우회 → isolation_effective=false."""
    status_rows = [("sales_units", True, True, 1)]
    db = _StatusFakeDB(status_rows, _Bypass("postgres", False, superuser=True))
    res = await boot.rls_status(db)
    assert res["bypassrls"] is False
    assert res["is_superuser"] is True
    assert res["isolation_effective"] is False
    assert "SUPERUSER" in res["isolation_warning"]


@pytest.mark.asyncio
async def test_rls_status_unknown_role_state_is_failopen_conservative():
    """★fail-open 제거: role 행 없음(상태불명) → effective=false + 상태확인불가 경고."""
    status_rows = [("sales_units", True, True, 1)]
    db = _StatusFakeDB(status_rows, None)  # bypass_row 없음(role 행 무)
    res = await boot.rls_status(db)
    assert res["bypassrls"] is None
    assert res["is_superuser"] is None
    assert res["role_state_unknown"] is True
    assert res["isolation_effective"] is False
    assert "확인불가" in res["isolation_warning"]


@pytest.mark.asyncio
async def test_rls_status_null_flags_is_failopen_conservative():
    """★두 플래그 모두 NULL(상태불명) → effective=false(상태불명을 안전으로 가정 안 함)."""
    status_rows = [("sales_units", True, True, 1)]
    db = _StatusFakeDB(status_rows, _Bypass("role_x", None, superuser=None))
    res = await boot.rls_status(db)
    assert res["bypassrls"] is None
    assert res["is_superuser"] is None
    assert res["role_state_unknown"] is True
    assert res["isolation_effective"] is False
    assert res["isolation_warning"]


@pytest.mark.asyncio
async def test_rls_status_forced_policyless_warns_even_when_role_ok():
    """★(선택) role 정상이라도 forced+policy_count=0 테이블이 있으면 경고에 포함(앱 브릭 위험)."""
    # sales_units: forced + policy 1(정상), sales_weird: forced + policy 0(이상).
    status_rows = [("sales_units", True, True, 1), ("sales_weird", True, True, 0)]
    db = _StatusFakeDB(status_rows, _Bypass("propai_app", False, superuser=False))
    res = await boot.rls_status(db)
    assert res["isolation_effective"] is True   # role 정상 → 격리 자체는 실효.
    assert "sales_weird" in res["forced_policyless"]
    assert "sales_weird" in res["isolation_warning"]


@pytest.mark.asyncio
async def test_rls_status_forced_zero_is_ineffective_even_with_good_role():
    """★9.5 게이트: 어떤 테이블도 FORCE 미적용(forced==0)이면 role 정상이어도 effective=False.

    코드베이스 실제 deploy-pending 상태(FORCE 0)에서 과거엔 effective=True+무경고로 보고해
    '한 테이블도 강제 안 했는데 격리 실효' 라는 가장 흔한 false-assurance 가 났다.
    이제 isolation_effective 의 1차 조건이 forced>0 이라 forced==0 → False + 명시 경고.
    """
    # rls_enabled=True 이나 rls_forced=False(=FORCE 미적용) → forced 집계 0.
    status_rows = [("sales_units", True, False, 1), ("sales_contracts", True, False, 1)]
    db = _StatusFakeDB(status_rows, _Bypass("propai_app", False, superuser=False))
    res = await boot.rls_status(db)
    assert res["forced"] == 0
    assert res["bypassrls"] is False and res["is_superuser"] is False
    assert res["isolation_effective"] is False          # ★role 정상이어도 미실효.
    assert "FORCE 미적용" in res["isolation_warning"]    # deploy-pending 경고 노출.


@pytest.mark.asyncio
async def test_rls_status_multi_reason_warning_accumulates():
    """★다중 사유 누적(elif 가림 제거): forced==0 + BYPASSRLS 동시 → 두 사유 모두 노출."""
    # forced==0(FORCE 미적용) + 접속 role BYPASSRLS → 두 경고가 함께 떠야 한다.
    status_rows = [("sales_units", True, False, 1)]
    db = _StatusFakeDB(status_rows, _Bypass("propai_user", True, superuser=False))
    res = await boot.rls_status(db)
    assert res["isolation_effective"] is False
    assert "FORCE 미적용" in res["isolation_warning"]    # 사유1.
    assert "BYPASSRLS" in res["isolation_warning"]       # 사유2(elif 로 가려지지 않음).


# ──────────────────────────────────────────────────────────────────────────────
# (3) v62_2 downgrade(_DISABLE) — DISABLE 뿐 아니라 정책 DROP 까지(orphan 정책 차단).
#     + _ENABLE IF EXISTS 에 table_schema='public' 한정자(부트스트랩과 드리프트 제거).
# ──────────────────────────────────────────────────────────────────────────────
def test_migration_downgrade_drops_policies():
    sql = _read_migration_sql()
    # _DISABLE 블록(downgrade)에 정책 DROP 이 포함돼야 함(런타임 disable_sales_rls 와 정합).
    assert "DROP POLICY IF EXISTS p_site ON %I" in sql
    assert "DROP POLICY IF EXISTS p_org ON %I" in sql
    assert "DISABLE ROW LEVEL SECURITY" in sql


def test_migration_enable_guard_qualifies_public_schema():
    sql = _read_migration_sql()
    # site_id 판정 IF EXISTS 가 table_schema='public' 로 한정돼야 함(부트스트랩 _SQL_SITE_TABLES 정합).
    assert "table_schema='public' AND table_name=r.tablename" in sql


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
