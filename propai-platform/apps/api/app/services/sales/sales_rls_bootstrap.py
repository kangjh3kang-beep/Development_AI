"""Phase 0 — 분양(sales)/모델하우스(mh) RLS(행수준 보안) 부트스트랩.

권위소스(정책 정의):
- database/migrations/versions/v62_2_sales_rls.py : p_site / p_org USING 절
- app/api/deps_sales.py : set_config('app.site_id'|'app.org_path'|'app.role', ..., true)

본 모듈은 v62_2 의 정책을 멱등(idempotent) 부트스트랩으로 재현하되,
★FORCE ROW LEVEL SECURITY 는 적용하지 않는다(앱 DB role=postgres 는 bypassrls=True 라
ENABLE 만으로 무중단 — 앱 쿼리는 우회하고 PostgREST anon/authenticated 표면만 보호).

USING 절은 deps_sales 가 주입하는 세션변수와 정확히 일치해야 한다:
- p_site: site_id = nullif(current_setting('app.site_id', true),'')::uuid
          OR current_setting('app.role', true) = 'SUPERADMIN'
- p_org : current_setting('app.role', true) IN ('AGENCY','DEVELOPER','SUPERADMIN')
          OR path <@ current_setting('app.org_path', true)::ltree

site_id 컬럼은 information_schema 로 동적 조회하므로 컬럼이 없는 테이블엔 p_site 를
적용하지 않는다(미보유 테이블에 site_id 정책 적용 시 에러 방지).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

# ── 정책 USING 절(v62_2 일치, nullif 가드 추가 — 빈문자열→NULL 캐스트 에러 방지) ──
_P_SITE_USING = (
    "(site_id = nullif(current_setting('app.site_id', true),'')::uuid "
    "OR current_setting('app.role', true) = 'SUPERADMIN')"
)
_P_ORG_USING = (
    "(current_setting('app.role', true) IN ('AGENCY','DEVELOPER','SUPERADMIN') "
    "OR path <@ current_setting('app.org_path', true)::ltree)"
)

# sales_/mh_ 테이블 + site_id 컬럼 보유 동적 조회(public 스키마).
_SQL_SITE_TABLES = """
SELECT c.table_name
FROM information_schema.columns c
JOIN information_schema.tables t
  ON t.table_schema = c.table_schema AND t.table_name = c.table_name
WHERE c.table_schema = 'public'
  AND c.column_name = 'site_id'
  AND t.table_type = 'BASE TABLE'
  AND (c.table_name LIKE 'sales\\_%' OR c.table_name LIKE 'mh\\_%')
ORDER BY c.table_name
"""

# sales_/mh_ 전체 BASE TABLE(상태/롤백 대상).
_SQL_ALL_TABLES = """
SELECT t.table_name
FROM information_schema.tables t
WHERE t.table_schema = 'public'
  AND t.table_type = 'BASE TABLE'
  AND (t.table_name LIKE 'sales\\_%' OR t.table_name LIKE 'mh\\_%')
