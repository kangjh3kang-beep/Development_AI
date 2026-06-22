"""#5 조직도·직원 — 순수로직 회귀 안전망(라이브 DB 불필요).

본 스위트는 '라이브 PostgreSQL 행' 이 아니라, 회귀가 자주 나는 순수 분기를 고정한다:
- ltree 라벨(_label)이 항상 '영문 접두 + 영숫자'라서 숫자 시작 라벨(text2ltree 캐스트 거부)을
  만들지 않는지.
- subtree 이동 경로 재기록(rewrite_subtree_path)이 off-by-one(라벨 중복)·구분자 누락 없이
  정확한지(이동노드 자신·하위·다단계·비하위 무변경).
- team_overview 응답계약(TeamOverviewResponse) + 집계/로스터/정렬이 가짜 DB 로 정합한지.
- staff_overview 응답계약(StaffOverviewResponse) Pydantic 모델 직렬화가 프론트 키와 1:1 인지.
- SQLSTATE 분류기(_missing_object_sqlstate)가 42P01 만 흡수하고 그 외는 전파신호(None)인지.

★deploy-pending(샌드박스 불가): 실제 ltree UPDATE(text2ltree/subpath)·advisory-lock·마이그레이션
적용은 라이브 PostgreSQL 이 있어야 검증 가능하다. 여기서는 동치 파이썬 로직만 고정한다.
"""
from __future__ import annotations

import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.api.endpoints.sales import actions as sales_actions  # noqa: E402
from app.services.sales.org import service as org_service  # noqa: E402
from app.services.sales.org.overview import (  # noqa: E402
    TeamOverviewResponse,
    TeamRosterItem,
    TeamTotals,
    _missing_object_sqlstate,
    team_overview,
)


# ──────────────────────────────────────────────────────────────────────────────
# (a) ltree 라벨 — 항상 영문 접두 + 영숫자(숫자 시작 라벨 방지).
# ──────────────────────────────────────────────────────────────────────────────
def test_label_starts_with_alpha_prefix():
    """_label 은 node_type[:3].lower() 영문 접두를 강제 → 숫자 시작 라벨 불가."""
    for ntype in ("MEMBER", "TEAM_LEADER", "GM_DIRECTOR", "DIRECTOR", "AGENCY", "SUBAGENCY"):
        label = org_service._label(ntype, uuid.uuid4())
        assert label[0].isalpha(), f"라벨 첫 글자는 영문이어야 함: {label}"
        # ltree 라벨 허용문자(영숫자·언더스코어)만 포함하는지.
        assert all(c.isalnum() or c == "_" for c in label), f"ltree 허용문자 위반: {label}"


def test_label_unique_per_node():
    """노드 id 가 다르면 라벨도 다르다(같은 부모 아래 라벨 충돌 방지)."""
    a = org_service._label("MEMBER", uuid.uuid4())
    b = org_service._label("MEMBER", uuid.uuid4())
    assert a != b


# ──────────────────────────────────────────────────────────────────────────────
# (b) subtree 이동 경로 재기록 — off-by-one(라벨 중복)·구분자 누락 회귀 고정.
# ──────────────────────────────────────────────────────────────────────────────
def test_move_rewrites_node_itself():
    """이동노드 자신: a.b.c 를 x.y 아래로 → x.y.c (라벨 중복 없음)."""
    assert org_service.rewrite_subtree_path("a.b.c", "x.y", "a.b.c") == "x.y.c"


def test_move_rewrites_descendant():
    """하위 노드: a.b.c.d 를 (c 가 x.y 아래로 이동) → x.y.c.d (구분자 유지)."""
    assert org_service.rewrite_subtree_path("a.b.c", "x.y", "a.b.c.d") == "x.y.c.d"


def test_move_rewrites_deep_descendant():
    """다단계 하위: a.b.c.d.e → x.y.c.d.e (전 구간 보존)."""
    assert org_service.rewrite_subtree_path("a.b.c", "x.y", "a.b.c.d.e") == "x.y.c.d.e"


def test_move_to_root_level_parent():
    """새 부모가 1단계(루트): a.b.c → r → r.c, 하위 r.c.d."""
    assert org_service.rewrite_subtree_path("a.b.c", "r", "a.b.c") == "r.c"
    assert org_service.rewrite_subtree_path("a.b.c", "r", "a.b.c.d") == "r.c.d"


def test_move_no_label_duplication_regression():
    """★회귀: 과거 버그는 x.y.c.c(라벨 중복) 를 만들었다 — 이제 절대 중복되지 않는다."""
    out = org_service.rewrite_subtree_path("a.b.c", "x.y", "a.b.c")
    assert out == "x.y.c"
    assert ".c.c" not in out


def test_move_non_descendant_unchanged():
    """old 의 하위가 아닌 경로는 무변경(WHERE path <@ :old 미해당 방어)."""
    assert org_service.rewrite_subtree_path("a.b.c", "x.y", "a.b.zzz") == "a.b.zzz"


# ──────────────────────────────────────────────────────────────────────────────
# (b2) 사이클 가드(순수함수) — 자기/하위로 이동 거부(자기참조·고아 손상 방지).
# ──────────────────────────────────────────────────────────────────────────────
def test_rewrite_rejects_move_into_self():
    """이동노드 자신을 새 부모로 지정 → ValueError(자기참조)."""
    with pytest.raises(ValueError):
        org_service.rewrite_subtree_path("a.b.c", "a.b.c", "a.b.c")


def test_rewrite_rejects_move_into_direct_child():
    """직속 하위를 새 부모로 지정(a.b.c → a.b.c.d 아래) → ValueError(고아)."""
    with pytest.raises(ValueError):
        org_service.rewrite_subtree_path("a.b.c", "a.b.c.d", "a.b.c")


def test_rewrite_rejects_move_into_deep_descendant():
    """심층 하위를 새 부모로 지정(a.b.c → a.b.c.d.e 아래) → ValueError."""
    with pytest.raises(ValueError):
        org_service.rewrite_subtree_path("a.b.c", "a.b.c.d.e", "a.b.c")


