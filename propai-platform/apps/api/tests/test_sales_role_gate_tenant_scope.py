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


def test_the_ssot_does_not_carry_the_registration_default() -> None:
    """★**생산자 축** — 가입이 넣는 값이 이 집합에 다시 들어오면 실패한다.

    ★목록을 손으로 적지 않는다: `UserRole.ADMIN.value` 를 **가입 코드와 같은 원천**에서
      가져와 대조한다(내가 기억하는 문자열이 아니라).
    """
    import ast
    import pathlib

    # `routers/auth.py` 가 실제로 무엇을 넣는지 AST 로 뽑는다(주석·문자열에 안 뚫린다).
    src = pathlib.Path(__file__).resolve().parents[1] / "routers" / "auth.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    assigned = {
        ast.unparse(kw.value)
        for call in ast.walk(tree) if isinstance(call, ast.Call)
        for kw in call.keywords if kw.arg == "role"
    }
    assert assigned, "가입 코드에서 `role=` 대입을 못 찾았다 — 축이 죽었다"
    assert "UserRole.ADMIN.value" in assigned, f"가입이 넣는 값이 바뀌었다: {assigned}"

    from packages.schemas.enums import UserRole

    assert UserRole.ADMIN.value.lower() not in deps_sales._SUPERADMIN_ROLES, (
        "가입이 넣는 값이 플랫폼 게이트에 **다시 들어왔다** — 누출이 복원된다"
    )
