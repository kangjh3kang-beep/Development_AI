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

import ast
import pathlib
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


#: 스캔에서 **제외**할 경로 조각 — 제3자 코드와 산출물은 «우리 생산자» 가 아니다.
#
#  ★왜(2026-09-12 실측 · #1034 후속): 종전 스캐너가 `apps/api` 전체를 `rglob` 하면서
#    `.venv` 를 제외하지 않았다. **`apps/api` 안에 자체 venv 가 있다**:
#        `apps/api` 전체 `.py` **12,146** 중 `.venv`/site-packages **10,176(83%)** · 실제 소스 1,970
#    CI 는 `.venv` 가 `propai-platform/.gitignore:15` 에 있어 안전했지만(`git ls-files` 0건),
#    **로컬에서는 83%를 헛 훑었다** — 느리고, 제3자 라이브러리가 `role="admin"` 을 쓰면 **위양성**이다.
#    ***환경에 따라 판정이 갈리면 그것도 결함이다 — 가드의 위양성도 결함이다.***
_SCAN_EXCLUDED = ("/.venv/", "/site-packages/", "/node_modules/", "/tests/")


def _scan_role_producers(root: pathlib.Path) -> dict[str, set[str]]:
    """`role=` 로 넘어가는 **문자열 리터럴**을 파일별로 모은다(상수 한 단계 해석).

    ★`root` 를 **인자로** 받는다 — 합성 입력으로 이 함수 자신을 태울 수 있어야
      «제외가 살아 있는가» 를 **환경과 무관하게** 잠글 수 있다(`.venv` 가 없는 CI 에서도).
    """
    producers: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*.py")):
        rel = str(path.relative_to(root))
        if any(x in f"/{rel}" for x in _SCAN_EXCLUDED):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
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
        if found:
            producers[rel] = found
    return producers