def test_is_self_or_descendant_helper():
    """사이클 판정 헬퍼(_is_self_or_descendant) 직접 고정."""
    assert org_service._is_self_or_descendant("a.b.c", "a.b.c") is True       # 자신
    assert org_service._is_self_or_descendant("a.b.c", "a.b.c.d") is True      # 하위
    assert org_service._is_self_or_descendant("a.b.c", "a.b") is False         # 조상(허용)
    assert org_service._is_self_or_descendant("a.b.c", "x.y") is False         # 무관(허용)


def test_move_single_level_node():
    """1단계 노드 자체 이동: c 를 x.y 아래로 → x.y.c."""
    assert org_service.rewrite_subtree_path("c", "x.y", "c") == "x.y.c"
    assert org_service.rewrite_subtree_path("c", "x.y", "c.d") == "x.y.c.d"


# ──────────────────────────────────────────────────────────────────────────────
# (c) SQLSTATE 분류기 — 42P01 만 흡수, 그 외는 전파신호(None).
# ──────────────────────────────────────────────────────────────────────────────
class _FakeOrig:
    def __init__(self, code):
        self.sqlstate = code


class _FakeDBError(Exception):
    def __init__(self, code):
        super().__init__(f"db error {code}")
        self.orig = _FakeOrig(code)


def test_missing_object_sqlstate_absorbs_undefined_table():
    """42P01(undefined_table) → 코드 반환(정상 0 으로 흡수 가능)."""
    assert _missing_object_sqlstate(_FakeDBError("42P01")) == "42P01"


def test_missing_object_sqlstate_propagates_real_errors():
    """권한(42501)·연결 등 실오류 → None(전파신호, 은폐 금지)."""
    assert _missing_object_sqlstate(_FakeDBError("42501")) is None
    assert _missing_object_sqlstate(ValueError("그냥 오류")) is None


# ──────────────────────────────────────────────────────────────────────────────
# (d) team_overview 응답계약 + 집계/로스터/정렬 — 가짜 DB.
# ──────────────────────────────────────────────────────────────────────────────
class _FakeNode:
    def __init__(self, node_id, node_type, display_name, user_id=None):
        self.id = node_id
        self.node_type = node_type
        self.display_name = display_name
        self.user_id = user_id


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)

    def all(self):
        return self._rows


class _OverviewFakeDB:
    """team_overview 가 실행하는 4개 쿼리(노드/계약/고객/업무일지)+세금유형을 순서대로 응답한다.

    SQLAlchemy select() 객체인지(엔티티 조회) text() 인지로 분기한다. 라이브 DB 없이
    집계·로스터·정렬·응답계약만 검증한다.
    """

    def __init__(self, nodes, contracts, customers, work_logs, tax_rows, tax_raises=None):
        self._nodes = nodes
        self._contracts = contracts        # [(node_id, count), ...]
        self._customers = customers
        self._work_logs = work_logs
        self._tax_rows = tax_rows          # [(node_id, tax_type), ...]
        self._tax_raises = tax_raises      # 예외 객체(세금유형 조회 시 raise) 또는 None
        self._agg_calls = 0

    async def execute(self, statement, params=None):
        sql = str(statement)
        # 노드 목록: select(SalesOrgNode) — FROM sales_org_nodes, GROUP BY 없음.
        if "sales_org_nodes" in sql and "group by" not in sql.lower():
            return _Result(self._nodes)
        # 세금유형: raw text(sales_commission_tax_pref).
        if "sales_commission_tax_pref" in sql:
            if self._tax_raises is not None:
                raise self._tax_raises
            return _Result(self._tax_rows)
        # 집계 3종(계약→고객→업무일지) 순서대로.
        self._agg_calls += 1
        return _Result([self._contracts, self._customers, self._work_logs][self._agg_calls - 1])


@pytest.mark.asyncio
async def test_team_overview_empty_returns_contract():
    """노드 0개 → 빈 응답계약(scope/totals/roster 기본값)."""
    db = _OverviewFakeDB([], [], [], [], [])
    out = await team_overview(db, uuid.uuid4(), org_path=None)
    assert isinstance(out, TeamOverviewResponse)
    assert out.scope == "site"
    assert out.scope_nodes == 0
    assert out.members == 0
    assert out.totals == TeamTotals()
    assert out.roster == []


@pytest.mark.asyncio
async def test_team_overview_aggregates_and_sorts():
    """집계 합산·로스터 직급 필터·계약 내림차순 정렬·세금유형 매핑을 고정한다."""
    n1, n2, n3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    nodes = [
        _FakeNode(n1, "MEMBER", "직원A", user_id=uuid.uuid4()),  # 배정됨
        _FakeNode(n2, "TEAM_LEADER", "팀장B"),                   # 미배정
        _FakeNode(n3, "AGENCY", "대행본사"),                      # 로스터 제외(직급 아님)
    ]
    contracts = [(n1, 2), (n2, 5)]
    customers = [(n1, 3)]
    work_logs = [(n2, 1)]
    tax_rows = [(n2, "VAT")]
    db = _OverviewFakeDB(nodes, contracts, customers, work_logs, tax_rows)

    out = await team_overview(db, uuid.uuid4(), org_path="x.y")
    assert out.scope == "subtree"
    assert out.scope_nodes == 3
    # 로스터엔 AGENCY 제외 → 2명(MEMBER·TEAM_LEADER).
    assert out.members == 2
    # 합계: 계약 7, 고객 3, 업무일지 1.
    assert out.totals.contracts == 7
    assert out.totals.customers == 3
    assert out.totals.work_logs == 1
    # 정렬: 계약 내림차순 → 팀장B(5) 가 먼저.
    assert [r.name for r in out.roster] == ["팀장B", "직원A"]
    # 배정여부·세금유형 매핑.
    by_name = {r.name: r for r in out.roster}
    assert by_name["직원A"].assigned is True
    assert by_name["팀장B"].assigned is False
    assert by_name["팀장B"].tax_type == "VAT"
    assert by_name["직원A"].tax_type == "WITHHOLDING"  # 미설정 기본값


@pytest.mark.asyncio
async def test_team_overview_tax_table_missing_uses_default():
    """세금유형 테이블 미존재(42P01) → 기본값 흡수(정상 0), 응답 정상."""
    n1 = uuid.uuid4()
    nodes = [_FakeNode(n1, "MEMBER", "직원A")]
    db = _OverviewFakeDB(nodes, [(n1, 1)], [], [], [], tax_raises=_FakeDBError("42P01"))
    out = await team_overview(db, uuid.uuid4(), org_path=None)
    assert out.members == 1
    assert out.roster[0].tax_type == "WITHHOLDING"


