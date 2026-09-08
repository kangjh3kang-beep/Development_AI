"""★고아 루트 노드가 수수료 전액을 가져가지 못하게 — **두 모집단**으로 잠근다.

## 왜 이 파일이 있나 (2026-09-08)

승인 경로(`market._link_membership_on_accept`)가 raw INSERT 로 `path=라벨 1개` ·
`parent_id` 미지정 = **루트 고아 MEMBER 노드**를 만들었다. 그런데 정산
(`commission/engine.py:163-182`)은 `chain[0]` 을 대행사로 **가정**한다:

    chain = ancestors_path(...)      # 루트면 [자기자신] 하나
    agency = chain[0]                # ← 자기 자신
    for node in chain[1:]  → 없음    ⇒ allocated = 0
    residual = total - 0 = total
    Split(node_id=agency.id, basis="RESIDUAL", amount=residual)

⇒ **수수료 100% 가 신규 MEMBER 에게**, 그것도 「대행사 몫」 자리에 `node_type='MEMBER'` 로.
대행사·본부장·팀장 배분 **0원**.

★저장소가 지키려던 것을 정확히 깬다 — `actions.py:43-48` 이
*"상위가 말단을 건너뛰면 **수수료 2단 배분 기준이 붕괴**한다"* 고 적어 둔 그것이다.
그리고 `actions.py:113-116` 은 **루트 생성 시 AGENCY 아니면 400** 인데,
**같은 테이블의 다른 생산자가 그 규칙을 안 걸고 있었다.**

★**라이브 실측(2026-09-08)**: 고아 루트 **0건**(조직도 3현장 · 117노드 ·
MEMBER 101건이 전부 깊이 2 이상 — 대조군이 이 0을 의미있게 만든다).
⇒ **도달 가능하나 미발화.** 사용자 요구(전체 열람→신청→승인)가 이 경로를 **온보딩 주 진입로**로
만들기 **전에** 고친다.

## 이 파일이 잠그는 것 — 두 층(하나만으로는 우회 경로가 생기면 다시 샌다)

1. **생성 층** — `create_node` 가 부모 없는 비-AGENCY 를 **거부**한다
2. **정산 층** — 체인 최상위가 AGENCY 가 아니면 배분을 **거부**한다

★두 모집단이 **서로 다른 결과**를 내야 한다. 「거부된다」만 단언하면
«모든 입력이 거부된다» 와 구별되지 않는다 — 정상 입력이 **통과하는 것**도 같이 태운다.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio


# ─────────────────────────────────────────────────────────────────────────────
# 생성 층 — create_node 의 루트 규칙
# ─────────────────────────────────────────────────────────────────────────────

class _FakeNode:
    """`create_node` 가 만드는 노드의 최소 대역 — path 계산만 태운다."""

    def __init__(self, **kw):
        self.id = uuid.uuid4()
        self.path = kw.get("path", "tmp")
        self.node_type = kw.get("node_type")
        self.parent_id = kw.get("parent_id")
        self.site_id = kw.get("site_id")
        for k, v in kw.items():
            setattr(self, k, v)


async def test_create_node_rejects_orphan_non_agency(monkeypatch) -> None:
    """★부모 없는 **비-AGENCY** 는 거부된다 — 이 결함의 근원."""
    from app.services.sales.org import service as svc

    class _DB:
        def add(self, _obj): pass
        async def flush(self): pass
        async def execute(self, *_a, **_k):  # parent 조회는 호출되지 않는다(parent_id=None)
            raise AssertionError("parent_id 가 없으면 부모를 조회하면 안 된다")

    monkeypatch.setattr(svc, "SalesOrgNode", _FakeNode, raising=True)

    with pytest.raises(ValueError) as ei:
        await svc.create_node(_DB(), uuid.uuid4(), "MEMBER", parent_id=None)
    # 사유가 사람에게 도달하는가 — 무언 거부는 진단 불가다.
    assert "AGENCY" in str(ei.value)


async def test_create_node_allows_orphan_agency(monkeypatch) -> None:
    """★두 모집단 — 부모 없는 **AGENCY** 는 정상이다(현장의 시작점).

    이것이 없으면 위 단언이 «모든 루트를 막는다» 와 구별되지 않는다.
    """
    from app.services.sales.org import service as svc

    class _DB:
        def add(self, _obj): pass
        async def flush(self): pass

    monkeypatch.setattr(svc, "SalesOrgNode", _FakeNode, raising=True)

    node = await svc.create_node(_DB(), uuid.uuid4(), "AGENCY", parent_id=None)
    assert node.node_type == "AGENCY"
    # 루트라 path 에 점이 없다.
    assert "." not in str(node.path)


async def test_create_node_allows_child_member(monkeypatch) -> None:
    """★★**반대편 모집단** — 부모가 있는 MEMBER 는 **정상 생성**된다.

    이것이 없으면 가드가 «부모 조건» 을 잃어도(=모든 비-AGENCY 를 막아도) 초록이다.
    실제로 그 변이가 **SURVIVED** 했다(2026-09-08):

        if parent is None and str(node_type) != "AGENCY":  →  if str(node_type) != "AGENCY":
            ::VERDICT=SURVIVED

    그 변이는 **정상 조직 확장을 통째로 막는다**(팀원을 못 넣는다) — 위양성도 결함이다.
    ⇒ 「막아야 할 것이 막힌다」와 「막지 말아야 할 것이 통과한다」를 **같은 실행에서** 태운다.
    """
    from app.services.sales.org import service as svc

    site = uuid.uuid4()
    parent = _FakeNode(node_type="AGENCY", path="a1", site_id=site)

    class _Res:
        def scalar_one_or_none(self): return parent

    class _DB:
        def add(self, _obj): pass
        async def flush(self): pass
        async def execute(self, *_a, **_k): return _Res()

    # ★`SalesOrgNode` 를 통째로 대체하면 `select(SalesOrgNode)` 가 ArgumentError 를 낸다
    #   (SQLAlchemy 가 실제 매핑 클래스를 요구한다). 그래서 **생성만** 가로챈다 —
    #   부모 조회는 원본 클래스로 가고, 조회 결과는 위 `_DB` 가 돌려준다.
    real = svc.SalesOrgNode

    class _Ctor(real):  # type: ignore[misc,valid-type]
        def __new__(cls, **kw):  # noqa: D401
            return _FakeNode(**kw)

    monkeypatch.setattr(svc, "SalesOrgNode", _Ctor, raising=True)

    node = await svc.create_node(_DB(), site, "MEMBER", parent_id=parent.id)
    assert node.node_type == "MEMBER"
    # 부모 path 를 상속한다 — 체인이 대행사에서 시작한다는 뜻이다.
    assert str(node.path).startswith("a1.")


# ─────────────────────────────────────────────────────────────────────────────
# 생성 층 (2) — **위계**도 생성 함수가 강제하는가 (2026-09-08 적대 리뷰 M1)
# ─────────────────────────────────────────────────────────────────────────────
#
# ★M1 의 지적: 루트 규칙만 `create_node` 로 내리고 **위계 규칙은 라우터에 남겨 뒀다.**
#   그래서 «두 생산자가 정반대 규칙을 갖는다» 는 이 PR 의 논지가 **절반만** 실행됐다.
#   실측(파생형 — `_ORG_RANK` 소비처 전수)으로 위계 판정은 `actions.py` 안에 **두 벌**이었다:
#   `add_node`(생성) · `move_node`(이동). `org/service.py` 는 `app.api.endpoints` 를
#   **0회** 임포트하므로, 그 표를 서비스 층으로 옮겨야 순환 없이 공유된다.


def _parent_child_db(monkeypatch, svc, parent):
    """부모 조회는 `parent` 를 돌려주고, 노드 생성만 가로채는 최소 대역."""
    class _Res:
        def scalar_one_or_none(self): return parent

    class _DB:
        def add(self, _obj): pass
        async def flush(self): pass
        async def execute(self, *_a, **_k): return _Res()

    real = svc.SalesOrgNode

    class _Ctor(real):  # type: ignore[misc,valid-type]
        def __new__(cls, **kw):
            return _FakeNode(**kw)

    monkeypatch.setattr(svc, "SalesOrgNode", _Ctor, raising=True)
    return _DB()


async def test_create_node_rejects_member_under_member(monkeypatch) -> None:
    """★**부모 MEMBER + 자식 MEMBER → 거부** — 리뷰가 지정한 한 줄.

    라우터를 안 거치는 생산자(`market._link_membership_on_accept`)는 승인자의 노드를 부모로
    삼는다. 승인자가 **말단 MEMBER** 여도 라우터 검증을 안 거치므로 종전엔 그대로 통과했고,
    `MEMBER → MEMBER` 사슬이 만들어져 배분 단계가 어긋난다.
    """
    from app.services.sales.org import service as svc

    site = uuid.uuid4()
    parent = _FakeNode(node_type="MEMBER", path="a1.t1.m1", site_id=site)
    db = _parent_child_db(monkeypatch, svc, parent)

    with pytest.raises(ValueError) as ei:
        await svc.create_node(db, site, "MEMBER", parent_id=parent.id)
    # ★사유가 사람에게 도달하는가 — 두 타입이 모두 문구에 실려야 어느 조합이 막혔는지 안다.
    assert "MEMBER" in str(ei.value)
    assert "위계" in str(ei.value)


async def test_create_node_allows_member_under_team_leader(monkeypatch) -> None:
    """★★**반대편 모집단** — 정상 위계(TEAM_LEADER → MEMBER)는 **통과한다**.

    이것이 없으면 위 단언이 «모든 부모-자식을 막는다» 와 구별되지 않는다
    (`assert_hierarchy` 를 무조건 raise 로 바꿔도 초록이 된다).
    """
    from app.services.sales.org import service as svc

    site = uuid.uuid4()
    parent = _FakeNode(node_type="TEAM_LEADER", path="a1.t1", site_id=site)
    db = _parent_child_db(monkeypatch, svc, parent)

    node = await svc.create_node(db, site, "MEMBER", parent_id=parent.id)
    assert node.node_type == "MEMBER"
    assert str(node.path).startswith("a1.t1.")


async def test_create_node_rejects_inverted_hierarchy(monkeypatch) -> None:
    """★같은 서열뿐 아니라 **역전**(팀장 아래 대행사)도 막힌다 — `>=` 의 두 변."""
    from app.services.sales.org import service as svc

    site = uuid.uuid4()
    parent = _FakeNode(node_type="TEAM_LEADER", path="a1.t1", site_id=site)
    db = _parent_child_db(monkeypatch, svc, parent)

    with pytest.raises(ValueError):
        await svc.create_node(db, site, "AGENCY", parent_id=parent.id)


async def test_create_node_rejects_unknown_node_type(monkeypatch) -> None:
    """★미등재 타입은 **fail-closed** — 서열표에 없으면 통과가 아니라 거부다.

    `_ORG_RANK.get()` 이 `None` 을 주는데 그것을 «비교 불가라 통과» 로 처리하면
    오타 하나로 위계 전체가 꺼진다.
    """
    from app.services.sales.org import service as svc

    site = uuid.uuid4()
    parent = _FakeNode(node_type="AGENCY", path="a1", site_id=site)
    db = _parent_child_db(monkeypatch, svc, parent)

    with pytest.raises(ValueError):
        await svc.create_node(db, site, "MEMBERR", parent_id=parent.id)


# ─────────────────────────────────────────────────────────────────────────────
# 계약 층 — 담당 노드가 **배분 가능한 체인**을 갖는가
# ─────────────────────────────────────────────────────────────────────────────
#
# ★★기계 변이가 짚어 준 자리(2026-09-08 · 60변이 중 생존 8건이 전부 이 블록):
#
#     if not chain:                                   → 조건무력화 ::VERDICT=SURVIVED
#     if str(chain[0].node_type) != "AGENCY":         → 조건무력화 ::VERDICT=SURVIVED
#
#   이 PR 이 «돈이 새는 것을 막았다» 고 선언한 자리가 **무잠금**이었다. 원인은 판정이
#   **라우터 안에 인라인**이라(`actions.record_contract`) 태우려면 FastAPI 의존을 다 세워야 했던 것.
#   ⇒ 판정을 `org/service.assert_commissionable_chain` 으로 내리고 **여기서 직접 태운다.**
#   ★M1 과 같은 형태의 형제다 — 규칙을 라우터에 두면 아무도 못 태운다.


class _ChainNode:
    def __init__(self, node_type: str):
        self.id = uuid.uuid4()
        self.node_type = node_type


def _patch_chain(monkeypatch, chain):
    """`ancestors_path` 만 갈아 끼운다 — 판정 로직은 **원문**을 태운다."""
    from app.services.sales.org import service as svc

    async def _fake(_db, _site, _node):
        return chain

    monkeypatch.setattr(svc, "ancestors_path", _fake, raising=True)
    return svc


async def test_commissionable_chain_rejects_empty_chain(monkeypatch) -> None:
    """★체인이 비면(현장 밖·미존재·삭제됨) **거부**한다."""
    svc = _patch_chain(monkeypatch, [])
    with pytest.raises(svc.OrgNodeNotFoundError):
        await svc.assert_commissionable_chain(None, uuid.uuid4(), uuid.uuid4())


async def test_commissionable_chain_rejects_non_agency_root(monkeypatch) -> None:
    """★최상위가 대행사가 아니면 **거부**한다 — RESIDUAL 전액 귀속을 막는 그 조건."""
    svc = _patch_chain(monkeypatch, [_ChainNode("MEMBER")])
    with pytest.raises(svc.OrgChainNotCommissionableError):
        await svc.assert_commissionable_chain(None, uuid.uuid4(), uuid.uuid4())


async def test_commissionable_chain_allows_agency_root(monkeypatch) -> None:
    """★★**반대편 모집단** — 정상 체인은 통과하고 **체인을 돌려준다**.

    이것이 없으면 위 둘이 «모든 입력을 거부한다» 와 구별되지 않는다
    (계약 체결이 통째로 막히는 것도 결함이다).
    """
    chain = [_ChainNode("AGENCY"), _ChainNode("TEAM_LEADER"), _ChainNode("MEMBER")]
    svc = _patch_chain(monkeypatch, chain)
    out = await svc.assert_commissionable_chain(None, uuid.uuid4(), uuid.uuid4())
    assert out is chain, "호출자가 재조회하지 않도록 체인을 그대로 돌려줘야 한다"


async def test_commissionable_chain_distinguishes_its_two_failures() -> None:
    """★두 실패가 **서로 다른 예외**인가 — 라우터가 404/409 로 갈라야 한다.

    한 예외로 뭉치면 사용자는 «못 찾았다» 와 «찾았는데 배분이 안 된다» 를 구별할 수 없고,
    조치도 달라진다(노드를 다시 고른다 / **조직도에서 상위를 지정한다**).
    """
    from app.services.sales.org import service as svc

    assert svc.OrgChainNotCommissionableError is not svc.OrgNodeNotFoundError
    assert not issubclass(svc.OrgChainNotCommissionableError, svc.OrgNodeNotFoundError)
    assert not issubclass(svc.OrgNodeNotFoundError, svc.OrgChainNotCommissionableError)


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="★이 저장소는 개발 환경(3.10)에서 **파싱조차 안 된다** — `app/crud/base.py` 가 3.11+ 문법. "
           "`datetime.UTC` 셰임으로 우회를 시도했으나 SyntaxError 라 원리적으로 불가. "
           "⇒ 이 락은 **CI(3.12)에서 처음 실행된다**(로컬 미실행 = 부채, 계획서 §5 에 명시). "
           "같은 축을 임포트 없이 보는 `test_router_wiring_is_declared_in_source` 는 로컬에서 돌고, "
           "그쪽으로 생존 3건이 CAUGHT 로 뒤집히는 것을 실측했다.",
)
async def test_contract_create_actually_validates_the_member_node(monkeypatch) -> None:
    """★★**행위 락** — 라우터가 담당 노드를 **실제로 검증하고 결과를 넘기는가**.

    ★기계 변이가 남긴 생존 3건이 정확히 이 배선이다(2026-09-08):

        if mnode:                      → `if False:` ::VERDICT=SURVIVED   ← 검증이 통째로 꺼진다
        mnode = mnode_uuid             → 줄삭제      ::VERDICT=SURVIVED   ← 원문 문자열이 그대로 간다
        member_node_id=mnode,          → 줄삭제      ::VERDICT=SURVIVED   ← 담당자가 사라진다

    앞선 락들은 **서비스 함수**를 태운다 — 「함수가 옳다」는 「그것이 불린다」를 함의하지 않는다.
    저장소가 여러 번 데인 자리라 여기서는 **핸들러를 직접 호출**한다.
    """
    from app.api.endpoints.sales import actions as router

    seen: dict = {}

    async def _fake_assert(_db, site_id, node_id):
        seen["asserted"] = (site_id, node_id)
        return [_ChainNode("AGENCY")]

    async def _fake_create(_db, _site, _unit, **kw):
        seen["create_kwargs"] = kw
        return type("C", (), {"id": uuid.uuid4(), "stage": "CONTRACTED", "total_price": 100})()

    monkeypatch.setattr(router, "assert_commissionable_chain", _fake_assert, raising=True)
    monkeypatch.setattr(router, "create_contract", _fake_create, raising=True)

    class _DB:
        async def commit(self): pass
        async def rollback(self): pass

    site = uuid.uuid4()
    ctx = type("Ctx", (), {"site_id": site, "user": type("U", (), {"id": uuid.uuid4()})()})()
    unit, node = uuid.uuid4(), uuid.uuid4()

    # ── 모집단 A: 담당 노드를 넘겼다 → **검증이 돌고**, 정규화된 UUID 가 전달된다.
    await router.contract_create(
        {"unit_id": str(unit), "member_node_id": str(node)}, db=_DB(), ctx=ctx)
    assert seen.get("asserted") == (site, node), "담당 노드 검증이 돌지 않았다"
    assert seen["create_kwargs"]["member_node_id"] == node, (
        "검증된 UUID 가 아니라 다른 값이 계약으로 넘어갔다(원문 문자열이거나 누락)"
    )
    assert not isinstance(seen["create_kwargs"]["member_node_id"], str), "UUID 로 정규화돼야 한다"

    # ── 모집단 B: 담당 노드가 없다 → 검증을 **부르지 않고**, None 이 전달된다.
    seen.clear()
    await router.contract_create({"unit_id": str(unit)}, db=_DB(), ctx=ctx)
    assert "asserted" not in seen, "담당 노드가 없는데 검증을 불렀다(불필요한 조회)"
    assert seen["create_kwargs"]["member_node_id"] is None


def test_router_wiring_is_declared_in_source() -> None:
    """★위 행위 락의 **로컬 대역** — 임포트 없이 AST 로 같은 배선을 본다.

    파이썬 3.10 개발 환경에서는 라우터를 임포트할 수 없어 위 락이 skip 된다.
    그 동안 배선이 무잠금이 되지 않도록, «검증 호출이 있고 그 결과가 계약으로 간다» 를
    소스 구조로 확인한다(문자열 grep 이 아니라 **호출 노드와 키워드 인자**).
    """
    api_root, _ = _tracked_backend_sources()
    src = (api_root / "app/api/endpoints/sales/actions.py").read_text(encoding="utf-8")

    fn = next(
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "contract_create"
    )
    calls = [c for c in ast.walk(fn) if isinstance(c, ast.Call)]

    assert any(
        isinstance(c.func, ast.Name) and c.func.id == "assert_commissionable_chain" for c in calls
    ), "`contract_create` 가 담당 노드 검증을 부르지 않는다"

    create = next(
        c for c in calls if isinstance(c.func, ast.Name) and c.func.id == "create_contract"
    )
    kw = {k.arg for k in create.keywords}
    assert "member_node_id" in kw, "검증한 담당 노드가 계약으로 전달되지 않는다"


def test_router_maps_the_two_failures_to_different_status_codes() -> None:
    """★배선 락 — 라우터가 두 예외를 **다른 HTTP 상태**로 옮기는가(AST).

    서비스가 갈라 준 것을 라우터가 다시 뭉치면 사용자 쪽에서는 안 갈린 것과 같다.
    """
    api_root, _ = _tracked_backend_sources()
    src = (api_root / "app/api/endpoints/sales/actions.py").read_text(encoding="utf-8")

    codes: dict[str, set[int]] = {}
    for handler in ast.walk(ast.parse(src)):
        if not isinstance(handler, ast.ExceptHandler) or handler.type is None:
            continue
        names = {n.id for n in ast.walk(handler.type) if isinstance(n, ast.Name)}
        target = names & {"OrgNodeNotFoundError", "OrgChainNotCommissionableError"}
        if not target:
            continue
        for call in ast.walk(handler):
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "HTTPException"
                and call.args
                and isinstance(call.args[0], ast.Constant)
            ):
                for t in target:
                    codes.setdefault(t, set()).add(call.args[0].value)

    assert codes.get("OrgNodeNotFoundError") == {404}, f"실측: {codes}"
    assert codes.get("OrgChainNotCommissionableError") == {409}, f"실측: {codes}"


# ─────────────────────────────────────────────────────────────────────────────
# 생성 층 (3) — **생산자가 하나뿐인가** (계획서 §5 «노드 생성 단일화» 의 실체)
# ─────────────────────────────────────────────────────────────────────────────


def _tracked_backend_sources() -> tuple[Path, list[str]]:
    """`git ls-files` 파생 — 새 파일이 생겨도 자동으로 모집단에 들어온다."""
    api_root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        ["git", "ls-files", "--", "app/*.py"],
        cwd=api_root, capture_output=True, text=True, check=True,
    ).stdout.split()
    return api_root, out


def _sql_literals(src: str) -> list[str]:
    """소스에서 **SQL 이 살 수 있는 문자열 리터럴만** 뽑는다(주석·독스트링 제외).

    ★저장소 규율: *"소스 검사는 주석·문자열을 배제하고 실행되는 줄만 본다."*
      여기서 «실행되는 줄» 은 곧 **`text("…")` 에 들어가는 리터럴**이다.
      주석까지 세면 *"raw INSERT 를 쓰지 마라"* 라고 **경고하는 주석**이 위반으로 신고된다 —
      가드의 위양성도 결함이고, 그러면 다음 사람이 `noqa` 로 이 락을 영구 무력화한다.
    ★독스트링도 뺀다: 이 PR 의 `create_node` 독스트링이 사고 경위를 SQL 로 적고 있다.
    """
    tree = ast.parse(src)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        c.value.lower()
        for c in ast.walk(tree)
        if isinstance(c, ast.Constant) and isinstance(c.value, str) and id(c) not in docstrings
    ]


def test_no_raw_insert_into_org_nodes_outside_the_service() -> None:
    """★★`sales_org_nodes` 에 **raw INSERT 하는 곳이 없다** — 규칙을 우회하는 생산자 금지.

    이 PR 의 결함은 «규칙 있는 생산자와 규칙 없는 생산자가 공존했다» 였다.
    위 행위 락들은 `create_node` 를 태우므로, **누군가 다시 raw INSERT 를 쓰면 전부 초록**이다.

    ★**대조군 없는 «0건» 은 근거가 아니다**(저장소 규율). 같은 조회기로
      «반드시 있어야 할 것»(`sales_org_nodes` 라는 이름 자체)을 먼저 세어, 조회기 생존을 증명한다.
    """
    api_root, tracked = _tracked_backend_sources()

    mentions: list[str] = []
    offenders: list[str] = []
    for rel in tracked:
        raw = (api_root / rel).read_text(encoding="utf-8")
        if "sales_org_nodes" not in raw:
            continue
        # ★주석·독스트링을 걷어내고 **SQL 리터럴만** 본다(위양성 차단 — 함수 독스트링 참조).
        lits = _sql_literals(raw)
        if not any("sales_org_nodes" in s for s in lits):
            continue
        mentions.append(rel)
        if any("insert into sales_org_nodes" in " ".join(s.split()) for s in lits):
            offenders.append(rel)

    # ★대조군 먼저 — 이게 비면 아래 «위반 0» 은 «파일을 못 읽었다» 와 같은 값이다.
    assert len(mentions) >= 5, f"조회기가 죽었다 — `sales_org_nodes` 언급 {len(mentions)}건"

    allowed = {"app/services/sales/org/service.py"}
    assert not (set(offenders) - allowed), (
        "조직 노드를 **생성 함수를 거치지 않고** 만드는 곳이 있다: "
        f"{sorted(set(offenders) - allowed)}\n"
        "  ★`create_node()` 를 쓰라 — 루트 규칙·위계 규칙이 거기에 있다.\n"
        "  raw INSERT 는 그 둘을 **전부 우회**하고, 그러면 수수료 RESIDUAL 이 신입에게 꽂힌다."
    )


def test_org_membership_queries_exclude_soft_deleted() -> None:
    """★소프트 삭제된 노드가 «현재 멤버» 로 세어지지 않는가 — 계획서 §5 넷째 줄의 실체.

    `active = true` 만 보면 **삭제된 노드가 active 인 채로 남아 있는 행**이 멤버로 잡힌다
    (탈퇴 처리는 `deleted_at` 을 찍고 `active` 를 안 내리는 경로가 있다).
    ⇒ `sales_org_nodes` 를 `active = true` 로 거르는 **모든** SQL 이 `deleted_at IS NULL` 도 건다.

    ★축은 **파일이 아니라 조회문**이다 — 파일 단위로 세면 한 파일에 5개 중 4개만 고쳐도 초록이다.
    """
    api_root, tracked = _tracked_backend_sources()

    checked = 0
    offenders: list[str] = []
    for rel in tracked:
        raw = (api_root / rel).read_text(encoding="utf-8")
        if "sales_org_nodes" not in raw:
            continue
        # ★한 파일의 SQL 리터럴을 이어 붙인다 — 여러 줄로 쪼갠 문자열이 **한 조회문**이기 때문.
        #   주석·독스트링은 `_sql_literals` 가 이미 걷어냈다.
        flat = " ".join(" ".join(_sql_literals(raw)).split())
        for chunk in flat.split("from sales_org_nodes")[1:]:
            head = chunk[:400]           # 그 조회문의 WHERE 절이 사는 범위
            if "active = true" not in head:
                continue
            checked += 1
            if "deleted_at is null" not in head:
                offenders.append(f"{rel} :: …{head[:120]}…")

    # ★공허 진리 가드 — 태운 조회문이 0이면 아래 단언은 아무것도 말하지 않는다.
    assert checked >= 3, f"검사 대상 조회문이 너무 적다({checked}) — 조회기 또는 축이 죽었다"
    assert not offenders, (
        "`active = true` 만 보고 **소프트 삭제를 안 거르는** 조직 조회가 있다:\n"
        + "\n".join(f"  - {o}" for o in offenders)
    )


def test_hierarchy_table_is_defined_exactly_once() -> None:
    """★★**SSOT 락(정의 수)** — 위계 서열표가 저장소에 **한 벌**인가.

    M1 의 근본은 «규칙이 두 곳에 복사됐다» 였다. 위 행위 락들은 `create_node` 만 태우므로,
    누군가 라우터에 표를 **다시 복사해도** 전부 초록이다 — 그리고 두 표가 갈리는 순간 재발한다.

    ★**임포트가 아니라 AST 로** 판정하는 이유: 라우터 모듈은 무거운 의존을 끌고 와
      개발 환경(python 3.10)에서 수집조차 안 된다. 임포트에 의존하면 이 락은
      **CI 에서만 도는 락**이 되고, 그건 재발이 로컬에서 조용해진다는 뜻이다.
      AST 는 **소스만** 보므로 어디서든 돈다.
    ★모집단은 `git ls-files` 파생이다 — 새 파일에 표를 복사해도 자동으로 들어온다.
    """
    import ast
    import subprocess
    from pathlib import Path

    api_root = Path(__file__).resolve().parents[1]
    tracked = subprocess.run(
        ["git", "ls-files", "--", "app/*.py"],
        cwd=api_root, capture_output=True, text=True, check=True,
    ).stdout.split()

    # ★공허 진리 가드 — 모집단이 비면 아래 «정의 1개» 가 «파일을 못 읽었다» 와 구별되지 않는다.
    assert len(tracked) > 100, f"백엔드 소스 수집이 비정상적으로 적다: {len(tracked)}"

    definitions: list[str] = []
    for rel in tracked:
        src = (api_root / rel).read_text(encoding="utf-8")
        # 값싼 1차 거름 — 이름이 없는 파일은 파싱하지 않는다.
        if "_ORG_RANK" not in src:
            continue
        for node in ast.walk(ast.parse(src)):
            targets = (
                node.targets if isinstance(node, ast.Assign)
                else [node.target] if isinstance(node, ast.AnnAssign) else []
            )
            if any(isinstance(t, ast.Name) and t.id == "_ORG_RANK" for t in targets):
                definitions.append(rel)

    assert definitions == ["app/services/sales/org/service.py"], (
        "위계 서열표(`_ORG_RANK`)의 정의가 서비스 층 한 곳이 아니다 — "
        "두 생산자가 서로 다른 규칙을 갖게 된다.\n"
        f"  실제 정의 위치: {definitions}\n"
        "  ★라우터는 `from app.services.sales.org.service import _ORG_RANK` 로 **가져다 쓴다**."
    )


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="라우터 모듈이 `datetime.UTC`(3.11+)를 쓰는 의존을 끌고 온다 — CI(3.12)에서 실행된다. "
           "★위 `test_hierarchy_table_is_defined_exactly_once` 가 임포트 없이 같은 축을 잠그므로 "
           "이 스킵이 무잠금을 뜻하지 않는다.",
)
async def test_router_shares_the_service_hierarchy_object() -> None:
    """★**동일성 락** — 라우터가 보는 표가 서비스 층의 **바로 그 객체**인가(사본이 아닌가).

    위 AST 락은 «정의가 하나» 를 잠그고, 이것은 «그 하나가 실제로 소비된다» 를 잠근다.
    (정의를 지우고 라우터 안에서 딕셔너리 리터럴을 인라인해도 AST 락은 초록이 될 수 있다.)
    """
    from app.api.endpoints.sales import actions as router
    from app.services.sales.org import service as svc

    assert router._ORG_RANK is svc._ORG_RANK
    # ★공허 방지 — 표가 비면 위 동일성은 참이지만 아무것도 안 지킨다.
    assert svc._ORG_RANK["AGENCY"] < svc._ORG_RANK["MEMBER"]


# ─────────────────────────────────────────────────────────────────────────────
# 정산 층 — ★**원문 `split_commission` 을 직접 태운다**(대역 폐기)
# ─────────────────────────────────────────────────────────────────────────────
#
# ★★2026-09-08 적대 리뷰 B1 — 종전엔 판정을 **재구현한 대역**(`_engine_guard`)을 태웠다.
#   그래서 «가드를 죽은 줄로 만드는» 변이가 **SURVIVED** 했다:
#
#       if not chain:  →  if not chain or str(chain[0].node_type) != "AGENCY":
#           ::VERDICT=SURVIVED
#
#   그 변이는 고아 루트를 만나면 `ev.status="SPLIT"` 로 **배분 0건인 채 조용히 반환**한다.
#   가드 줄은 **도달 불가능한 죽은 줄**이 되지만 문자열은 남아 문자열 락도 초록이었다.
#   ⇒ 락이 **판정문의 존재**만 잠그고 **그 판정이 실행되는지**는 안 잠갔다.
#   ★이 PR 이 주석에 두 번 적은 *"무언 실패 금지"* 가 정확히 그 변이로 복원되는데 아무것도
#     빨개지지 않았다. 저장소 메모리 «대리 변수를 잠그면 속성은 안 잠긴다» 의 재발이다.
#
#   ⇒ 이제 **원문 함수를 부른다.** 의존(`resolve_total`·`_active_master`·`_rules`·
#     `ancestors_path`·`_assert_pool_not_exceeded`)이 전부 모듈 전역이라 monkeypatch 로 잡힌다.


class _Ev:
    # ★멱등 조회가 클래스 속성으로 비교식을 만든다(`_Ev.contract_ext_id == cid`).
    #   `select` 는 무해화했지만 비교식 자체는 평가되므로 속성이 있어야 한다.
    contract_ext_id = None
    status = None

    def __init__(self, **kw):
        self.id = uuid.uuid4()
        self.status = None
        for k, v in kw.items():
            setattr(self, k, v)


class _Master:
    id = uuid.uuid4()


class _Contract:
    """★`id` 를 주지 않는다 — 그래야 `cid` 가 None 이 되어 멱등 조회 분기를 안 탄다.

    (그 분기는 이 락의 대상이 아니고, 태우려면 진짜 DB 가 필요하다.)
    """

    def __init__(self, member_node_id=None):
        # ★`id` 는 필요하다(원문이 `contract_ext_id=contract.id` 로 쓴다).
        #   멱등 조회는 `cid` 가 무엇을 보고 정해지는지에 달렸다 — 아래 주석 참조.
        self.id = uuid.uuid4()
        self.member_node_id = member_node_id


class _NoopSelect:
    """`select(...)` 자리를 대신하는 무해한 객체 — `.where(...)` 체인만 받는다."""

    def where(self, *_a, **_k):
        return self


class _RecordingDB:
    """`db.add` 된 것을 모아 둔다 — «배분이 실제로 생겼는가» 를 태우기 위해."""

    def __init__(self):
        self.added: list[object] = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def execute(self, *_a, **_k):
        class _R:
            def scalar_one_or_none(self): return None
            def scalars(self): return self
            def all(self): return []
            def first(self): return None
        return _R()


def _patch_engine(monkeypatch, chain: list, total=1000):
    """`split_commission` 의 모듈 전역 의존만 갈아 끼운다 — 판정 자체는 **원문**이 한다."""
    from app.services.sales.commission import engine as eng

    async def _total(*_a, **_k): return total
    async def _master(*_a, **_k): return _Master()
    async def _pool(*_a, **_k): return None
    async def _anc(*_a, **_k): return chain
    async def _rules(*_a, **_k): return ({}, {})

    monkeypatch.setattr(eng, "resolve_total", _total, raising=True)
    monkeypatch.setattr(eng, "_active_master", _master, raising=True)
    monkeypatch.setattr(eng, "_assert_pool_not_exceeded", _pool, raising=True)
    monkeypatch.setattr(eng, "ancestors_path", _anc, raising=True)
    monkeypatch.setattr(eng, "_rules", _rules, raising=True)
    # ★`SalesCommissionEvent` 를 통째로 대체하면 멱등 조회의 `select(...)` 가 ArgumentError 를 낸다
    #   (SQLAlchemy 가 실제 매핑 클래스를 요구한다). **생성만** 가로챈다 —
    #   조회 경로는 원본 클래스로 가고, `cid=None` 이라 그 분기는 애초에 실행되지 않는다.
    #   ★클래스를 **상속**하면 SQLAlchemy 선언 베이스가 오염된다(SAWarning + 이름 충돌).
    #     원문은 `SalesCommissionEvent(...)` 를 **호출**만 하므로 팩토리 함수로 충분하다.
    #   ★단 멱등 조회가 `select(SalesCommissionEvent)` 를 부르므로, 그 조회가 실제 클래스를
    #     쓰도록 `select` 를 무해화한다(이 락의 대상은 **체인 판정**이지 멱등이 아니다).
    monkeypatch.setattr(eng, "SalesCommissionEvent", _Ev, raising=True)
    monkeypatch.setattr(eng, "select", lambda *_a, **_k: _NoopSelect(), raising=True)
    return eng


class _Node:
    def __init__(self, node_type: str, path: str):
        self.id = uuid.uuid4()
        self.node_type = node_type
        self.path = path


async def test_split_commission_rejects_orphan_root(monkeypatch) -> None:
    """★고아 루트(체인이 자기 자신 하나) → **원문이 거부한다.**

    ★이것이 «조용히 건너뛰기» 로 되살아나는 변이를 잡는 유일한 단언이다 —
      대역을 태우면 그 변이가 SURVIVED 한다(실증).
    """
    eng = _patch_engine(monkeypatch, [_Node("MEMBER", "mabc123")])
    db = _RecordingDB()

    with pytest.raises(ValueError) as ei:
        await eng.split_commission(db, uuid.uuid4(), _Contract(member_node_id=uuid.uuid4()))
    assert "AGENCY" in str(ei.value)


async def test_split_commission_allows_normal_chain(monkeypatch) -> None:
    """★★**반대편 모집단** — 정상 체인은 배분이 **실제로 생긴다.**

    「거부된다」만 단언하면 «모든 체인을 거부한다» 와 구별되지 않는다.
    ⇒ `RESIDUAL` Split 이 만들어지고 그 `node_id` 가 **대행사**인지까지 본다.
    """
    agency = _Node("AGENCY", "a1")
    chain = [agency, _Node("TEAM_LEADER", "a1.t1"), _Node("MEMBER", "a1.t1.m1")]
    eng = _patch_engine(monkeypatch, chain, total=1000)
    db = _RecordingDB()

    ev = await eng.split_commission(db, uuid.uuid4(), _Contract(member_node_id=uuid.uuid4()))

    assert ev is not None and ev.status == "SPLIT"
    splits = [o for o in db.added if getattr(o, "basis", None) == "RESIDUAL"]
    assert len(splits) == 1, "잔여 배분이 만들어지지 않았다"
    # ★잔여는 **대행사**에게 간다 — 이 결함이 깨뜨렸던 바로 그 성질.
    assert splits[0].node_id == agency.id
    assert splits[0].node_type == "AGENCY"
    assert int(splits[0].amount) == 1000


