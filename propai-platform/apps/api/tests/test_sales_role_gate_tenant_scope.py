"""★가입 기본값(`role='admin'`)이 **플랫폼 전역 권한**이 되지 않는다(2026-09-12).

【결함】`POST /register`(`routers/auth.py:347`)는 **새 Tenant 를 만들고** 그 사용자에게
`role="admin"` 을 준다 — *"Create a **tenant** admin account"*. 즉 **테넌트 스코프 라벨**이다.
그런데 `deps_sales._SUPERADMIN_ROLES` 가 그 라벨을 담아, `resolve_site_membership` 이
**테넌트 검사 없이** `("", "SUPERADMIN")` 을 내줬다 → 가입한 누구나 **플랫폼 전체 현장**의
SUPERADMIN. `require_role` 은 `ctx.role != "SUPERADMIN"` 으로 모든 역할 게이트를 통과시킨다.

【라이브 실측 · 읽기 전용 2026-09-12】`/sales/sites`(테넌트 스코프) **13** vs
`/sales/my-sites` **14** — 추가 1건의 `membership` 이 **`admin`**(= 이 게이트로 들어온
자기 테넌트 **밖** 현장).

【DB 층은 막지 않는다】RLS 정책에 `OR current_setting('app.role')='SUPERADMIN'` 이 있고
`deps_sales` 가 **판정된 role 을 그대로 주입**한다. `sales_sites` 는 정책 대상도 아니다.
볼트 `dev-tasks/2026-09-08_분양앱_회원체계_통합설계_결정4건.md` **D-3** 이
*"지금 통합이 도는 이유가 RLS 미실효"* 라고 같은 것을 적어 뒀다.

【축】«문자열 목록이 어떻게 생겼나» 가 아니라 **«그 역할로 무엇을 받는가»** 를 태운다.
그리고 **두 모집단**을 같은 파일에서 본다 — 플랫폼 라벨은 통과하고 가입 기본값은 막힌다.
한쪽만 보면 «전부 막는» 구현도 통과한다.
"""
from __future__ import annotations

import uuid

import pytest

from app.api import deps_sales


class _Site:
    def __init__(self, sid: str, organization_id=None):
        self.id = sid
        self.organization_id = organization_id


class _User:
    def __init__(self, uid: str, role: str = "", tenant_id=None):
        self.id = uid
        self.role = role
        self.tenant_id = tenant_id


class _NoNodeDB:
    """조직 노드가 **0건**인 DB — 폴백 경로만 태운다."""

    async def execute(self, *_a, **_k):
        class _R:
            def scalars(self):
                class _S:
                    def all(self):
                        return []
                return _S()
        return _R()


# ─────────────────────────────────────────────────────────────────────────────
# A. 두 모집단 — 플랫폼 라벨은 통과, 가입 기본값은 막힌다
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("role", sorted(deps_sales._SUPERADMIN_ROLES))
async def test_platform_labels_still_grant_superadmin(role: str) -> None:
    """★대조군 — 진짜 플랫폼 라벨은 **그대로** SUPERADMIN 이다(전부 막는 구현이 아님)."""
    res = await deps_sales.resolve_site_membership(_NoNodeDB(), _Site("sid"), _User("u", role=role))
    assert res == ("", "SUPERADMIN"), f"{role!r} 이 플랫폼 권한을 잃었다 — 과잉 차단"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "owner", "ADMIN", "Owner"])
async def test_registration_default_role_is_not_platform_superadmin(role: str) -> None:
    """★★**가입하면 누구나 받는 라벨**이 플랫폼 전역 권한이 되면 안 된다.

    ★대소문자도 태운다 — 판정이 `role.lower()` 라, 목록에서만 빼고 정규화를 바꾸면
      다시 샌다(`"ADMIN".lower() == "admin"`).
    """
    res = await deps_sales.resolve_site_membership(
        _NoNodeDB(), _Site("sid"), _User("u", role=role))
    assert res != ("", "SUPERADMIN"), (
        f"가입 기본값 {role!r} 이 **테넌트 검사 없이** 플랫폼 SUPERADMIN 을 받는다 — "
        "가입한 누구나 모든 테넌트의 현장을 연다"
    )
    assert res is None, f"멤버도 소유자도 아닌데 멤버십이 나왔다: {res!r}"