@pytest.mark.asyncio
async def test_team_overview_tax_real_error_propagates():
    """세금유형 조회 실오류(42501 권한 등) → 전파(은폐 금지)."""
    n1 = uuid.uuid4()
    nodes = [_FakeNode(n1, "MEMBER", "직원A")]
    db = _OverviewFakeDB(nodes, [(n1, 1)], [], [], [], tax_raises=_FakeDBError("42501"))
    with pytest.raises(_FakeDBError):
        await team_overview(db, uuid.uuid4(), org_path=None)


# ──────────────────────────────────────────────────────────────────────────────
# (e) 응답계약 직렬화 — 프론트 키와 1:1(드리프트 차단).
# ──────────────────────────────────────────────────────────────────────────────
def test_team_overview_response_keys_match_frontend():
    """TeamOverviewResponse 직렬화 키 = OrgTree.tsx 의 Ov 타입 키."""
    item = TeamRosterItem(node_id="n", name="이름", role="MEMBER", role_label="직원", assigned=False)
    resp = TeamOverviewResponse(scope="site", scope_nodes=1, members=1,
                                totals=TeamTotals(), roster=[item])
    d = resp.model_dump()
    assert set(d.keys()) == {"scope", "scope_nodes", "members", "totals", "roster_totals", "roster"}
    assert set(d["totals"].keys()) == {"contracts", "customers", "work_logs"}
    assert set(d["roster_totals"].keys()) == {"contracts", "customers", "work_logs"}
    assert set(d["roster"][0].keys()) == {
        "node_id", "name", "role", "role_label", "assigned",
        "contracts", "customers", "work_logs", "tax_type",
    }


def test_staff_overview_response_keys_match_frontend():
    """StaffOverviewResponse 직렬화 키 = StaffOverviewPanel.tsx 의 OverviewResponse 타입 키."""
    from app.api.endpoints.sales.market import (
        SiteStaffSummary,
        StaffOverviewResponse,
        StaffOverviewTotals,
    )

    site = SiteStaffSummary(site_id="s", site_name="현장", member_count=1,
                            contract_count=2, attendance_count=3, commission_gross=4)
    resp = StaffOverviewResponse(scope="site", site_count=1, sites=[site],
                                 totals=StaffOverviewTotals(member_count=1, contract_count=2,
                                                            attendance_count=3, commission_gross=4))
    d = resp.model_dump()
    assert set(d.keys()) == {"scope", "site_count", "sites", "totals"}
    assert set(d["sites"][0].keys()) == {
        "site_id", "site_name", "member_count", "contract_count",
        "attendance_count", "commission_gross",
    }
    assert set(d["totals"].keys()) == {
        "member_count", "contract_count", "attendance_count", "commission_gross",
    }


# ──────────────────────────────────────────────────────────────────────────────
# (f) move_subtree — 현장격리(IDOR)·사이클 거부·인접리스트 동기화(가짜 DB).
#     실제 ltree UPDATE 는 deploy-pending(라이브 PG 필요) — 여기선 '거부 분기'와
#     parent_id 동기화 같은 순수 제어흐름만 고정한다.
# ──────────────────────────────────────────────────────────────────────────────
class _MoveNode:
    def __init__(self, node_id, site_id, path):
        self.id = node_id
        self.site_id = site_id
        self.path = path
        self.parent_id = None


class _MoveFakeDB:
    """move_subtree 가 실행하는 SELECT(노드/새부모 조회: id+site_id 필터)와 UPDATE/flush 를 흉내낸다.

    SELECT 는 compile().params 에서 id_1·site_id_1 을 추출해 (id, site_id) 가 일치하는 노드만 반환
    (현장 격리 검증). text() UPDATE 는 호출만 기록하고 no-op(실제 ltree 재기록은 deploy-pending).
    ★iter-4: ① advisory-lock SELECT(pg_advisory_xact_lock)는 no-op 으로 흡수(반환값 미사용).
      ② 사유별 거부(404/403) 분류용 '무스코프 존재 probe'(site_id 없이 id 만으로 조회)는 site 무관
      매칭으로 응답한다(타 현장에 존재하면 OrgCrossSiteError, 어디에도 없으면 OrgNodeNotFoundError)."""

    def __init__(self, nodes):
        self._by_key = {(str(n.id), str(n.site_id)): n for n in nodes}
        self._by_id = {str(n.id): n for n in nodes}  # 무스코프 probe(site 무관)용.
        self.updated = False
        self.added = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        low = sql.strip().lower()
        if low.startswith("update"):
            self.updated = True
            return _Result([])
        # advisory-lock(SELECT pg_advisory_xact_lock(...)) — 직렬화용, 반환값 미사용 → no-op.
        if "pg_advisory_xact_lock" in low:
            return _Result([])
        # select(SalesOrgNode) — 컴파일 파라미터에서 id/site 추출.
        compiled = statement.compile()
        p = compiled.params
        nid = p.get("id_1")
        sid = p.get("site_id_1")
        if sid is None:
            # 무스코프 존재 probe(_raise_node_reason): site 무관, id 만으로 매칭.
            return _ScalarOneOrNone(self._by_id.get(str(nid)))
        node = self._by_key.get((str(nid), str(sid)))
        return _ScalarOneOrNone(node)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def rollback(self):
        # 엔드포인트(move_node)가 ValueError 거부 시 db.rollback() 후 403 을 던지므로 흉내낸다.
        return None

    async def commit(self):
        # 엔드포인트가 정상 이동 시 db.commit() 한다(가짜 — no-op).
        return None


class _ScalarOneOrNone:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


@pytest.mark.asyncio
async def test_move_subtree_rejects_cross_site_new_parent():
    """★IDOR: new_parent 가 타 현장 노드면 거부(ValueError) — 교차테넌트 이동 차단."""
    site_a, site_b = uuid.uuid4(), uuid.uuid4()
    node = _MoveNode(uuid.uuid4(), site_a, "a.b.c")
    other = _MoveNode(uuid.uuid4(), site_b, "x.y")  # B현장 노드
    db = _MoveFakeDB([node, other])
    with pytest.raises(ValueError):
        # 호출자 현장은 A. new_parent 는 B현장 → A 스코프 조회에서 못 찾아 거부.
        await org_service.move_subtree(db, site_a, node.id, other.id, by=None)
    assert db.updated is False  # 거부 시 UPDATE 미실행.


