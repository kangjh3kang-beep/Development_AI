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
# 정산 층 — 체인 최상위가 AGENCY 가 아니면 배분하지 않는다
# ─────────────────────────────────────────────────────────────────────────────

class _Node:
    def __init__(self, node_type: str, path: str):
        self.id = uuid.uuid4()
        self.node_type = node_type
        self.path = path


def _engine_guard(chain: list[_Node]) -> None:
    """`split_commission` 이 체인에 대해 하는 판정만 떼어 태운다.

    ★함수 전체를 태우려면 DB·계약·규칙이 필요하다. 그러면 픽스처가 무거워지고
      **판정이 아니라 픽스처를 시험**하게 된다. 판정식은 원문과 **같은 문자열**을 쓴다 —
      원문이 바뀌면 `test_engine_guard_matches_source` 가 빨개진다.
    """
    agency = chain[0]
    if str(agency.node_type) != "AGENCY":
        raise ValueError("수수료 배분 체인의 최상위가 대행사(AGENCY)가 아닙니다")


async def test_orphan_root_chain_is_rejected() -> None:
    """★고아 루트(체인이 자기 자신 하나) → **거부**."""
    with pytest.raises(ValueError) as ei:
        _engine_guard([_Node("MEMBER", "mabc123")])
    assert "AGENCY" in str(ei.value)


async def test_normal_chain_is_allowed() -> None:
    """★두 모집단 — 정상 체인(AGENCY 루트)은 **통과**한다.

    ★이 케이스가 없으면 위 단언이 «모든 체인을 거부한다» 와 구별되지 않는다.
    """
    chain = [_Node("AGENCY", "a1"), _Node("TEAM_LEADER", "a1.t1"), _Node("MEMBER", "a1.t1.m1")]
    _engine_guard(chain)  # 예외가 나면 실패


def test_engine_guard_matches_source() -> None:
    """★위 대역이 **원문과 같은 판정**인지 잠근다 — 대역만 고치고 원문을 안 고치면 무의미하다.

    (저장소 규율: 대리 변수를 잠그면 속성은 안 잠긴다. 대역을 쓰되 **원문과 결속**시킨다.)
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1]
           / "app" / "services" / "sales" / "commission" / "engine.py").read_text(encoding="utf-8")
    # 실행 줄에 그 판정이 있어야 한다(주석이 아니라).
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert 'if str(agency.node_type) != "AGENCY":' in code, "원문의 판정식이 바뀌었다 — 대역을 맞춰라"
    # 대조군: 그 판정이 쓰는 변수가 실제로 chain[0] 이다.
    assert "agency = chain[0]" in code
