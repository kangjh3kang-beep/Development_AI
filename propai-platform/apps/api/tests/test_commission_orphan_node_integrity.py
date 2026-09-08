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

import uuid

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
        def scalar_one_or_none(self_inner): return parent

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
            def scalar_one_or_none(self_inner): return None
            def scalars(self_inner): return self_inner
            def all(self_inner): return []
            def first(self_inner): return None
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