@pytest.mark.asyncio
async def test_move_subtree_rejects_missing_node():
    """이동할 노드가 본 현장에 없으면 거부(ValueError)."""
    site_a = uuid.uuid4()
    parent = _MoveNode(uuid.uuid4(), site_a, "x.y")
    db = _MoveFakeDB([parent])
    with pytest.raises(ValueError):
        await org_service.move_subtree(db, site_a, uuid.uuid4(), parent.id, by=None)


@pytest.mark.asyncio
async def test_move_subtree_rejects_cycle_into_descendant():
    """★사이클: 새 부모가 이동노드 하위면 거부(자기참조/고아 방지)."""
    site_a = uuid.uuid4()
    node = _MoveNode(uuid.uuid4(), site_a, "a.b.c")
    child = _MoveNode(uuid.uuid4(), site_a, "a.b.c.d")  # node 의 하위
    db = _MoveFakeDB([node, child])
    with pytest.raises(ValueError):
        await org_service.move_subtree(db, site_a, node.id, child.id, by=None)
    assert db.updated is False


@pytest.mark.asyncio
async def test_move_subtree_same_site_succeeds_and_syncs_parent():
    """같은 현장·비순환 이동은 성공: UPDATE 수행 + parent_id 인접리스트 동기화 + 이력 add."""
    site_a = uuid.uuid4()
    node = _MoveNode(uuid.uuid4(), site_a, "a.b.c")
    new_parent = _MoveNode(uuid.uuid4(), site_a, "x.y")
    db = _MoveFakeDB([node, new_parent])
    await org_service.move_subtree(db, site_a, node.id, new_parent.id, by=None)
    assert db.updated is True               # ltree 경로 UPDATE 실행.
    assert node.parent_id == new_parent.id  # 인접리스트(parent_id) 동기화.
    assert len(db.added) == 1               # MOVE 이력 1건 기록.


# ──────────────────────────────────────────────────────────────────────────────
# (g) team_overview — totals(전체 노드) vs roster_totals(로스터 행) 분리 고정.
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_team_overview_totals_vs_roster_totals_diverge():
    """본사(AGENCY) 노드에 귀속된 계약이 있으면 totals > roster_totals(행 합) — 둘 다 명시."""
    n_member, n_agency = uuid.uuid4(), uuid.uuid4()
    nodes = [
        _FakeNode(n_member, "MEMBER", "직원A"),
        _FakeNode(n_agency, "AGENCY", "대행본사"),  # 로스터 제외 직급
    ]
    # 본사 노드에 계약 4건(로스터엔 안 보이지만 totals 엔 합산됨), 직원 계약 2건.
    contracts = [(n_member, 2), (n_agency, 4)]
    db = _OverviewFakeDB(nodes, contracts, [], [], [])
    out = await team_overview(db, uuid.uuid4(), org_path=None)
    assert out.totals.contracts == 6          # 전체 노드 합(본사 포함).
    assert out.roster_totals.contracts == 2   # 로스터 행 합(직원만).
    assert out.totals.contracts > out.roster_totals.contracts


# ──────────────────────────────────────────────────────────────────────────────
# (h) DDL/인덱스 SSOT — market._ensure 와 036 마이그레이션이 같은 한 부를 소비(드리프트 차단).
# ──────────────────────────────────────────────────────────────────────────────
def test_market_ddl_ssot_shared_by_runtime_and_migration():
    """런타임 _ensure 와 036 마이그레이션이 동일한 sales_market_ddl 상수를 import 한다(byte-identical)."""
    import importlib

    from apps.api.database import sales_market_ddl

    mig = importlib.import_module(
        "apps.api.database.migrations.versions.036_sales_market_tables")
    market = importlib.import_module("app.api.endpoints.sales.market")
    # 세 모듈이 같은 객체(동일 튜플)를 참조 — 복붙 드리프트 불가능.
    assert market.TABLE_DDLS is sales_market_ddl.TABLE_DDLS
    assert market.INDEX_DDLS is sales_market_ddl.INDEX_DDLS
    assert mig.TABLE_DDLS is sales_market_ddl.TABLE_DDLS
    assert mig.INDEX_DDLS is sales_market_ddl.INDEX_DDLS
    # 정본 자체 형태(테이블 5개·인덱스 3개) 고정.
    assert len(sales_market_ddl.TABLE_DDLS) == 5
    assert len(sales_market_ddl.INDEX_DDLS) == 3
    assert all("CREATE TABLE IF NOT EXISTS" in d for d in sales_market_ddl.TABLE_DDLS)
    assert all("CREATE INDEX IF NOT EXISTS" in d for d in sales_market_ddl.INDEX_DDLS)


# ──────────────────────────────────────────────────────────────────────────────
# (i) 엔드포인트 HTTP 상태 매핑(통합) — move_node/add_node 가 입력오류·격리위반을
#     올바른 상태코드(400 입력형식 / 403 격리·권한 / 200 정상)로 돌리는지 고정한다.
#     ★iter-1 은 '서비스 계층(move_subtree)'의 거부분기만 단위테스트했고, FastAPI 엔드포인트가
#       그 ValueError 를 403 으로, 입력형식 오류를 400 으로 '매핑'하는 계약은 미검증이었다.
#       엔드포인트는 평범한 async 함수이므로, 가짜 db/ctx 로 직접 호출해 HTTPException.status_code 만
#       고정한다(라이브 DB·FastAPI 라우팅 불필요 — 정상 경로는 deploy-pending).
#       (sales_actions·HTTPException 은 파일 상단 import 블록에서 한 번에 가져온다.)
# ──────────────────────────────────────────────────────────────────────────────
class _FakeUser:
    def __init__(self, user_id):
        self.id = user_id


class _FakeCtx:
    """SalesCtx 대용 — 엔드포인트가 읽는 site_id·role·user 만 보유."""
    def __init__(self, site_id, role, user_id):
        self.site_id = site_id
        self.role = role
        self.user = _FakeUser(user_id)