@pytest.mark.asyncio
async def test_owning_your_tenants_site_still_grants_developer() -> None:
    """★**자기 테넌트 현장은 그대로 열린다** — 이 변경이 정당 사용자를 막지 않는다.

    라이브 실측에서 이 계정이 보던 14건 중 **13건이 이 경로**(`membership: owner`)다.
    """
    site = _Site("sid", organization_id="tenant-1")
    res = await deps_sales.resolve_site_membership(
        _NoNodeDB(), site, _User("u", role="admin", tenant_id="tenant-1"))
    assert res == ("", "DEVELOPER"), f"자기 테넌트 소유 현장이 막혔다: {res!r}"


@pytest.mark.asyncio
async def test_other_tenants_site_is_not_granted_to_a_registered_user() -> None:
    """★★**반대편 모집단** — 남의 테넌트 현장은 가입 기본값으로 열리지 않는다."""
    site = _Site("sid", organization_id="tenant-OTHER")
    res = await deps_sales.resolve_site_membership(
        _NoNodeDB(), site, _User("u", role="admin", tenant_id="tenant-1"))
    assert res is None, (
        f"가입한 사용자가 **남의 테넌트** 현장의 멤버십을 받았다: {res!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# B. 형제 — 손복사가 아니라 파생인가
# ─────────────────────────────────────────────────────────────────────────────

def test_tenant_finance_roles_is_derived_from_the_ssot() -> None:
    """★`views._TENANT_FINANCE_ROLES` 가 **SSOT 에서 파생**되는가.

    그 파일 주석이 *"sales_ctx 의 분류와 **동일 의미**"* 라고 단정한다. 손복사면 그 단정이
    조용히 거짓이 된다 — 실제로 이번 변경에서 손복사를 남겼으면 **그 게이트만 전원 통과**했다.
    """
    from app.api.endpoints.sales import views

    assert views._TENANT_FINANCE_ROLES == (
        deps_sales._SUPERADMIN_ROLES | deps_sales._DEVELOPER_ROLES
    ), "손복사가 SSOT 와 갈렸다"
    # ★공허 방지 — 두 집합이 **비면** 위 단언이 공짜다.
    assert deps_sales._SUPERADMIN_ROLES and deps_sales._DEVELOPER_ROLES
    # ★그리고 가입 기본값이 이 게이트에도 없어야 한다(파생이 실제로 전파됐는가).
    assert "admin" not in views._TENANT_FINANCE_ROLES
    assert "owner" not in views._TENANT_FINANCE_ROLES


def test_the_platform_role_set_is_pinned_to_a_literal() -> None:
    """★★**파생 모집단은 잠그려는 상수에서 나온다** — 그래서 상수가 줄면 조용히 같이 준다.

    실측(2026-09-12 · 독립 리뷰 ㉣ + 내 재현): `_SUPERADMIN_ROLES` 에서 `platform_admin` 하나를
    빼는 변이가 **`11 passed` 로 초록**이었다(종전 12). 위 `@parametrize(sorted(...))` 의
    모집단이 **함께 깎여** 단언이 사라진 것이지, 통과한 것이 아니다.

    ⇒ **리터럴 핀**을 따로 둔다. 파생의 이점(새 라벨이 자동으로 행위 테스트에 들어옴)은 유지하고,
      **줄어들거나 바꿔치기되는 것**은 여기서 잡는다.
    ★핀은 «무엇이 있어야 하나» 와 «무엇이 없어야 하나» 를 **둘 다** 적는다 —
      포함만 적으면 추가는 안 잡히고, 배제만 적으면 삭제가 안 잡힌다.
    """
    assert {
        "superadmin", "super_admin", "총괄관리자", "platform_admin",
    } == deps_sales._SUPERADMIN_ROLES, (
        "플랫폼 역할 집합이 바뀌었다. **의도된 변경이면 이 핀을 같이 고쳐라** — "
        "핀 없이 바꾸면 위 파생 테스트들이 **조용히 줄면서 초록**이 된다: "
        f"{sorted(deps_sales._SUPERADMIN_ROLES)}"
    )
    assert {"developer", "시행사", "dev"} == deps_sales._DEVELOPER_ROLES


def test_the_ssot_does_not_carry_the_registration_default() -> None:
    """★**생산자 축** — 가입이 넣는 값이 이 집합에 다시 들어오면 실패한다.

    ★목록을 손으로 적지 않는다: `UserRole.ADMIN.value` 를 **가입 코드와 같은 원천**에서
      가져와 대조한다(내가 기억하는 문자열이 아니라).
    """
    import ast
    import pathlib

    # ★★**파일 목록이 아니라 전수 파생**(2026-09-12 · 독립 리뷰 MAJOR-3).
    #   종전엔 `routers/auth.py` **한 파일**만 읽었다. 그래서 **소셜 가입**
    #   (`auth/oauth_common.py:33 _DEFAULT_SOCIAL_ROLE = "admin"` → `:208 role=…`)이
    #   **축 밖**이었고, 그 값을 `"superadmin"` 으로 바꾸는 변이가 **SURVIVED** 했다
    #   — 즉 「소셜 가입자 전원이 플랫폼 SUPERADMIN」이 되어도 이 파일의 락이 전부 초록이었다.
    #   ★내가 그 파일을 못 본 이유도 **조회 범위**였다(`app/`·`routers/` 만 봤고
    #     `auth/` 는 밖이었다) — 「0건」은 결론이 아니라 조회 결과다.
    root = pathlib.Path(__file__).resolve().parents[1]

    def _literal_roles(tree: ast.AST) -> set[str]:
        """모듈 하나에서 **`role=` 로 넘어가는 문자열 리터럴**을 뽑는다(상수 한 단계 해석)."""
        consts = {
            t.id: n.value.value
            for n in ast.walk(tree) if isinstance(n, ast.Assign)
            and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
            for t in n.targets if isinstance(t, ast.Name)
        }
        found: set[str] = set()
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call):
                continue
            for kw in call.keywords:
                if kw.arg != "role":
                    continue
                v = kw.value
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    found.add(v.value)            # role="admin"
                elif isinstance(v, ast.Name) and v.id in consts:
                    found.add(consts[v.id])       # role=_DEFAULT_SOCIAL_ROLE
                elif isinstance(v, ast.Attribute) and ast.unparse(v).endswith(".ADMIN.value"):
                    from packages.schemas.enums import UserRole
                    found.add(UserRole.ADMIN.value)
        return found

    producers: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*.py")):
        rel = str(path.relative_to(root))
        if "/tests/" in rel or rel.startswith("tests/"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        roles = _literal_roles(tree)
        if roles:
            producers[rel] = roles

    # ★공허 방지 + 조회기 생존 — 알려진 두 생산자가 **둘 다** 잡혀야 한다.
    assert "routers/auth.py" in producers, f"이메일 가입 생산자를 못 찾았다: {sorted(producers)}"
    assert "auth/oauth_common.py" in producers, (
        f"**소셜 가입** 생산자를 못 찾았다 — 축이 다시 좁아졌다: {sorted(producers)}"
    )

    # ★본판정 — 어떤 생산자도 **플랫폼 라벨**을 일반 사용자에게 박지 않는다.
    leaking = {
        rel: sorted(roles & deps_sales._SUPERADMIN_ROLES)
        for rel, roles in producers.items()
        if roles & deps_sales._SUPERADMIN_ROLES
    }
    assert not leaking, (
        "가입/생성 경로가 **플랫폼 전역 라벨**을 박는다 — 그 사용자는 전 테넌트의 현장을 연다: "
        f"{leaking}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# C. R1 — **누출을 실측한 바로 그 자리**를 태운다 (2026-09-12 · 독립 리뷰 MAJOR-1)
#
# ★내 계획서 §5 는 이 자리에 락이 있다고 **선언**했는데 그 이름이 실재하지 않았다.
#   실재하던 것은 `resolve_site_membership` 을 태우는 락이고 — **그건 「접근 판정」이지
#   「목록 노출」이 아니다.** 라이브에서 13 vs **14** 로 잰 그 14번째를 만든 자리는
#   `site_auth.my_sites` 의 `is_super` 분기(`site_auth.py:225`)다.
#   ⇒ 실측(독립 리뷰 + 내 재현): `is_super = True` 변이가 **SURVIVED**.
#   ***처방의 범위가 결함의 범위와 갈렸다 — 내가 잰 곳을 내가 안 잠갔다.***
# ─────────────────────────────────────────────────────────────────────────────


class _MySitesDB:
    """`my_sites` 의 세 갈래를 **쿼리 내용으로** 라우팅한다(호출 순서가 아니라).

    ★호출 횟수로 라우팅하면 생산 코드가 쿼리를 하나 더하는 순간 조용히 틀린다
      (이 저장소에서 실제로 CI 를 빨갛게 만든 형태).
    ★(b)소유와 (c)관리자 전체는 **둘 다 `select(SalesSite)`** 라 SELECT 절이 글자 단위로 같다 —
      `ORDER BY`(관리자 전체만 정렬한다)로 가른다. 안 그러면 두 갈래가 한 갈래로 뭉쳐
      「세 갈래」 단언이 공허해진다.
    """

    def __init__(self, *, nodes, owned, allsites):
        self._nodes, self._owned, self._all = nodes, owned, allsites

    async def execute(self, stmt, params=None):
        q = " ".join(str(stmt).split())

        class _R:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

            def scalars(self):
                return self

        if "sales_org_nodes" in q and "sales_sites" in q:
            return _R(self._nodes)
        if "ORDER BY" in q:
            return _R(self._all)          # (c) 관리자 전체 — 유일하게 정렬한다
        if "organization_id =" in q:
            return _R(self._owned)        # (b) 소유 테넌트
        return _R([])

    async def commit(self):
        pass


def _site_row(name: str, org):
    return type("S", (), {
        "id": uuid.uuid4(), "site_code": name, "site_name": name,
        "development_type": "APT", "status": "ACTIVE", "organization_id": org,
    })()


@pytest.mark.asyncio
async def test_my_sites_does_not_show_other_tenants_sites_to_a_registered_user() -> None:
    """★★**가입 기본값으로는 남의 테넌트 현장이 목록에 안 뜬다** — 라이브 13 vs 14 의 그 자리.

    ★두 모집단을 **같은 실행에서** 본다. 한쪽만 보면 «전부 막는» 구현도 통과한다.
    """
    from app.api.endpoints.sales import site_auth as mod

    tenant = uuid.uuid4()
    mine, theirs = _site_row("mine", tenant), _site_row("theirs", uuid.uuid4())

    def _db():
        return _MySitesDB(nodes=[], owned=[mine], allsites=[mine, theirs])

    # ① 가입 기본값 — **자기 것 1건만**.
    rows = await mod.my_sites(db=_db(), user=_User("u", role="admin", tenant_id=tenant))
    codes = sorted(r["site_code"] for r in rows)
    assert codes == ["mine"], f"가입 기본값이 남의 테넌트 현장을 본다: {codes}"
    assert not [r for r in rows if r.get("membership") == "admin"], (
        "`membership='admin'`(플랫폼 role 게이트 분기) 행이 나왔다 — 라이브 14번째가 그 행이었다"
    )

    # ② **대조군** — 진짜 플랫폼 라벨은 **2건**을 본다(과잉 차단이 아니다).
    rows2 = await mod.my_sites(db=_db(), user=_User("s", role="superadmin", tenant_id=tenant))
    assert sorted(r["site_code"] for r in rows2) == ["mine", "theirs"], (
        f"플랫폼 총괄이 전체를 못 본다 — 과잉 차단: {[r['site_code'] for r in rows2]}"
    )
    assert [r for r in rows2 if r.get("membership") == "admin"], "관리자 분기가 아예 안 돈다"