def test_the_exclusion_is_alive_in_every_environment() -> None:
    """★★**제외가 죽으면 실패한다** — 합성 입력으로 태운다(환경 의존 없이).

    ★동료 지적(2026-09-12): *"`.venv` 가 없는 환경에서 제외 로직이 통째로 빠져도 초록이면,
      그 제외는 다음 사람에게 **장식**이다."* 맞다 — CI 에는 `.venv` 가 없으므로
      «실제로 뭔가 제외했나» 를 단언하면 **CI 에서 공허**해진다.
    ⇒ **합성 트리**를 만들어 태운다. 어느 환경에서도 같은 판정이 나온다.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / "src").mkdir()
        (root / "src" / "signup.py").write_text(
            'def make():\n    return User(role="admin")\n', encoding="utf-8")
        # ★★**제외 항목마다 「그것만 걸리는」 파일**을 둔다 — 겹치면 하나를 지워도 다른 하나가
        #   덮어 **그 제외는 개별적으로 무잠금**이 된다(실측: 처음엔 악성 파일을 모두
        #   `.venv/lib/site-packages/` 에 뒀더니 `/.venv/` 만 빼는 변이가 **SURVIVED** 했다).
        #   ***차가 0인 픽스처는 잠금이 아니다.***
        only_venv = root / ".venv" / "bin"            # `/.venv/` 에만 걸린다
        only_site = root / "vendor" / "site-packages"  # `/site-packages/` 에만 걸린다
        only_node = root / "node_modules" / "x"        # `/node_modules/` 에만 걸린다
        only_test = root / "tests"                     # `/tests/` 에만 걸린다
        for d in (only_venv, only_site, only_node, only_test):
            d.mkdir(parents=True)
            (d / "evil.py").write_text(
                'def x():\n    return User(role="superadmin")\n', encoding="utf-8")

        found = _scan_role_producers(root)

        # ★★**대조군을 본판정보다 먼저** 찍는다(리뷰 MINOR-1).
        #   순서가 바뀌면 스캐너가 죽었을 때 «제외가 죽었다» 라는 **틀린 사유**가 먼저 나오고,
        #   다음 사람이 **틀린 곳을 판다.** ***사유가 틀리면 진단이 없는 것보다 나쁘다.***
        assert found.get("src/signup.py") == {"admin"}, (
            f"스캐너가 **진짜 생산자를 못 읽는다**(제외 문제가 아니다): {sorted(found)}"
        )

        # ★본판정 — 제외 대상이 **하나도** 안 들어온다.
        assert set(found) == {"src/signup.py"}, (
            f"제외가 죽었다 — 제3자/산출물/테스트가 생산자로 세어진다: {sorted(found)}"
        )
        # ★★제외 **항목별**로 각각 살아 있는지(하나를 지우면 그 항목이 새어 나온다).
        for frag, path in (
            ("/.venv/", ".venv/bin/evil.py"),
            ("/site-packages/", "vendor/site-packages/evil.py"),
            ("/node_modules/", "node_modules/x/evil.py"),
            ("/tests/", "tests/evil.py"),
        ):
            assert frag in _SCAN_EXCLUDED, f"제외 항목 {frag} 이 사라졌다"
            assert path not in found, f"{frag} 제외가 죽었다 — {path} 가 모집단에 있다"



def test_the_real_scan_stays_within_our_sources() -> None:
    """★실제 저장소에서 **모집단이 제3자 코드로 부풀지 않는다**.

    ★★**판정자가 피판정자와 상수를 공유하면 아무것도 안 잠근다**(2026-09-12 실측 · 리뷰 MAJOR-1).
      종전 판은 `any(x in f"/{rel}" for x in _SCAN_EXCLUDED)` 로 걸렀는데, `producers` 는
      **그 술어로 이미 걸러진** 집합이라 `_SCAN_EXCLUDED` 가 무엇이든 결과가 **항상 공집합**이었다.
      변이 `_SCAN_EXCLUDED = ()` 로 이 락만 돌려 확인: 모집단이 `.venv` 로 오염된 **그 상태에서
      초록**(`::VERDICT=SURVIVED`). ***잠긴 것처럼 보이는 무잠금***이었고, 독스트링은
      *"합성 락과 다른 축"* 이라고 **거짓을 주장**했다 — 다음 사람이 «두 축이 있다» 고 믿는다.

    ⇒ 판정을 **독립 리터럴**로 내린다. `_SCAN_EXCLUDED` 를 **참조하지 않는 것**이 이 락의 전부다.
    ★글자까지 같게 쓰지 않는다(`/` 없는 형태) — 같아지면 리팩토링 한 번에 **다시 한 축으로 접힌다**.
    ★역할 분담: 이 락은 **「venv 가 있는 환경」** 담당이고(CI 엔 없어 공허),
      반대편은 `test_the_exclusion_is_alive_in_every_environment` 의 **합성 트리**가 맡는다.
      **그때 비로소 축이 둘이 된다.**

    ★★**단일점 고지 — `/tests/` 는 이 락이 보지 않는다**(2026-09-12 실측 · 독립 리뷰 잔여 관측).
      아래 독립 리터럴은 `.venv`·`site-packages`·`node_modules` **셋만** 본다.
      즉 `_SCAN_EXCLUDED` 에서 **`/tests/` 만 죽으면 이 락은 초록**이고
      (실측: 이 락 단독 → `::VERDICT=SURVIVED` · 합성 락 단독 → `CAUGHT`),
      잡는 것은 **합성 락의 항목별 루프 하나뿐**이다.
      ⇒ 지금 커버리지에 **구멍은 없다.** 그러나 그 루프가 **`/tests/` 의 유일한 잠금**이다 —
        나중에 누가 합성 락을 「중복」이라 여겨 줄이면 **`/tests/` 가 두 축 모두에서 빠진다.**
      ***락을 더 만들 이유는 아니고, 무엇이 단일점인지 적어 둘 이유는 된다.***
    """
    root = pathlib.Path(__file__).resolve().parents[1]
    producers = _scan_role_producers(root)

    # ★대조군 먼저 — 비면 아래 「0건」이 공짜다.
    assert producers, "생산자를 하나도 못 찾았다 — 조회기가 죽었다"

    # ★본판정 — **독립 리터럴**(위 상수를 안 쓴다).
    polluted = [
        rel for rel in producers
        if ".venv" in rel or "site-packages" in rel or "node_modules" in rel
    ]
    assert not polluted, (
        f"모집단이 **제3자 코드로 부풀었다**({len(polluted)}건) — 스캔 범위가 소스를 벗어났다: "
        f"{polluted[:5]}"
    )


def test_the_ssot_does_not_carry_the_registration_default() -> None:
    """★**생산자 축** — 가입이 넣는 값이 이 집합에 다시 들어오면 실패한다.

    ★목록을 손으로 적지 않는다: `UserRole.ADMIN.value` 를 **가입 코드와 같은 원천**에서
      가져와 대조한다. 모집단은 `_scan_role_producers()` **한 곳**에서 나온다(사본 금지).
    """
    root = pathlib.Path(__file__).resolve().parents[1]
    producers = _scan_role_producers(root)

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


# ─────────────────────────────────────────────────────────────────────────────
# D. **과잉 차단이 0 이라는 근거**를 잠근다 (2026-09-12 · 내가 스스로 때린 축)
#
# 이 PR 의 안전 논거는 «`owns_site` 폴백이 남으니 자기 테넌트 현장은 계속 열린다» 다.
# 그런데 그 폴백이 주는 역할은 **`DEVELOPER`** 이고, 종전 가입 기본값이 받던 것은
# **`SUPERADMIN`**(= `require_role` 을 **무조건 통과**시키는 값)이었다.
# ⇒ 그러므로 안전 논거가 성립하려면 **분양 표면의 모든 `require_role` 이 DEVELOPER 를 받아야** 한다.
#
# ★실측(2026-09-12): 58건 중 **0건**이 DEVELOPER 를 빠뜨렸다 — 논거는 지금 참이다.
#   그러나 **미래의 `require_role("SUPERADMIN")` 한 줄이 이 논거를 조용히 깬다**
#   (테넌트 소유자가 자기 현장에서 403 을 받는데, 그 원인이 이 PR 로 되짚어지지 않는다).
#   그래서 **논거를 락으로** 바꾼다.
#
# ★조회기 교정 이력: 첫 판은 `ast.Constant` 인자만 봐서 `require_role("MEMBER", *_DRAW_MGR)` 를
#   **「MEMBER 전용」으로 오보**했다(별표 언패킹을 못 봄). 상수를 해석하도록 고쳤고,
#   **해석 못 한 호출은 조용히 넘기지 않고 드러낸다**(아래 `unresolved`).
# ─────────────────────────────────────────────────────────────────────────────

def _sales_require_role_calls() -> tuple[list[tuple[str, int, set[str]]], list[str]]:
    """분양 표면의 `deps_sales.require_role(...)` 호출을 **파생**한다 → (해석됨, 해석불가)."""
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    resolved: list[tuple[str, int, set[str]]] = []
    unresolved: list[str] = []

    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        src = ast.unparse(tree)
        # ★**같은 이름의 다른 헬퍼를 세지 않는다** — `app.core.rbac.require_role` 은 다른 함수다
        #   (실측: `cost.py`·`mass_templates.py` 가 그쪽을 쓰고 `Role.ADMIN` 을 넘긴다).
        if "from app.api.deps_sales import" not in src or "require_role" not in src:
            continue
        consts: dict[str, set[str]] = {}
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Tuple | ast.Set | ast.List):
                vals = {e.value for e in n.value.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)}
                for t in n.targets:
                    if isinstance(t, ast.Name) and vals:
                        consts[t.id] = vals
        rel = str(path.relative_to(root.parent))
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "require_role"):
                continue
            args: set[str] = set()
            ok = True
            for a in n.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    args.add(a.value)
                elif isinstance(a, ast.Starred) and isinstance(a.value, ast.Name) \
                        and a.value.id in consts:
                    args |= consts[a.value.id]       # ★별표 언패킹을 해석한다
                else:
                    ok = False
            if ok:
                resolved.append((rel, n.lineno, args))
            else:
                unresolved.append(f"{rel}:{n.lineno}")
    return resolved, unresolved


def test_every_sales_gate_admits_developer_so_tenant_owners_keep_their_sites() -> None:
    """★★이 PR 의 **안전 논거**를 락으로 — 자기 테넌트 소유자가 조용히 잃지 않는다."""
    resolved, unresolved = _sales_require_role_calls()

    # 공허 방지 — 모집단이 붕괴하면 「0건」이 공짜다.
    assert len(resolved) >= 40, f"수집 {len(resolved)}건 — 조회기가 죽었다"
    assert not unresolved, (
        "인자를 해석 못 한 `require_role` 호출이 있다 — **조용히 넘기지 않는다**. "
        f"상수를 해석하도록 이 조회기를 고치거나 호출을 단순화하라: {unresolved}"
    )

    missing = [f"{f}:{ln} {sorted(a)}" for f, ln, a in resolved if "DEVELOPER" not in a]
    assert not missing, (
        "분양 게이트가 **DEVELOPER 를 안 받는다** — 그러면 자기 테넌트 현장을 소유한 사용자가 "
        "403 을 받고, 그 원인이 이 PR(가입 기본값 제거)로 되짚어지지 않는다. "
        f"그 엔드포인트에 DEVELOPER 를 넣거나, 왜 제외인지 적어라: {missing}"
    )


def test_the_fallback_that_keeps_owners_in_is_still_developer() -> None:
    """★위 락이 지키는 **전제**가 그대로인지 — 폴백이 주는 역할이 바뀌면 위 락은 엉뚱한 것을 본다."""
    import ast
    import inspect

    src = inspect.getsource(deps_sales.resolve_site_membership)
    returns = {
        ast.unparse(n.value)
        for n in ast.walk(ast.parse(src.lstrip()))
        if isinstance(n, ast.Return) and n.value is not None
    }
    assert any("'DEVELOPER'" in r or '"DEVELOPER"' in r for r in returns), (
        f"소유자 폴백이 더 이상 DEVELOPER 를 주지 않는다 — 위 락의 축이 바뀌었다: {returns}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# E. **이 PR 이 실제로 바꾸는 행위**를 태운다 — 연결결산 게이트 (㉮ · 내가 남긴 약점)
#
# `views._TENANT_FINANCE_ROLES` 를 손복사 → SSOT 파생으로 바꾼 결과,
# **가입 기본값(`admin`)이 그 집합에서도 빠진다.** 그래서 동작이 갈린다:
#     소유 현장 0건인 tenant admin : 종전 통과 → **이제 403**
#     소유 현장 1건 이상            : 종전·지금 **통과**(`owns > 0` 폴백)
#
# ★기존 락(`test_sales_admin_console.py::TestRequireTenantFinance`)은 `viewer`·`developer`·
#   `superadmin` 을 태우는데 **`admin` 은 없다** — 즉 **이 PR 이 바꾸는 바로 그 모집단이
#   무잠금**이었다. 집합 파생만 잠그고 **그 결과 나는 403 은 아무도 안 태웠다.**
#
# ★이것은 **의도된 변경**이다(그 함수 독스트링: *"차단: 순수 viewer … 소유 현장 0"*).
#   그러나 **의도를 적는 것과 잠그는 것은 다르다** — 여기서 못 박아, 되돌아가면 빨개지게 한다.
# ★미측정(권한 부족): «소유 현장 0건인 tenant admin» 이 라이브에 **몇 명인지** 모른다
#   (DB 자격증명 없음). 도달성은 픽스처로 증명했고 **발생량은 미관측**이다.
# ─────────────────────────────────────────────────────────────────────────────

class _FinanceUser:
    def __init__(self, role: str, tenant_id):
        self.role = role
        self.tenant_id = tenant_id


class _OwnedCountDB:
    """소유 현장 수만 돌려주는 스텁 — `owns > 0` 폴백 분기를 가른다."""

    def __init__(self, owned: int):
        self._owned = owned
        self.calls = 0

    async def execute(self, *_a, **_k):
        self.calls += 1

        class _R:
            def __init__(self, n):
                self._n = n

            def scalar(self):
                return self._n

        return _R(self._owned)


@pytest.mark.asyncio
async def test_registration_default_no_longer_grants_tenant_finance_without_owning_a_site() -> None:
    """★★**모집단 ①** — 가입 기본값 + 소유 현장 **0** → **403**(이 PR 이 바꾸는 행위)."""
    from fastapi import HTTPException

    from app.api.endpoints.sales.views import require_tenant_finance

    db = _OwnedCountDB(owned=0)
    with pytest.raises(HTTPException) as ei:
        await require_tenant_finance(db=db, user=_FinanceUser("admin", "tenant-1"))
    assert ei.value.status_code == 403, (
        f"가입 기본값이 소유 현장 없이 연결결산을 본다({ei.value.status_code}) — "
        "손복사가 SSOT 파생으로 전파되지 않았다"
    )
    assert db.calls == 1, "소유 현장 폴백을 **거치기는 했는지** — 0회면 role 로 조기 통과한 것"


@pytest.mark.asyncio
async def test_owning_a_site_still_grants_tenant_finance_to_a_registered_user() -> None:
    """★★**모집단 ②(반대편)** — 같은 라벨인데 소유 현장이 **있으면 통과**한다.

    이것이 없으면 «전부 막는» 구현과 구별되지 않는다 — **과잉 차단도 결함이다.**
    """
    from app.api.endpoints.sales.views import require_tenant_finance

    db = _OwnedCountDB(owned=1)
    user = _FinanceUser("admin", "tenant-1")
    assert await require_tenant_finance(db=db, user=user) is user, (
        "자기 테넌트 현장을 소유한 사용자가 연결결산에서 막혔다 — 과잉 차단"
    )


@pytest.mark.asyncio
async def test_platform_label_still_short_circuits_without_touching_the_db() -> None:
    """★대조군 — 진짜 플랫폼 라벨은 **DB 를 안 거치고** 통과한다(집합이 안 비었다는 증거)."""
    from app.api.endpoints.sales.views import require_tenant_finance

    db = _OwnedCountDB(owned=0)
    user = _FinanceUser("superadmin", "tenant-1")
    assert await require_tenant_finance(db=db, user=user) is user
    assert db.calls == 0, "플랫폼 라벨인데 소유 현장을 조회했다 — 조기 반환이 죽었다"


# ─────────────────────────────────────────────────────────────────────────────
# F. **부채를 초록 안에 보이게** — 같은 클래스가 「쓰기」 경로에 하나 더 있다
#
# 계획서에 좌표와 함께 적었지만 **산문은 재발 저수지**다(이 저장소 원장: 교훈의 77%가 산문만).
# 여기서 `xfail(strict=True)` 로 **초록 안에 드러낸다**:
#   · 고치기 전 → `xfailed` 로 **매 실행마다 보인다**(커밋 메시지와 달리 사라지지 않는다)
#   · 고친 순간 → `XPASS` 가 **실패**로 뜬다 ⇒ 이 표식을 지우라고 기계가 말한다
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason=(
        "★부채(별건) — `market.py:48 _MANAGER_ROLES` 에 가입 기본값(`admin`·`owner`)이 그대로 있고 "
        "`:664` 에서 **테넌트·현장 검사 없이** 플랫폼 게이트로 쓰인다. 이 PR 은 `deps_sales` 축만 "
        "고쳤다(사용자 승인 범위). ★그쪽은 **쓰기 경로**라 자체 분석·리뷰가 필요하다: "
        "공고 INSERT(`market.py:436-452`, site 소유 검증 없음) → 작성자 본인 통과(`:610-637`) → "
        "`sales_org_nodes` INSERT(`:688-693`) → `deps_sales.py:224-232` 가 살아 있는 노드를 무조건 "
        "신뢰 ⇒ 남의 테넌트 현장에 **영속 멤버십**을 심을 수 있다(독립 리뷰 추론 · 쓰기 금지라 "
        "실증 안 함). ★반증조건: `job_posts` INSERT 앞에 site 소유 검증이 있거나 `sales_org_nodes` "
        "에 site↔tenant FK/트리거가 있으면 이 경로는 무너진다(애플리케이션 층 원문엔 없다). "
        "★고치면 이 테스트가 XPASS 로 **실패**한다 — 그때 이 표식을 지워라."
    ),
)
def test_market_manager_roles_also_drops_the_registration_default() -> None:
    """★**아직 안 고친 자리**를 초록 안에 보이게 둔다(같은 결함 클래스 · 쓰기 경로)."""
    import ast
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app/api/endpoints/sales/market.py").read_text(encoding="utf-8")
    roles: set[str] = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Set | ast.Tuple | ast.List):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == "_MANAGER_ROLES":
                    roles = {e.value for e in n.value.elts
                             if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    # ★공허 방지 — 상수를 못 찾으면 「위반 0」이 공짜가 된다(이 단언은 xfail 밖의 사실이다).
    assert roles, "`market._MANAGER_ROLES` 를 못 찾았다 — 이 부채 표식의 축이 죽었다"

    leaking = roles & {"admin", "owner"}
    assert not leaking, (
        f"`market._MANAGER_ROLES` 가 가입 기본값을 담고 있다: {sorted(leaking)}"
    )