class _NoopDB:
    """엔드포인트가 입력검증 단계에서 즉시 400 으로 빠지는 경로용 — DB 호출 없음(no-op)."""
    async def execute(self, *a, **k):
        raise AssertionError("입력검증 400 경로에서는 DB 를 건드리지 않아야 한다")

    async def commit(self):
        raise AssertionError("입력검증 400 경로에서는 commit 하지 않아야 한다")

    async def rollback(self):
        return None


@pytest.mark.asyncio
async def test_move_node_missing_new_parent_id_returns_400():
    """move_node body 에 new_parent_id 누락 → 400(KeyError→500 누출 방지)."""
    ctx = _FakeCtx(uuid.uuid4(), "AGENCY", uuid.uuid4())
    with pytest.raises(HTTPException) as ei:
        await sales_actions.move_node(uuid.uuid4(), {}, db=_NoopDB(), ctx=ctx)
    assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_move_node_malformed_new_parent_id_returns_400():
    """move_node new_parent_id 가 UUID 형식이 아니면 → 400(형식오류)."""
    ctx = _FakeCtx(uuid.uuid4(), "AGENCY", uuid.uuid4())
    with pytest.raises(HTTPException) as ei:
        await sales_actions.move_node(
            uuid.uuid4(), {"new_parent_id": "not-a-uuid"}, db=_NoopDB(), ctx=ctx)
    assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_move_node_cross_site_new_parent_returns_403():
    """★IDOR 회귀(엔드포인트): 타 현장 new_parent_id → 서비스 ValueError → 403 매핑.

    move_subtree 가 A현장 스코프 조회에서 B현장 노드를 못 찾아 ValueError 를 던지고,
    엔드포인트는 이를 403(격리·권한 위반)으로 매핑해야 한다(입력형식 400 과 구분)."""
    site_a, site_b = uuid.uuid4(), uuid.uuid4()
    node = _MoveNode(uuid.uuid4(), site_a, "a.b.c")
    other = _MoveNode(uuid.uuid4(), site_b, "x.y")  # B현장 노드
    db = _MoveFakeDB([node, other])
    ctx = _FakeCtx(site_a, "AGENCY", uuid.uuid4())
    with pytest.raises(HTTPException) as ei:
        # new_parent_id 가 B현장 노드 → A 스코프 조회 실패 → ValueError → 403.
        await sales_actions.move_node(node.id, {"new_parent_id": str(other.id)}, db=db, ctx=ctx)
    assert ei.value.status_code == 403
    assert db.updated is False  # 거부 시 UPDATE 미실행.


@pytest.mark.asyncio
async def test_move_node_cycle_into_descendant_returns_422():
    """★사이클 회귀(엔드포인트): 새 부모가 이동노드 하위 → OrgCycleError → 422(입력오류).

    ★iter-4: 과거엔 모든 ValueError 를 일괄 403 으로 매핑해, 사이클(자기참조 입력오류)도 격리·권한
      위반과 똑같이 403 이었다. 이제 사유별로 분리해 사이클은 422(처리가능 형식이나 의미상 불가능한
      입력), 격리는 403 으로 구분한다(정직성)."""
    site_a = uuid.uuid4()
    node = _MoveNode(uuid.uuid4(), site_a, "a.b.c")
    child = _MoveNode(uuid.uuid4(), site_a, "a.b.c.d")
    db = _MoveFakeDB([node, child])
    ctx = _FakeCtx(site_a, "AGENCY", uuid.uuid4())
    with pytest.raises(HTTPException) as ei:
        await sales_actions.move_node(node.id, {"new_parent_id": str(child.id)}, db=db, ctx=ctx)
    assert ei.value.status_code == 422
    assert db.updated is False


@pytest.mark.asyncio
async def test_add_node_missing_node_type_returns_400():
    """add_node body 에 node_type 누락 → 400(KeyError→500 누출 방지)."""
    ctx = _FakeCtx(uuid.uuid4(), "AGENCY", uuid.uuid4())
    with pytest.raises(HTTPException) as ei:
        await sales_actions.add_node({}, db=_NoopDB(), ctx=ctx)
    assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_add_node_insufficient_role_returns_403():
    """add_node 등록권한 사다리: MEMBER 가 AGENCY 노드 등록 시도 → 403(상위 직급만 등록)."""
    ctx = _FakeCtx(uuid.uuid4(), "MEMBER", uuid.uuid4())
    with pytest.raises(HTTPException) as ei:
        # AGENCY 등록은 {DEVELOPER, SUPERADMIN} 만 허용 → MEMBER 는 403.
        await sales_actions.add_node({"node_type": "AGENCY"}, db=_NoopDB(), ctx=ctx)
    assert ei.value.status_code == 403


# ──────────────────────────────────────────────────────────────────────────────
# (i2) iter-4 — DIRECTOR 권한사다리 적용·fail-closed·키셋 패리티·move_node 사유별 상태코드.
#      ★HIGH(fail-open authz): DIRECTOR 키 부재로 권한사다리가 통째로 스킵되던 우회를 막고,
#        matrix 미등재 node_type 은 '거부(403)'가 기본(fail-closed)임을 고정한다.
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_add_node_director_ladder_applies_member_rejected():
    """★fail-open 회귀: DIRECTOR 등록은 GM_DIRECTOR+ 만 허용 → MEMBER 는 403(과거엔 권한사다리 스킵).

    DIRECTOR 는 OrgTree.tsx 기본 선택값이자 실사용 경로다. 과거엔 _REGISTER_MATRIX 에 'DIRECTOR'
    키가 없어 allowed=None → 권한사다리가 통째로 스킵되고 require_role 만 남아, MEMBER 도 통과할 수
    있었다(권한 우회). 이제 DIRECTOR 키가 있어 사다리가 적용되고 MEMBER 는 403."""
    ctx = _FakeCtx(uuid.uuid4(), "MEMBER", uuid.uuid4())
    with pytest.raises(HTTPException) as ei:
        await sales_actions.add_node({"node_type": "DIRECTOR"}, db=_NoopDB(), ctx=ctx)
    assert ei.value.status_code == 403


