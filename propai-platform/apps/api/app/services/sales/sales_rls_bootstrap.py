"""Phase 0 — 분양(sales)/모델하우스(mh) RLS(행수준 보안) 부트스트랩.

권위소스(정책 정의)는 마이그레이션이 정본(定本)이다:
- database/migrations/versions/v62_2_sales_rls.py : p_site / p_org USING 절 + FORCE
- app/api/deps_sales.py : set_config('app.site_id'|'app.org_path'|'app.role', ..., true)

본 모듈은 v62_2(정본)와 동일한 정책을 멱등(idempotent) 런타임 부트스트랩으로 재현한다.
샌드박스/신규 DB에서 마이그레이션 미적용 시의 보완 경로이며, advisory-lock 으로
프로세스 동시 호출의 race 만 제거한다. 마이그레이션이 항상 정본이다.

★FORCE ROW LEVEL SECURITY 를 적용한다(이번 변경의 핵심).
  - ENABLE 만으로는 테이블 소유자/BYPASSRLS role 이 정책을 우회하므로 격리 실효가 없다.
  - 따라서 모든 sales_/mh_ RLS 테이블에 'ALTER TABLE ... FORCE ROW LEVEL SECURITY' 를
    함께 적용해 소유자 쿼리도 정책을 거치게 한다.
  - ★운영 전제(실효 조건): 앱이 DB에 접속하는 role 은 반드시 'BYPASSRLS 아님'이어야 한다.
    (앱 전용 non-bypassrls role 분리는 인프라 작업 = deploy-pending.) BYPASSRLS role 로
    접속하면 FORCE 여부와 무관하게 정책이 무시되어 get_current_user/세션기반 격리가
    무력화된다. 즉 'FORCE 적용(코드)' + '앱 role=non-bypassrls(인프라)' 둘 다 충족돼야
    deps_sales 의 set_config 세션격리가 실제로 강제된다.

USING 절은 deps_sales 가 주입하는 세션변수와 정확히 일치하며, 모두 fail-closed(미설정 시
전부 거부)다. 3치논리(NULL) 가드를 nullif 로 적용한다:
- p_site: site_id = nullif(current_setting('app.site_id', true),'')::uuid
          OR current_setting('app.role', true) = 'SUPERADMIN'
          → app.site_id 미설정(NULL)/빈문자열이면 좌변=NULL, role 미설정이면 우변=NULL,
            'NULL OR NULL = NULL' 이므로 행 비노출(fail-closed). 빈문자열은 nullif 로
            NULL 화해 '::uuid 캐스트 에러' 도 방지한다.
- p_org : ★RESTRICTIVE(AND 결합) 정책이다. sales_org_nodes 는 p_site(PERMISSIVE)와
          p_org 가 함께 걸리는데, p_org 가 PERMISSIVE 면 둘이 OR 로 결합돼
          'role IN (AGENCY,DEVELOPER,SUPERADMIN)' 광역분기가 p_site 의 현장 스코프를
          무력화(타 현장 조직노드 노출)한다. 그래서 p_org 를 RESTRICTIVE 로 만들어
          'p_site AND p_org' 가 되게 하고, USING 절에도 현장 스코프
          'site_id = nullif(app.site_id,'')::uuid' 를 직접 강제한다:
            (site_id = nullif(current_setting('app.site_id', true),'')::uuid
             OR current_setting('app.role', true) = 'SUPERADMIN')
            AND (current_setting('app.role', true) IN ('AGENCY','DEVELOPER','SUPERADMIN')
                 OR path <@ nullif(current_setting('app.org_path', true),'')::ltree)
          → 1차로 현장 스코프(SUPERADMIN 제외)를 강제하고, 2차로 역할 광역/조직경로 가시성을
            제한한다. 모든 세션변수 미설정 시 'NULL'/false 로 행 비노출(fail-closed).

site_id 컬럼은 information_schema 로 동적 조회하므로 컬럼이 없는 테이블엔 p_site 를
적용하지 않는다(미보유 테이블에 site_id 정책 적용 시 에러 방지).

★ENABLE+FORCE 적용범위 = '정책이 실제 생기는 테이블'로 한정한다(단일 출처):
  - p_site 대상 = site_id 보유 sales_/mh_ 테이블(information_schema 동적).
  - p_org  대상 = sales_org_nodes.
  - 정책 0개 테이블(site_id 미보유·org 아님: 예 sales_commission_holdback,
    sales_contract_installments, mh_inventory_txns 등)에는 ENABLE/FORCE 를 적용하지
    않는다. FORCE+정책0 이면 non-bypassrls role 에서 '전 행 거부'(소유자 포함)되어
    앱 전체가 404 로 브릭되기 때문이다. 마이그레이션(v62_2_sales_rls.py)도 동일 기준으로
    정책 거는 테이블에만 ENABLE+FORCE 를 적용한다(범위 1:1 정합).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

# ── 정책 USING 절(v62_2 정본과 1:1 일치) ──
# nullif 가드: 세션변수 미설정/빈문자열을 NULL 로 만들어 ① '::uuid|::ltree 캐스트 에러' 방지
# ② 3치논리상 'NULL OR NULL = NULL' → 행 비노출(fail-closed) 보장.
_P_SITE_USING = (
    "(site_id = nullif(current_setting('app.site_id', true),'')::uuid "
    "OR current_setting('app.role', true) = 'SUPERADMIN')"
)
# ★p_org 는 RESTRICTIVE(AND 결합)다. PERMISSIVE 이면 p_site 와 OR 로 묶여 role-IN 광역분기가
# 현장 스코프를 무력화(타 현장 조직노드 노출)하므로, USING 절에 현장 스코프(site_id 일치)를
# 직접 AND 로 강제해 '현장 + 조직경로/역할' 둘 다 만족해야만 노출되게 한다.
_P_ORG_USING = (
    "((site_id = nullif(current_setting('app.site_id', true),'')::uuid "
    "OR current_setting('app.role', true) = 'SUPERADMIN') "
    "AND (current_setting('app.role', true) IN ('AGENCY','DEVELOPER','SUPERADMIN') "
    "OR path <@ nullif(current_setting('app.org_path', true),'')::ltree))"
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

# 접속 role 의 BYPASSRLS/SUPERUSER 여부(★false assurance 방지). 둘 중 하나라도 참이면 FORCE
# 여부와 무관하게 정책이 전부 우회되므로, forced=true 만으로 '격리 실효'를 보고하면 오인이다.
# ★슈퍼유저(rolsuper)는 rolbypassrls 플래그와 무관하게 항상 RLS(FORCE 포함)를 우회하므로,
#   rolbypassrls 만 검사하면 슈퍼유저 접속을 '격리 실효'로 오보(false assurance)한다.
_SQL_BYPASSRLS = """
SELECT current_user AS current_user,
       rolbypassrls AS bypassrls,
       rolsuper AS superuser