ORDER BY t.table_name
"""

# 상태 집계: rowsecurity 플래그 + 정책수.
_SQL_STATUS = """
SELECT c.relname AS table_name,
       c.relrowsecurity AS rls_enabled,
       c.relforcerowsecurity AS rls_forced,
       (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS policy_count
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind = 'r'
  AND (c.relname LIKE 'sales\\_%' OR c.relname LIKE 'mh\\_%')
ORDER BY c.relname
"""

_ORG_TABLE = "sales_org_nodes"


def _quote_ident(name: str) -> str:
    """식별자 안전 인용(정적 information_schema 결과만 사용하나 방어적으로 처리)."""
    return '"' + name.replace('"', '""') + '"'


def _site_statements(table: str) -> list[str]:
    """site_id 보유 테이블의 멱등 p_site 부트스트랩 SQL(★FORCE 없음)."""
    q = _quote_ident(table)
    return [
        f"ALTER TABLE {q} ENABLE ROW LEVEL SECURITY;",
        f"DROP POLICY IF EXISTS p_site ON {q};",
        f"CREATE POLICY p_site ON {q} USING {_P_SITE_USING};",
    ]


def _org_statements() -> list[str]:
    """sales_org_nodes 의 멱등 p_org 부트스트랩 SQL(★FORCE 없음)."""
    q = _quote_ident(_ORG_TABLE)
    return [
        f"ALTER TABLE {q} ENABLE ROW LEVEL SECURITY;",
        f"DROP POLICY IF EXISTS p_org ON {q};",
        f"CREATE POLICY p_org ON {q} USING {_P_ORG_USING};",
    ]


async def _fetch_site_tables(db) -> list[str]:
    rows = (await db.execute(text(_SQL_SITE_TABLES))).fetchall()
    return [r[0] for r in rows]


async def ensure_sales_rls(
    db,
    *,
    only_table: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """sales_/mh_ 테이블에 RLS ENABLE + p_site/p_org 정책을 멱등 적용한다.

    - site_id 보유 테이블 → p_site (information_schema 동적 조회).
    - sales_org_nodes    → p_org.
    - ★FORCE 미적용(ENABLE 만). 멱등(DROP IF EXISTS + CREATE, ENABLE 반복 무해).

    Args:
        only_table: 지정 시 그 1개 테이블만 적용(카나리). site_id 보유 또는
                    sales_org_nodes 여야 함. 미보유면 skipped 처리.
        dry_run:    True 면 SQL 만 생성·반환하고 실행하지 않는다.

    Returns:
        {applied, skipped, policies, org_applied, dry_sql?}
    """
    site_tables = await _fetch_site_tables(db)

    applied: list[str] = []
    skipped: list[str] = []
    dry_sql: list[str] = []
    org_applied = False

    # 적용 대상 결정(only_table = 카나리).
    if only_table is not None:
        target = only_table.strip()
        do_org = target == _ORG_TABLE
        do_sites = [target] if target in site_tables else []
        if not do_sites and not do_org:
            # site_id 미보유 & org 아님 → 정책 대상 아님(에러 대신 skip).
            skipped.append(target)
    else:
        do_sites = site_tables
        do_org = True

    for t in do_sites:
        stmts = _site_statements(t)
        if dry_run:
            dry_sql.extend(stmts)
        else:
            for s in stmts:
                await db.execute(text(s))
        applied.append(t)

    if do_org:
        stmts = _org_statements()
        if dry_run:
            dry_sql.extend(stmts)
        else:
            for s in stmts:
                await db.execute(text(s))
        org_applied = True

    if not dry_run:
        await db.commit()

    result: dict[str, Any] = {
        "applied": applied,
        "skipped": skipped,
        "org_applied": org_applied,
        "policies": {"p_site": _P_SITE_USING, "p_org": _P_ORG_USING},
        "force": False,
        "dry_run": dry_run,
        "site_table_count": len(site_tables),
    }
    if dry_run:
        result["dry_sql"] = dry_sql
    return result


async def rls_status(db) -> dict[str, Any]:
    """sales_/mh_ 테이블별 rowsecurity·force·정책수 집계."""
    rows = (await db.execute(text(_SQL_STATUS))).fetchall()
    tables = [
        {
            "table": r[0],
            "rls_enabled": bool(r[1]),
            "rls_forced": bool(r[2]),
            "policy_count": int(r[3]),
        }
        for r in rows
    ]
    enabled = sum(1 for t in tables if t["rls_enabled"])
    with_policy = sum(1 for t in tables if t["policy_count"] > 0)
    return {
        "total": len(tables),
        "rls_enabled": enabled,
        "with_policy": with_policy,
        "forced": sum(1 for t in tables if t["rls_forced"]),
        "tables": tables,
    }


async def disable_sales_rls(db) -> dict[str, Any]:
    """롤백(1콜): 전 sales_/mh_ 테이블 RLS DISABLE + p_site/p_org DROP IF EXISTS."""
    rows = (await db.execute(text(_SQL_ALL_TABLES))).fetchall()
    all_tables = [r[0] for r in rows]
    disabled: list[str] = []
    for t in all_tables:
        q = _quote_ident(t)
        await db.execute(text(f"DROP POLICY IF EXISTS p_site ON {q};"))
        await db.execute(text(f"DROP POLICY IF EXISTS p_org ON {q};"))
        await db.execute(text(f"ALTER TABLE {q} DISABLE ROW LEVEL SECURITY;"))
        disabled.append(t)
    await db.commit()
    return {"disabled": disabled, "count": len(disabled)}