def test_add_node_director_register_matrix_allows_gm_director():
    """권한 단조성: DIRECTOR 등록 허용집합에 GM_DIRECTOR+상위·관리자가 모두 포함된다."""
    allowed = sales_actions._REGISTER_MATRIX["DIRECTOR"]
    assert {"GM_DIRECTOR", "AGENCY", "SUBAGENCY", "DEVELOPER", "SUPERADMIN"} <= allowed
    # 하급(TEAM_LEADER/MEMBER)은 DIRECTOR 를 등록할 수 없다(상위만 등록).
    assert "TEAM_LEADER" not in allowed and "MEMBER" not in allowed
    # 단조성: DIRECTOR 는 TEAM_LEADER/MEMBER 보다 상위라 그 등록 허용집합에 포함돼야 한다.
    assert "DIRECTOR" in sales_actions._REGISTER_MATRIX["TEAM_LEADER"]
    assert "DIRECTOR" in sales_actions._REGISTER_MATRIX["MEMBER"]


@pytest.mark.asyncio
async def test_add_node_unknown_type_fail_closed_returns_403():
    """★fail-closed: _REGISTER_MATRIX 미등재 node_type(오타·미정의 직급) → 403(과거엔 fail-open 통과)."""
    # DEVELOPER(최상위)라도 미등재 직급은 거부 — '키 누락 시 통과(fail-open)'가 아님을 고정.
    ctx = _FakeCtx(uuid.uuid4(), "DEVELOPER", uuid.uuid4())
    with pytest.raises(HTTPException) as ei:
        await sales_actions.add_node({"node_type": "CEO_UNKNOWN"}, db=_NoopDB(), ctx=ctx)
    assert ei.value.status_code == 403


def test_node_type_keyset_parity_across_three_sources():
    """★드리프트 차단: 프론트 NODE_TYPES · overview._LABEL · 백엔드 _REGISTER_MATRIX 가 동일 node_type 집합.

    세 소스가 같은 직급 집합을 공유해야 하나라도 누락되면(예: DIRECTOR 부재) fail-open/오라벨/미배선이
    생긴다. 프론트 NODE_TYPES 의 value 들을 정본으로 보고, _LABEL·_REGISTER_MATRIX 키셋이 1:1 인지
    고정한다(누락 시 테스트 실패로 드리프트 차단)."""
    from app.services.sales.org.overview import _LABEL

    # 프론트 OrgTree.tsx 의 NODE_TYPES value 집합(정본). 프론트는 TS 라 파이썬에서 직접 import 불가 →
    # 화면과 동일한 6개 직급을 명시 고정한다(프론트 변경 시 이 집합도 함께 갱신해야 함을 주석화).
    frontend_node_types = {"AGENCY", "SUBAGENCY", "GM_DIRECTOR", "DIRECTOR", "TEAM_LEADER", "MEMBER"}
    assert set(_LABEL.keys()) == frontend_node_types, "overview._LABEL 키셋이 프론트 NODE_TYPES 와 불일치"
    assert set(sales_actions._REGISTER_MATRIX.keys()) == frontend_node_types, (
        "_REGISTER_MATRIX 키셋이 프론트 NODE_TYPES 와 불일치(누락 직급은 fail-closed 라 등록 불가가 됨)")


def test_node_type_label_value_parity_frontend_vs_backend():
    """★[iter-7 라벨 값 패리티] 키셋만 같고 라벨 '값'이 다르면(예: DIRECTOR=본부장 vs 이사) 같은 화면에서
    트리 배지(프론트 LABEL)와 로스터 표(백엔드 role_label=_LABEL)가 모순 표시된다(silent-pass 안티패턴).
    그래서 키셋 비교(test_node_type_keyset_parity_across_three_sources)에 더해 라벨 '값'까지 byte-동일로
    고정한다.

    백엔드 overview._LABEL 이 정본(SSOT)이며, 프론트 OrgTree.tsx 의 NODE_TYPES 라벨이 이 값과 byte-동일
    해야 한다. 프론트는 TS 라 파이썬에서 import 불가 → 화면 상수와 동일한 라벨 한 부를 여기 명시 고정한다
    (OrgTree.tsx 의 NODE_TYPES 라벨을 바꾸면 이 dict 도 함께 갱신해야 함 — 어긋나면 즉시 실패).
    프론트 OrgTree.contract.test.ts 가 같은 기대값을 프론트 쪽에서 고정한다(양쪽 협공)."""
    from app.services.sales.org.overview import _LABEL

    # 프론트 OrgTree.tsx 의 NODE_TYPES(value→label) 한 부 — 백엔드 _LABEL 과 byte-동일이어야 함.
    frontend_labels = {
        "AGENCY": "대행본사", "SUBAGENCY": "대행지사", "GM_DIRECTOR": "본부장",
        "DIRECTOR": "이사", "TEAM_LEADER": "팀장", "MEMBER": "직원",
    }
    # 각 node_type 별 프론트 라벨 == 백엔드 _LABEL[node_type] (6개 전부 1:1, byte-동일).
    for node_type, fe_label in frontend_labels.items():
        assert _LABEL[node_type] == fe_label, (
            f"라벨 값 드리프트({node_type}): backend _LABEL={_LABEL.get(node_type)!r} != frontend={fe_label!r}")
    # dict 전체가 동일(추가/누락 라벨도 잡힘).
    assert frontend_labels == _LABEL, "overview._LABEL 와 프론트 NODE_TYPES 라벨이 byte-동일해야 함(SSOT)"


@pytest.mark.asyncio
async def test_move_node_missing_node_returns_404():
    """★사유별 상태코드: 어디에도 없는 node_id(미존재) → 404(add_node 404분리와 대칭)."""
    site_a = uuid.uuid4()
    new_parent = _MoveNode(uuid.uuid4(), site_a, "x.y")
    db = _MoveFakeDB([new_parent])  # 이동할 노드는 등록 안 됨(어디에도 없음).
    ctx = _FakeCtx(site_a, "AGENCY", uuid.uuid4())
    with pytest.raises(HTTPException) as ei:
        await sales_actions.move_node(uuid.uuid4(), {"new_parent_id": str(new_parent.id)}, db=db, ctx=ctx)
    assert ei.value.status_code == 404
    assert db.updated is False


