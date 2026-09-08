"""★현장 **발견 → 신청 → 승인** 파이프라인 — 행위 락 + 배선 락.

## 무엇을 지키나 (2026-09-09 · Stage 2)

1. **발견이 세 관계를 실제로 가른다** — `active` / `pending` / `none`
   («세 값이 서로 다른 다음 행동을 뜻한다» 가 이 모듈의 논지인데, 한 값으로 뭉개도
   초록이면 그 논지는 잠기지 않은 것이다)
2. **발견이 테넌트 식별자를 안 흘린다** — `organization_id` 부재를 **직접** 단언
3. **승인이 `create_node` 를 경유한다** — raw INSERT 로 되돌리면 고아 루트가 생기고
   수수료 RESIDUAL 전액이 신입에게 꽂힌다(PR #1021 이 봉합한 결함)
4. **승인 권한이 「관리자 및 상위레벨」로 좁다** — MEMBER 는 승인할 수 없다
5. **사유 어휘를 채용 승인 경로와 공유한다** — 번역표가 두 벌이 되면 하나가 낡는다

★**이 파일에는 `skipif` 가 없다.** 앞선 PR 에서는 판정이 라우터에 있어 행위 락이 전부
  «CI 에서 처음 실행되는 테스트» 였다(개발 환경 python 3.10 이 `app/crud/base.py` 의
  PEP 695 문법 `class CRUDBase[M]:` 를 **파싱조차 못 한다**). 판정을 **서비스 층**
  (`app/services/sales/org/join.py`)으로 내리자 sqlalchemy + 모델만 끌고 오게 되어
  **로컬에서도 전부 태워진다.** 「태울 수 있는 자리에 두는 것」이 락 설계의 일부다.

축은 둘이다 — **판정**은 서비스 층(`_SVC`), **배선·격리**는 라우터(`_MODULE`).
어느 쪽을 보는 락인지 파일 상수로 구분한다.
"""

from __future__ import annotations

import ast
import subprocess
import uuid
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_API = _HERE.parents[1]
_MODULE = _API / "app/api/endpoints/sales/site_join.py"   # 라우터(배선·격리)
_SVC = _API / "app/services/sales/org/join.py"            # 서비스 층(판정)

# ★`skipif` 가 **없다** — 그게 이 파일의 설계다.
#   앞선 PR 에서 판정을 라우터에 두었더니 행위 락이 전부 «CI 에서 처음 실행되는 테스트» 가 됐다
#   (이 저장소는 개발 환경 python 3.10 에서 `app/crud/base.py` 의 PEP 695 문법을 **파싱조차 못 한다**).
#   판정을 **서비스 층**(`org/join.py`)으로 내리자 sqlalchemy + 모델만 끌고 오게 되어
#   **로컬에서도 태워진다.** 「태울 수 있는 자리에 두는 것」이 락 설계의 일부다.


def _tree(path: Path = _MODULE) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _fn(name: str, path: Path = _MODULE) -> ast.AsyncFunctionDef:
    for n in ast.walk(_tree(path)):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == name:
            return n
    raise AssertionError(f"`{name}` 을 {path.name} 에서 찾지 못했다 — 축이 죽었다")


# ═══════════════════════════════════════════════════════════════════════════
# A. 배선 — AST(임포트 불필요 · 어디서나 돈다)
# ═══════════════════════════════════════════════════════════════════════════

def test_module_is_registered_on_the_sales_router() -> None:
    """★라우터가 **실제로 등록**되는가 — 파일만 만들고 안 붙이면 라우트 0건이다.

    ★축은 **파일 존재**가 아니라 `include_router` **호출 인자**다.
    """
    src = (_API / "app/api/endpoints/sales/__init__.py").read_text(encoding="utf-8")
    included = [
        c.args[0].id
        for c in ast.walk(ast.parse(src))
        if isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "include_router"
        and c.args and isinstance(c.args[0], ast.Name)
    ]
    # 공허 방지 — 목록이 비면 아래 포함 단언이 «파서가 죽었다» 와 구별되지 않는다.
    assert len(included) >= 8, f"include_router 수집이 비정상({len(included)})"
    assert "site_join_router" in included, "신규 라우터가 sales 라우터에 안 붙었다 — 라우트 0건"