FROM pg_roles
WHERE rolname = current_user
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

# 부트스트랩 DDL 의 프로세스/요청 동시 호출 race 제거용 전역 advisory lock 키(임의 상수).
# pg_advisory_xact_lock 은 트랜잭션 종료(commit/rollback) 시 자동 해제되므로 누수 없음.
# ★마이그레이션이 정본이며, 본 lock 은 런타임 부트스트랩 중복 실행의 race 만 막는다.
_BOOTSTRAP_LOCK_KEY = 760_201_062  # 'sales rls bootstrap' 식별용 임의 키


def _quote_ident(name: str) -> str:
    """식별자 안전 인용(정적 information_schema 결과만 사용하나 방어적으로 처리)."""
    return '"' + name.replace('"', '""') + '"'


def _site_statements(table: str) -> list[str]:
    """site_id 보유 테이블의 멱등 p_site 부트스트랩 SQL(★ENABLE+FORCE).

    ENABLE 만으로는 소유자/BYPASSRLS role 이 우회하므로 FORCE 까지 적용한다.
    ENABLE·FORCE 반복 적용은 무해(멱등), 정책은 DROP IF EXISTS + CREATE 로 멱등.
    """
    q = _quote_ident(table)
    return [
        f"ALTER TABLE {q} ENABLE ROW LEVEL SECURITY;",
        f"ALTER TABLE {q} FORCE ROW LEVEL SECURITY;",
        f"DROP POLICY IF EXISTS p_site ON {q};",
        f"CREATE POLICY p_site ON {q} USING {_P_SITE_USING};",
    ]