# ──────────────────────────────────────────────────────────────────────────────
# (j) create_node — 부모 조회 현장격리(IDOR)·미존재 부모 거부(iter-3).
#     parent 조회 WHERE 에 site_id+deleted_at 가 걸려 scalar_one_or_none()→None 이면 ValueError.
#     거부는 노드 구성(flush) 이전에 일어나야 한다(부분 생성 금지).
# ──────────────────────────────────────────────────────────────────────────────
class _CreateNodeFakeDB:
    """create_node 의 parent SELECT(scalar_one_or_none)+flush 를 흉내낸다.

    parent SELECT 컴파일 파라미터에서 id_1/site_id_1 을 추출해 (id, site_id) 가 일치하는 노드만
    반환(현장 격리). flush 는 node.id 가 비어 있으면 채워(라벨 생성용) no-op 한다. ValueError 거부
    경로에서는 add/flush 가 호출되지 않아야 한다(부분 생성 금지 검증)."""

    def __init__(self, parents):
        self._by_key = {(str(n.id), str(n.site_id)): n for n in parents}
        self.added = []
        self.flushes = 0

    async def execute(self, statement, params=None):
        compiled = statement.compile()
        p = compiled.params
        nid = p.get("id_1")
        sid = p.get("site_id_1")
        return _ScalarOneOrNone(self._by_key.get((str(nid), str(sid))))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushes += 1
        # 라벨 생성을 위해 첫 flush 에서 node.id 를 채운다(실 DB server_default 흉내).
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def rollback(self):
        # add_node 가 create_node ValueError 시 db.rollback() 후 404 를 던지므로 흉내낸다.
        return None

    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_create_node_rejects_cross_site_parent():
    """★IDOR: parent_id 가 타 현장 노드면 거부(ValueError) — 교차현장 path graft 차단."""
    site_a, site_b = uuid.uuid4(), uuid.uuid4()
    parent_b = _MoveNode(uuid.uuid4(), site_b, "x.y")  # B현장 부모
    db = _CreateNodeFakeDB([parent_b])
    with pytest.raises(ValueError):
        # 호출자 현장 A. parent 는 B → A 스코프 조회에서 못 찾아 거부.
        await org_service.create_node(db, site_a, "MEMBER", parent_id=parent_b.id)
    assert db.added == []      # 거부 시 노드 미생성(부분 생성 금지).
    assert db.flushes == 0


@pytest.mark.asyncio
async def test_create_node_rejects_missing_parent():
    """미존재 parent_id → ValueError(과거 scalar_one NoResultFound→500 누출 대칭화)."""
    site_a = uuid.uuid4()
    db = _CreateNodeFakeDB([])  # 어떤 부모도 없음
    with pytest.raises(ValueError):
        await org_service.create_node(db, site_a, "MEMBER", parent_id=uuid.uuid4())
    assert db.added == []
    assert db.flushes == 0


@pytest.mark.asyncio
async def test_create_node_same_site_parent_inherits_path():
    """같은 현장 부모는 정상: 자식 path = 부모.path + 라벨(현장격리 통과 경로)."""
    site_a = uuid.uuid4()
    parent = _MoveNode(uuid.uuid4(), site_a, "x.y")
    db = _CreateNodeFakeDB([parent])
    node = await org_service.create_node(db, site_a, "MEMBER", parent_id=parent.id)
    assert node.path.startswith("x.y.")   # 부모 경로 상속.
    assert node.site_id == site_a
    assert db.flushes >= 1


@pytest.mark.asyncio
async def test_add_node_cross_site_parent_returns_404():
    """★엔드포인트: 타 현장/미존재 parent_id → create_node ValueError → 404(500 누출 차단).

    node_type 누락(400)·권한부족(403)과 대칭으로, 부모 못 찾음을 404 로 명시 매핑한다."""
    site_a, site_b = uuid.uuid4(), uuid.uuid4()
    parent_b = _MoveNode(uuid.uuid4(), site_b, "x.y")
    db = _CreateNodeFakeDB([parent_b])
    ctx = _FakeCtx(site_a, "AGENCY", uuid.uuid4())
    with pytest.raises(HTTPException) as ei:
        await sales_actions.add_node(
            {"node_type": "MEMBER", "parent_id": str(parent_b.id)}, db=db, ctx=ctx)
    assert ei.value.status_code == 404
    assert db.added == []  # 거부 시 노드 미생성.


# ──────────────────────────────────────────────────────────────────────────────
# (k) descendants/ancestors_path — 현장격리(site_id) WHERE 전파 고정(iter-3).
#     모든 노드/조상 조회 쿼리가 호출자 site_id 를 파라미터로 실어야 한다(타 현장 혼입 차단).
# ──────────────────────────────────────────────────────────────────────────────
class _ParamCapturingDB:
    """실행되는 모든 select 의 컴파일 파라미터를 기록한다. 노드/조상 조회는 nodes 에서 반환.

    ancestors_path 의 첫 조회(id 로 본인 노드)와 이후 조상 조회(path=)를 같은 nodes 목록으로
    응답한다. 각 쿼리에 site_id_1 이 실리는지(=격리 WHERE 통과)를 captured 로 검증한다."""

    def __init__(self, node=None, ancestors=None):
        self._node = node              # ancestors_path 의 첫 본인 노드(scalar_one_or_none)
        self._ancestors = ancestors or []
        self.captured = []             # [params dict, ...]

    async def execute(self, statement, params=None):
        compiled = statement.compile()
        p = dict(compiled.params)
        self.captured.append(p)
        sql = str(statement).lower()
        # descendants: path <@ :p (scalars().all())
        if "<@" in sql:
            return _Result(self._ancestors)
        # ancestors_path 본인 조회(id_1 있음) vs 조상 조회(path=:p)
        if "id_1" in p:
            return _ScalarOneOrNone(self._node)
        # 조상 path 조회: 해당 sub-path 와 일치하는 노드 1개(없으면 None).
        want = p.get("p")
        match = next((n for n in self._ancestors if str(n.path) == want), None)
        return _ScalarOneOrNone(match)