def test_approval_goes_through_create_node_not_raw_insert() -> None:
    """★★승인이 **`create_node` 를 경유**하는가 — raw INSERT 는 금지.

    raw INSERT 는 `create_node` 의 **루트=AGENCY** 규칙과 **직속 위계** 규칙을 전부 우회한다.
    그러면 고아 루트가 생기고 정산이 `chain[0]` 을 대행사로 보므로
    **수수료 RESIDUAL 전액이 신입에게** 꽂힌다(PR #1021 이 봉합한 그 결함이 새 문으로 재유입).

    ★축은 **함수의 호출 노드**다(파일 grep 아님 — 독스트링에 그 낱말이 여러 번 나온다).
    """
    fn = _fn("link_membership", _SVC)
    calls = {c.func.id for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "create_node" in calls, "멤버십 생성이 `create_node` 를 안 거친다"

    # 같은 함수 안의 **실행 문자열 리터럴**만 본다(독스트링·주석 제외).
    doc_ids = {id(fn.body[0].value)} if (
        fn.body and isinstance(fn.body[0], ast.Expr)
        and isinstance(fn.body[0].value, ast.Constant)) else set()
    lits = " ".join(
        c.value.lower() for c in ast.walk(fn)
        if isinstance(c, ast.Constant) and isinstance(c.value, str) and id(c) not in doc_ids
    )
    assert "insert into sales_org_nodes" not in lits, (
        "승인 경로가 조직 노드를 **raw INSERT** 로 만든다 — 규칙을 전부 우회한다"
    )


def test_discover_does_not_leak_the_tenant_identifier() -> None:
    """★발견 목록이 `organization_id` 를 **안 싣는다** — 모듈이 선언한 격리의 실체.

    ★선언(주석)이 아니라 **응답 dict 의 키**를 본다. 주석은 지워도 아무것도 안 깨진다.
    """
    fn = _fn("discover_sites")
    keys: set[str] = set()
    for d in ast.walk(fn):
        if isinstance(d, ast.Dict):
            keys |= {k.value for k in d.keys
                     if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    # 공허 방지 — 응답 dict 를 못 찾으면 아래 부재 단언이 무의미하다.
    assert {"site_id", "site_name", "membership"} <= keys, f"응답 키 수집 실패: {sorted(keys)}"
    assert "organization_id" not in keys, (
        "발견 목록이 **어느 시행사의 현장인가**를 흘린다 — 요구를 넘어선 노출이다"
    )


def test_reason_vocabulary_is_shared_with_the_hiring_approval() -> None:
    """★사유 어휘가 채용 승인 경로(`market.py`)에서 **온다** — 사본이면 하나가 낡는다.

    ★사본을 만들었는지 보는 방법은 «`_LINKED_REASONS` 를 임포트하는가» 다.
      이 모듈 안에서 **재정의**하면 두 승인 경로가 서로 다른 말을 하게 된다.
    """
    tree = _tree()
    imported = {
        a.name
        for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
        and (n.module or "").endswith("sales.market")
        for a in n.names
    }
    assert "_LINKED_REASONS" in imported, "사유 어휘를 채용 경로에서 안 가져온다"

    redefined = [
        t.id for n in ast.walk(tree) if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Name)
        and t.id in {"_LINKED_REASONS", "_MEMBERSHIP_REASONS"}
    ]
    assert not redefined, f"사유 어휘를 이 모듈에서 **재정의**했다: {redefined}"


def test_no_import_cycle_market_does_not_depend_on_join() -> None:
    """★방향을 잠근다 — `market` 은 이 모듈을 임포트하지 않는다(순환 금지).

    이 모듈이 `market` 을 임포트하므로, 반대 방향이 생기는 순간 앱이 **기동 자체를 못 한다.**
    주석에 «순환 없음» 이라고 쓴 것을 **기계가 지키게** 한다.
    """
    market = (_API / "app/api/endpoints/sales/market.py").read_text(encoding="utf-8")
    modules = {
        (n.module or "") for n in ast.walk(ast.parse(market)) if isinstance(n, ast.ImportFrom)
    }
    # 공허 방지 — market 이 무언가는 임포트한다.
    assert len(modules) >= 3, "market 의 임포트 수집이 비정상"
    assert not any("site_join" in m for m in modules), "순환 임포트가 생겼다"


def test_member_cannot_approve() -> None:
    """★「관리자 및 상위레벨」의 기계적 정의에 **MEMBER 가 없다**.

    MEMBER 는 서열 최하위라 아래를 승인할 대상이 없다(`_ORG_RANK` 와 정합).
    ★두 모집단으로 본다 — 없어야 할 것이 없고, **있어야 할 것이 있다**.
      후자가 없으면 «집합을 통째로 비워도» 초록이다.
    """
    approvers: set[str] = set()
    for n in ast.walk(_tree(_SVC)):
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "APPROVER_NODE_TYPES" for t in n.targets):
            approvers = {c.value for c in ast.walk(n)
                         if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    assert "MEMBER" not in approvers, "말단 직원이 남을 현장에 들일 수 있다"
    assert {"AGENCY", "TEAM_LEADER"} <= approvers, (
        f"승인자 집합이 비었거나 좁다: {sorted(approvers)} — 아무도 승인 못 하면 파이프라인이 죽는다"
    )


def test_pending_uniqueness_is_partial_not_total() -> None:
    """★유일성이 **대기 중에만** 걸리는가 — 전체 유니크면 **재신청이 원리적으로 불가**다.

    거절당한 사람이 나중에 다시 신청하는 것은 정당하다.
    정상 사용을 막는 가드는 그 자체가 결함이다.
    """
    src = _MODULE.read_text(encoding="utf-8")
    flat = " ".join(src.split())
    assert "CREATE UNIQUE INDEX IF NOT EXISTS ux_join_pending_one" in flat, "유일성 인덱스가 없다"
    idx = flat.index("ux_join_pending_one")
    assert "WHERE status = 'pending'" in flat[idx:idx + 260], (
        "유일성이 **전체**에 걸렸다 — 거절 뒤 재신청이 영원히 막힌다"
    )


# ═══════════════════════════════════════════════════════════════════════════
# B. 행위 — **원문 함수를 직접 부른다**(서비스 층이라 로컬에서도 돈다)
# ═══════════════════════════════════════════════════════════════════════════

pytestmark_async = pytest.mark.asyncio


class _Node:
    def __init__(self, node_type="TEAM_LEADER", path="a1.t1"):
        self.id = uuid.uuid4()
        self.node_type = node_type
        self.path = path


@pytest.mark.asyncio
async def test_link_membership_holds_when_there_is_no_parent(monkeypatch) -> None:
    """★★붙일 자리가 없으면 **고아를 만들지 않고 보류**한다.

    이것이 이 파이프라인의 돈 축이다 — 조용히 루트를 만들면
    수수료 RESIDUAL 전액이 신입에게 간다.
    ★그리고 보류는 **전용 사유**로 말한다(«실패» 도 «해당없음» 도 아니다).
    """
    from app.services.sales.org import join as mod

    created: list = []

    async def _create(*a, **kw):
        created.append((a, kw))

    monkeypatch.setattr(mod, "create_node", _create, raising=True)

    class _Res:
        def first(self): return None
        def scalars(self): return self
        def all(self): return []
    class _DB:
        async def execute(self, *_a, **_k): return _Res()

    reason = await mod.link_membership(_DB(), uuid.uuid4(), uuid.uuid4(), None)
    assert reason == "ORG_NOT_SEEDED"
    assert created == [], "★붙일 자리가 없는데 노드를 만들었다 — 고아 루트다"


@pytest.mark.asyncio
async def test_link_membership_attaches_under_the_approver(monkeypatch) -> None:
    """★★**반대편 모집단** — 승인자 노드가 있으면 **그 아래**에 붙고 `LINKED` 를 낸다.

    이것이 없으면 위 단언이 «항상 보류한다» 와 구별되지 않는다(파이프라인이 통째로 죽어도 초록).
    ★부모가 **승인자**여야 수수료 체인이 승인자의 체인을 물려받는다.
    """
    from app.services.sales.org import join as mod

    seen: dict = {}

    async def _create(_db, site_id, node_type, parent_id=None, **kw):
        seen.update(site_id=site_id, node_type=node_type, parent_id=parent_id, kw=kw)

    monkeypatch.setattr(mod, "create_node", _create, raising=True)

    approver = _Node("TEAM_LEADER")

    class _Res:
        def first(self): return None
        def scalars(self): return self
        def all(self): return []
    class _DB:
        async def execute(self, *_a, **_k): return _Res()

    site, applicant = uuid.uuid4(), uuid.uuid4()
    reason = await mod.link_membership(_DB(), site, applicant, approver)
    assert reason == "LINKED"
    assert seen["node_type"] == "MEMBER"
    assert seen["parent_id"] == approver.id, "승인자 아래가 아니라 다른 곳에 붙었다"
    assert seen["kw"]["user_id"] == applicant


@pytest.mark.asyncio
async def test_link_membership_is_idempotent_for_existing_member(monkeypatch) -> None:
    """★이미 멤버면 **다시 만들지 않는다** — 중복 노드는 역할 판정을 흔든다."""
    from app.services.sales.org import join as mod

    created: list = []

    async def _create(*a, **kw):
        created.append(1)

    monkeypatch.setattr(mod, "create_node", _create, raising=True)

    class _Res:
        def first(self): return (uuid.uuid4(),)      # 기존 멤버 있음
        def scalars(self): return self
        def all(self): return []
    class _DB:
        async def execute(self, *_a, **_k): return _Res()

    reason = await mod.link_membership(_DB(), uuid.uuid4(), uuid.uuid4(), _Node())
    assert reason == "ALREADY_MEMBER"
    assert created == [], "이미 멤버인데 노드를 또 만들었다"


@pytest.mark.asyncio
async def test_link_membership_reports_reason_when_guard_rejects(monkeypatch) -> None:
    """★`create_node` 의 가드가 거부하면 **삼키지 않고 사유로 말한다**.

    ★삼키고 `LINKED` 를 돌려주면 «승인됐다» 는데 조직도엔 아무도 없는 유령 상태가 된다
      (그 은폐가 PR #1021 이 고친 결함의 원형이다).
    """
    from app.services.sales.org import join as mod

    async def _create(*_a, **_k):
        raise ValueError("직속 위계 위반")

    monkeypatch.setattr(mod, "create_node", _create, raising=True)

    class _Res:
        def first(self): return None
        def scalars(self): return self
        def all(self): return []
    class _DB:
        async def execute(self, *_a, **_k): return _Res()

    reason = await mod.link_membership(_DB(), uuid.uuid4(), uuid.uuid4(), _Node())
    assert reason == "ORG_NOT_SEEDED", f"가드 거부를 삼켰다(사유={reason})"


@pytest.mark.asyncio
async def test_approver_resolution_two_populations(monkeypatch) -> None:
    """★★승인 권한 — **MEMBER 는 거부되고 TEAM_LEADER 는 통과**한다(같은 실행에서)."""
    from app.services.sales.org import join as mod

    def _db_with(node):
        class _Res:
            def scalars(self): return self
            def first(self): return node
        class _DB:
            async def execute(self, *_a, **_k): return _Res()
        return _DB()

    plain = type("U", (), {"id": uuid.uuid4(), "role": "user"})()

    can, parent = await mod.resolve_approver_node(_db_with(_Node("MEMBER")), uuid.uuid4(), plain)
    assert can is False and parent is None, "말단 직원이 승인할 수 있다"

    can, parent = await mod.resolve_approver_node(
        _db_with(_Node("TEAM_LEADER")), uuid.uuid4(), plain)
    assert can is True and parent is not None, "팀장이 승인 못 하면 파이프라인이 죽는다"
    assert parent.node_type == "TEAM_LEADER", "부모로 쓸 노드를 **함께** 돌려줘야 한다"


@pytest.mark.asyncio
async def test_platform_operator_can_approve_without_a_node(monkeypatch) -> None:
    """★조직도에 노드가 없는 **플랫폼 운영자**도 승인할 수 있다(부모는 None → AGENCY 루트로).

    ★이 분기가 없으면 «조직도를 아직 안 만든 현장» 은 **아무도 승인할 수 없어** 영원히 막힌다.
    """
    from app.services.sales.org import join as mod

    class _Res:
        def scalars(self): return self
        def first(self): return None
    class _DB:
        async def execute(self, *_a, **_k): return _Res()

    admin = type("U", (), {"id": uuid.uuid4(), "role": "superadmin"})()
    can, parent = await mod.resolve_approver_node(_DB(), uuid.uuid4(), admin)
    assert can is True and parent is None


# ═══════════════════════════════════════════════════════════════════════════
# C. 상태 어휘 — 코드가 내는 값이 목록 안에 있는가
# ═══════════════════════════════════════════════════════════════════════════

def test_every_emitted_status_is_declared() -> None:
    """★`JOIN_STATUSES` 밖의 상태를 SQL 로 쓰지 않는가 — 프론트가 번역 못 하는 값 금지."""
    tree = _tree()
    declared: set[str] = set()
    decl_node = None
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "JOIN_STATUSES" for t in n.targets):
            decl_node = n
            declared = {c.value for c in ast.walk(n)
                        if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    assert len(declared) >= 3, f"상태 목록이 비었거나 좁다: {declared}"

    # SQL 리터럴 안의 `status = 'x'` / `'x'` 대입을 훑는다(선언 자신은 뺀다 — 자기지시 금지).
    decl_ids = {id(c) for c in ast.walk(decl_node)} if decl_node else set()
    import re
    emitted: set[str] = set()
    for c in ast.walk(tree):
        if isinstance(c, ast.Constant) and isinstance(c.value, str) and id(c) not in decl_ids:
            emitted |= set(re.findall(r"status\s*=\s*'([a-z_]+)'", c.value))
    # 공허 방지 — 하나도 못 찾으면 아래 포함 단언이 무의미하다.
    assert emitted, "SQL 에서 상태 리터럴을 하나도 못 찾았다 — 조회기가 죽었다"
    assert emitted <= declared, f"목록에 없는 상태를 쓴다: {sorted(emitted - declared)}"


def test_module_has_no_uncommitted_mutation_sentinel() -> None:
    """★변이 표식이 이 신규 파일에 실려 있지 않은가(형제 락의 로컬 판)."""
    sentinel = "__MUT" + "ATED__"
    head = subprocess.run(
        ["git", "show", f"HEAD:{_MODULE.relative_to(_API.parents[1])}"],
        cwd=_API, capture_output=True, text=True, check=False)
    if head.returncode != 0:
        pytest.skip("아직 커밋되지 않은 신규 파일 — 저장소 전역 센티널 락이 커밋 후 잡는다")
    assert sentinel not in head.stdout