def _org_statements() -> list[str]:
    """sales_org_nodes 의 멱등 p_org 부트스트랩 SQL(★ENABLE+FORCE, p_org=RESTRICTIVE).

    p_org 는 RESTRICTIVE 로 만들어 p_site(PERMISSIVE)와 AND 결합되게 한다(현장 스코프
    무력화 차단). sales_org_nodes 는 site_id 보유 테이블이므로 _site_statements 에서
    p_site 도 함께 적용된다(둘 다 RESTRICTIVE×PERMISSIVE 로 AND).
    """
    q = _quote_ident(_ORG_TABLE)
    return [
        f"ALTER TABLE {q} ENABLE ROW LEVEL SECURITY;",
        f"ALTER TABLE {q} FORCE ROW LEVEL SECURITY;",
        f"DROP POLICY IF EXISTS p_org ON {q};",
        f"CREATE POLICY p_org ON {q} AS RESTRICTIVE USING {_P_ORG_USING};",
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
    """sales_/mh_ 테이블에 RLS ENABLE+FORCE + p_site/p_org 정책을 멱등 적용한다.

    - site_id 보유 테이블 → p_site (information_schema 동적 조회).
    - sales_org_nodes    → p_org.
    - ★ENABLE+FORCE 적용(소유자/BYPASSRLS 우회 차단). 멱등(DROP IF EXISTS + CREATE,
      ENABLE·FORCE 반복 무해).
    - 실DDL 경로는 pg_advisory_xact_lock 으로 동시 호출 race 만 제거(트랜잭션 종료 시 자동 해제).
      마이그레이션이 정본이며 본 경로는 보완(샌드박스/신규 DB)이다.

    Args:
        only_table: 지정 시 그 1개 테이블만 적용(카나리). site_id 보유 또는
                    sales_org_nodes 여야 함. 미보유면 skipped 처리.
        dry_run:    True 면 SQL 만 생성·반환하고 실행하지 않는다(lock 미획득).

    Returns:
        {applied, skipped, policies, org_applied, force, dry_sql?}
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

    # 실행 경로만 advisory lock 획득(dry_run 은 SQL 생성만 하므로 lock 불필요).
    # pg_advisory_xact_lock 은 아래 commit/rollback 으로 트랜잭션이 끝날 때 자동 해제된다.
    if not dry_run:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:k)"), {"k": _BOOTSTRAP_LOCK_KEY}
        )

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
        "force": True,
        "dry_run": dry_run,
        "site_table_count": len(site_tables),
    }
    if dry_run:
        result["dry_sql"] = dry_sql
    return result


async def rls_status(db) -> dict[str, Any]:
    """sales_/mh_ 테이블별 rowsecurity·force·정책수 집계 + 접속 role BYPASSRLS/SUPERUSER 노출.

    ★false assurance 방지(2겹):
      (가) forced==0 인데 effective=true 보고 금지: ★한 테이블도 FORCE 가 안 걸렸으면(=실제
           deploy-pending 상태) role 이 정상이어도 세션격리는 미실효다. 가장 흔한 미배포
           false-assurance 라 isolation_effective 의 1차 조건으로 'forced>0' 을 강제하고,
           forced==0 이면 'RLS FORCE 미적용=세션격리 미실효(deploy-pending)' 경고를 노출한다.
      (나) BYPASSRLS/SUPERUSER 우회: forced 테이블이 있어도 접속 role 이 BYPASSRLS/SUPERUSER
           면 정책이 전부 우회된다. current_user/rolbypassrls/rolsuper 를 함께 노출하고
           isolation_effective=false 로 보고한다(코드상 검증 — 라이브 role 분리는 deploy-pending).

    ★fail-open 제거: role 행이 없거나 플래그가 NULL(상태불명)이면 '안전'으로 낙관(true)하지
    않고 isolation_effective=false + isolation_warning 으로 보수 보고한다(상태불명을 안전으로
    가정하는 fail-open 차단).

    ★(선택) forced 인데 policy_count=0 인 테이블이 있으면 경고에 포함한다. 부트스트랩/마이그
    레이션이 정책 0개 테이블엔 FORCE 를 걸지 않으므로 정상 경로에선 발생 가능성이 낮으나,
    수동 DDL 등으로 생기면 non-bypassrls role 에서 '전 행 거부'(앱 브릭)가 되므로 노출한다.
    """
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
    forced = sum(1 for t in tables if t["rls_forced"])

    # 접속 role 의 BYPASSRLS/SUPERUSER 여부 조회(연결 사용자가 정책을 우회하는지).
    br = (await db.execute(text(_SQL_BYPASSRLS))).first()
    current_user = br.current_user if br else None
    # NULL(상태불명)은 bool 강제하지 않고 None 으로 보존 → 아래 fail-open 보수 판정에 사용.
    bypassrls = bool(br.bypassrls) if br is not None and br.bypassrls is not None else None
    superuser = bool(br.superuser) if br is not None and br.superuser is not None else None

    # role 상태 확인불가 = 행 무(無) 또는 두 플래그가 모두 NULL(상태불명).
    role_state_unknown = (
        br is None or (bypassrls is None and superuser is None)
    )

    # 격리 실효 판정(보수적, 3조건 AND):
    #  ① forced > 0       : ★한 테이블도 FORCE 가 안 걸렸으면(=코드베이스 실제 deploy-pending
    #                       상태) 세션격리는 '미실효'다. 과거엔 forced==0 이어도 role 만 정상이면
    #                       effective=True 로 보고해 '한 테이블도 강제 안 했는데 격리 실효'라는
    #                       가장 흔한 미배포 false-assurance 가 났다. forced==0 → 무조건 false.
    #  ② not role_state_unknown : role 상태 불명(fail-open 제거)이면 안전 가정 금지 → false.
    #  ③ not bypasses     : 접속 role 이 BYPASSRLS/SUPERUSER 면 FORCE 가 걸려도 정책 전부 우회.
    #  - forced 테이블 중 policy_count=0(정책 없는 FORCE)은 별도 경고(앱 브릭 위험)로 누적.
    forced_policyless = [
        t["table"] for t in tables if t["rls_forced"] and t["policy_count"] == 0
    ]
    bypasses = (bypassrls is True) or (superuser is True)
    isolation_effective = (
        forced > 0
        and not role_state_unknown
        and not bypasses
    )

    # ★다중 사유 누적(elif 가림 제거): role bypass + policyless 동시처럼 여러 사유가 함께
    #   발생하면 하나만 노출하던 elif 체인이 나머지를 가렸다. 모든 해당 사유를 모아 보고한다.
    warnings_list: list[str] = []
    if forced == 0:
        warnings_list.append(
            "RLS FORCE 미적용=세션격리 미실효(deploy-pending) — sales_/mh_ 테이블 중 FORCE 가 "
            "걸린 테이블이 0개입니다. 마이그레이션(v62_2_sales_rls) 적용 또는 부트스트랩 "
            "(ensure_sales_rls)으로 ENABLE+FORCE 를 적용해야 세션기반 격리가 실효됩니다."
        )
    if role_state_unknown:
        warnings_list.append(
            "접속 role 상태 확인불가(role 행 없음 또는 rolbypassrls/rolsuper NULL) — "
            "상태불명을 안전으로 가정하지 않고 보수적으로 격리 미실효로 보고합니다. "
            "DB 권한 점검이 필요합니다(deploy-pending)."
        )
    elif bypasses:
        # role 상태가 명확할 때만 BYPASSRLS/SUPERUSER 판정이 의미 있음(불명이면 위에서 처리).
        kind = "SUPERUSER" if superuser is True else "BYPASSRLS"
        warnings_list.append(
            f"접속 role 이 {kind} 입니다 — FORCE 가 걸려도 정책이 전부 우회됩니다. "
            "앱 전용 non-bypassrls·non-superuser role 로 접속해야 세션기반 격리가 "
            "실효됩니다(deploy-pending)."
        )
    if forced_policyless:
        # 정책 없는 FORCE 테이블은 non-bypassrls role 에서 전 행 거부(앱 브릭) 위험 → 항상 경고.
        warnings_list.append(
            "FORCE 가 걸렸으나 정책이 0개인 테이블이 있습니다(non-bypassrls role 에서 전 행 "
            f"거부=앱 브릭 위험): {', '.join(forced_policyless)}. 정책을 추가하거나 FORCE 를 해제하세요."
        )
    # 단일 문자열로 합치되(기존 계약 보존), 다중 사유를 모두 담는다. 사유 0건이면 None.
    isolation_warning: str | None = " / ".join(warnings_list) if warnings_list else None

    return {
        "total": len(tables),
        "rls_enabled": enabled,
        "with_policy": with_policy,
        "forced": forced,
        "tables": tables,
        # ★접속 role 컨텍스트(false assurance 차단).
        "current_user": current_user,
        "bypassrls": bypassrls,
        "is_superuser": superuser,
        "role_state_unknown": role_state_unknown,
        "forced_policyless": forced_policyless,
        "isolation_effective": isolation_effective,
        "isolation_warning": isolation_warning,
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