@pytest.mark.asyncio
async def test_descendants_query_carries_site_id():
    """descendants 가 site_id 를 WHERE 파라미터로 실어 타 현장 혼입을 막는지 고정."""
    site_a = uuid.uuid4()
    node = _MoveNode(uuid.uuid4(), site_a, "a.b")
    db = _ParamCapturingDB(ancestors=[node])
    rows = await org_service.descendants(db, site_a, node)
    assert rows == [node]
    # 단일 조회 쿼리에 site_id_1 가 caller site_id 로 실렸는지.
    assert any(str(p.get("site_id_1")) == str(site_a) for p in db.captured)


@pytest.mark.asyncio
async def test_ancestors_path_queries_carry_site_id():
    """ancestors_path 의 본인+조상 모든 조회가 site_id 를 실어 타 현장 조상 혼입을 막는지 고정."""
    site_a = uuid.uuid4()
    root = _MoveNode(uuid.uuid4(), site_a, "a")
    leaf = _MoveNode(uuid.uuid4(), site_a, "a.b")
    db = _ParamCapturingDB(node=leaf, ancestors=[root, leaf])
    out = await org_service.ancestors_path(db, site_a, leaf.id)
    assert [n.path for n in out] == ["a", "a.b"]  # [최상위 … 본인] 순.
    # 모든 조회(본인 1 + 조상 2)에 site_id_1 가 실렸는지(어느 하나도 누락 없음).
    assert db.captured and all(str(p.get("site_id_1")) == str(site_a) for p in db.captured)


@pytest.mark.asyncio
async def test_ancestors_path_empty_node_returns_empty():
    """member_node_id 가 없으면 빈 리스트(쿼리 없이 단락)."""
    db = _ParamCapturingDB()
    assert await org_service.ancestors_path(db, uuid.uuid4(), None) == []
    assert db.captured == []


# ──────────────────────────────────────────────────────────────────────────────
# (l) market._missing_table_sqlstate — count(*) 집계는 42P01 만 흡수, 42703(컬럼누락) 전파.
#     공유 _missing_object_sqlstate(42P01+42703)와 달리, 집계 경로는 컬럼 드리프트를 은폐하지 않는다.
# ──────────────────────────────────────────────────────────────────────────────
def test_missing_table_sqlstate_absorbs_only_undefined_table():
    """42P01 → 흡수(정상 0), 42703(컬럼누락=스키마 드리프트) → 전파신호(None)."""
    from app.api.endpoints.sales.market import (
        _missing_object_sqlstate as market_missing_object,
    )
    from app.api.endpoints.sales.market import (
        _missing_table_sqlstate,
    )

    # 집계 전용 분류기: 테이블 미존재만 흡수.
    assert _missing_table_sqlstate(_FakeDBError("42P01")) == "42P01"
    # 컬럼 미존재는 집계 경로에서 '진짜 결함' → 전파(은폐 금지).
    assert _missing_table_sqlstate(_FakeDBError("42703")) is None
    assert _missing_table_sqlstate(_FakeDBError("42501")) is None
    # 대조: 공유 분류기는 42703 도 '미설치'로 흡수한다(채용연계 noop 용도) — 역할이 다름.
    assert market_missing_object(_FakeDBError("42703")) == "42703"


# ──────────────────────────────────────────────────────────────────────────────
# (m) 수수료 events 컬럼 계약(iter-6) — staff_overview 집계가 지목하는 컬럼이 실제로 존재하는지.
#     ★선재버그: market._site_staff_summary 의 수수료 집계가 'sum(e.amount)' 였으나
#       sales_commission_events 엔 base_amount 만 있고 amount 는 sales_commission_splits 의 컬럼이라,
#       테이블이 존재하는 모든 라이브 DB 에서 42703(undefined_column)→전파→staff_overview 500 이었다.
#       가짜 DB 테스트라 미적발이었으므로, ORM 모델 introspection 으로 컬럼셋을 단언해 컬럼명 드리프트를
#       차단한다(text() raw SQL 이 지목하는 컬럼명이 모델과 어긋나면 즉시 실패).
# ──────────────────────────────────────────────────────────────────────────────
def test_sales_commission_event_column_contract():
    """sales_commission_events 모델엔 base_amount 가 있고 amount 는 없어야 한다(집계 SQL 의 정본)."""
    from apps.api.database.models.sales.commission_mh_harness import (
        SalesCommissionEvent,
        SalesCommissionSplit,
    )

    event_cols = {c.name for c in SalesCommissionEvent.__table__.columns}
    split_cols = {c.name for c in SalesCommissionSplit.__table__.columns}
    # staff_overview 의 'SELECT sum(e.base_amount) FROM sales_commission_events e' 가 가리키는 컬럼.
    assert "base_amount" in event_cols, "sales_commission_events 에 base_amount 가 있어야 함(집계 베이스액)"
    # amount 는 events 가 아니라 splits 의 컬럼 — events 에 있으면 과거 잘못된 SQL 이 우연히 통과해 버린다.
    assert "amount" not in event_cols, "amount 는 events 가 아니라 splits 의 컬럼이어야 함(드리프트 차단)"
    assert "amount" in split_cols, "sales_commission_splits 에 amount 가 있어야 함(배분액)"


def test_staff_summary_commission_sql_references_base_amount():
    """★회귀: _site_staff_summary 의 수수료 집계 SQL 이 base_amount 를 쓰고 amount 를 쓰지 않는지 고정.

    소스 텍스트를 직접 검사해, 누군가 다시 sum(e.amount) 로 되돌리면(컬럼 드리프트 재도입) 즉시
    실패하게 한다(가짜 DB 가 SQL 을 실행하지 않아 못 잡는 경로를 텍스트 계약으로 보강).
    ★주석에 'sum(e.amount)' 설명 문구가 있어도 오탐하지 않도록, '#' 주석을 제거한 코드 라인만 검사한다."""
    import inspect

    from app.api.endpoints.sales.market import _site_staff_summary

    src = inspect.getsource(_site_staff_summary)
    # 코드 라인만 추출: 각 줄에서 '#' 이후(주석)를 잘라낸다(문자열 안 '#' 는 이 함수에 없어 안전).
    code_only = "\n".join(line.split("#", 1)[0] for line in src.splitlines())
    assert "sum(e.base_amount)" in code_only, "수수료 집계는 sum(e.base_amount) 여야 함(존재하는 컬럼)"
    assert "sum(e.amount)" not in code_only, "sum(e.amount) 는 없는 컬럼 — 재도입 시 라이브 DB 에서 500"
