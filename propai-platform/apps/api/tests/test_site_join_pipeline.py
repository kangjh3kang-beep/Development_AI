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
import contextlib
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


def test_discover_does_not_read_the_tenant_column_into_the_response() -> None:
    """★발견 응답이 `organization_id` 를 **안 읽는다** — 축은 **값의 출처**다.

    ★2026-09-09 적대 리뷰 A-3 정정: 앞 판은 응답 dict 의 **키 이름** `"organization_id"` 의
      부재만 봤다. 그래서 키만 바꿔 실으면 그대로 샜다 — 실측:

          "site_id": sid,  →  "site_id": sid, "org": str(s.organization_id),
              ::VERDICT=SURVIVED

      **낱말을 잠그면 속성이 아니라 어휘를 잠근다.** 이제 «그 컬럼을 **읽는** 코드가 있는가» 를
      본다(`s.organization_id` 의 `ast.Attribute`), 이름이 무엇이든 걸린다.
    """
    fn = _fn("discover_sites")

    # 응답을 만드는 dict 안에서 읽는 속성 이름을 전부 모은다.
    attrs: set[str] = set()
    for d in ast.walk(fn):
        if isinstance(d, ast.Dict):
            for v in d.values:
                attrs |= {a.attr for a in ast.walk(v) if isinstance(a, ast.Attribute)}
    # ★공허 방지 — 정상적으로 읽는 것이 있어야 위 수집이 살아 있다는 뜻이다.
    assert {"site_name", "site_code"} <= attrs, f"응답이 읽는 속성 수집 실패: {sorted(attrs)}"
    assert "organization_id" not in attrs, (
        "발견 응답이 **어느 시행사의 현장인가**를 읽어 싣는다 — 키 이름과 무관하게 누출이다"
    )


# ═══════════════════════════════════════════════════════════════════════════
# A-2. **복원된 락 4건** — 내가 「락 무결성 반영」 커밋에서 지웠다
# ═══════════════════════════════════════════════════════════════════════════
#
# ★★2026-09-09 R2 리뷰가 짚었다: 계획서 §5 가 이름 댄 락 14개 중 **5개가 실재하지 않았다.**
#   원인은 내가 이 파일을 «head + 새 mid + tail» 로 이어 붙이며 **중간 구간을 통째로 날린** 것이다
#   (`c7f48d4f1` 에서 만들고 `7966ce7b5` 에서 삭제 — **그 커밋 제목이 「락 무결성 반영」이다**).
#
# ★**테스트 수가 15 → 16 이라 아무 신호도 없었다.** 늘어난 수가 줄어든 것을 덮었다.
#   그리고 푸시 때 삭제 가드가 발화했는데, 나는 «변경 파일이 전부 내 것인가» 만 확인하고
#   **무엇이 지워졌는지는 안 봤다.** 소유 확인과 내용 확인은 다른 축이다.


def test_reason_vocabulary_is_shared_with_the_hiring_approval() -> None:
    """★사유 어휘가 채용 승인 경로(`market.py`)에서 **온다** — 사본이면 하나가 낡는다.

    ★사본을 만들었는지 보는 방법은 «`_LINKED_REASONS` 를 임포트하는가» 다.
      이 모듈 안에서 **재정의**하면 두 승인 경로가 서로 다른 말을 하게 된다.
    """
    tree = _tree()   # 라우터가 어휘를 가져오는 쪽이다
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



class _Node:
    def __init__(self, node_type="TEAM_LEADER", path="a1.t1"):
        self.id = uuid.uuid4()
        self.node_type = node_type
        self.path = path



# ═══════════════════════════════════════════════════════════════════════════
# B. 행위 — **원문 함수를 직접 부른다** + **스텁이 쿼리를 읽는다**
# ═══════════════════════════════════════════════════════════════════════════
#
# ★★2026-09-09 적대 리뷰 A-1(BLOCKER): 앞 판의 스텁이 이랬다.
#
#       class _DB:
#           async def execute(self, *_a, **_k): return _Res()
#
#   **인자를 버린다.** 그래서 `join.py` 의 WHERE 술어 14개(현장격리·소유자·active·
#   soft-delete·node_type·정렬)가 **무엇이든 같은 답**이 나왔고, 아래 두 변이가 살아남았다:
#
#       SalesOrgNode.site_id == site_id,  삭제  → **타 현장 관리자가 이 현장 신청을 승인**
#           ::VERDICT=SURVIVED
#       node_type == "AGENCY" → "SUBAGENCY"     → **대행사 아닌 곳**에 붙어 수수료 체인 붕괴
#           ::VERDICT=SURVIVED
#
#   ⇒ 스텁이 **받은 쿼리를 컴파일해 기록**한다. 술어가 사라지면 기록에서 사라지고 단언이 깨진다.
#     («행위» 와 «질의» 는 다른 축이다 — 반환값만 보면 질의는 영원히 무잠금이다.)


class _Result:
    """SQLAlchemy Result 의 최소 대역 — 호출별로 **다른 행**을 준다."""

    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _RecordingDB:
    """★**쿼리를 읽는** 스텁. `rows` 는 «컴파일된 SQL → 행 목록» 라우터다.

    기록된 SQL(`self.sql`)에 술어가 실제로 실려 있는지를 테스트가 단언한다.
    리터럴 바인딩으로 컴파일하므로 `node_type = 'AGENCY'` 같은 **값까지** 보인다.
    """

    def __init__(self, rows=None):
        self.sql: list[str] = []
        self._rows = rows or (lambda _s: [])

    async def execute(self, stmt, params=None):
        try:
            rendered = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        except Exception:                     # noqa: BLE001 — text() 등은 그대로 문자열화
            rendered = str(stmt)
        flat = " ".join(rendered.split())
        self.sql.append(flat)
        return _Result(self._rows(flat))

    async def commit(self):
        pass

    def find(self, needle: str) -> str:
        """기록된 쿼리 중 `needle` 을 담은 첫 줄 — 없으면 명시적으로 실패시킨다."""
        for q in self.sql:
            if needle in q:
                return q
        raise AssertionError(f"{needle!r} 를 담은 쿼리가 없다. 기록: {self.sql}")


def _rows_for(*, member=None, agency=None, name=None):
    """조회 종류별로 다른 답을 주는 라우터 — 한 모집단으로 뭉개지 않는다."""
    def route(sql: str):
        if "FROM users" in sql:
            return [name] if name else []
        if "node_type" in sql and "AGENCY" in sql:
            return [agency] if agency else []
        return [member] if member else []
    return route


async def test_link_membership_scopes_every_lookup_to_the_site(monkeypatch) -> None:
    """★★**현장 격리** — 멤버십 조회가 `site_id` 로 묶이는가(리뷰 A-1 의 그 자리).

    이 술어가 사라지면 **타 현장 관리자가 이 현장 신청을 승인**할 수 있다.
    반환값만 보는 락으로는 원리적으로 못 잡는다 — 그래서 **쿼리를 본다.**
    """
    from app.services.sales.org import join as mod

    async def _create(*_a, **_k):
        pass

    monkeypatch.setattr(mod, "create_node", _create, raising=True)

    site = uuid.uuid4()
    db = _RecordingDB(_rows_for(name=("홍길동",)))
    await mod.link_membership(db, site, uuid.uuid4(), _Node())

    q = db.find("sales_org_nodes")
    assert "site_id" in q, f"멤버십 조회가 현장으로 묶이지 않는다: {q}"
    # ★SQLAlchemy 는 UUID 를 하이픈 없이 렌더한다 — **값**을 보되 표기에 기대지 않는다.
    assert (str(site) in q) or (site.hex in q), "조회가 **이 현장**이 아니라 다른 값으로 묶였다"
    assert "user_id" in q, "소유자 술어가 없다 — 남의 멤버십을 보고 판정한다"
    assert "deleted_at IS NULL" in q, "소프트 삭제된 노드를 살아 있는 멤버로 센다"


async def test_link_membership_uses_the_agency_root_when_operator_approves(monkeypatch) -> None:
    """★★**운영자 승인 분기** — 부모가 없으면 **대행사 루트**를 찾는다(그 쿼리를 본다).

    ★모듈 독스트링이 «이 분기가 없으면 조직도 없는 현장은 영원히 막힌다» 고 선언한 자리인데,
      앞 판에는 **이 분기를 태우는 테스트가 한 건도 없었다**(리뷰 A-1).
      `node_type == "AGENCY"` 를 `"SUBAGENCY"` 로 바꿔도 초록이었다 — 대행사가 아닌 곳에
      붙으면 수수료 체인이 처음부터 어긋난다.
    """
    from app.services.sales.org import join as mod

    seen: dict = {}

    async def _create(_db, site_id, node_type, parent_id=None, **kw):
        seen.update(parent_id=parent_id, node_type=node_type)

    monkeypatch.setattr(mod, "create_node", _create, raising=True)

    root = _Node("AGENCY", "a1")
    db = _RecordingDB(_rows_for(agency=root, name=("홍길동",)))
    reason = await mod.link_membership(db, uuid.uuid4(), uuid.uuid4(), None)

    assert reason == "LINKED"
    assert seen["parent_id"] == root.id, "대행사 루트가 아니라 다른 노드에 붙었다"
    q = db.find("node_type")
    assert "'AGENCY'" in q, f"루트를 **대행사로** 찾지 않는다: {q}"


async def test_link_membership_holds_when_there_is_no_parent(monkeypatch) -> None:
    """★★붙일 자리가 없으면 **고아를 만들지 않고 보류**한다 — 이 파이프라인의 돈 축.

    조용히 루트를 만들면 정산이 `chain[0]` 을 대행사로 보므로
    **수수료 RESIDUAL 전액이 신입에게** 간다. 보류는 **전용 사유**로 말한다.
    """
    from app.services.sales.org import join as mod

    created: list = []

    async def _create(*a, **kw):
        created.append((a, kw))

    monkeypatch.setattr(mod, "create_node", _create, raising=True)

    db = _RecordingDB()          # 어떤 조회도 빈 결과
    reason = await mod.link_membership(db, uuid.uuid4(), uuid.uuid4(), None)
    assert reason == "ORG_NOT_SEEDED"
    assert created == [], "★붙일 자리가 없는데 노드를 만들었다 — 고아 루트다"


async def test_link_membership_attaches_under_the_approver(monkeypatch) -> None:
    """★★**반대편 모집단** — 승인자 노드가 있으면 **그 아래**에 붙고 `LINKED` 를 낸다.

    이것이 없으면 위 단언이 «항상 보류한다» 와 구별되지 않는다(파이프라인이 죽어도 초록).
    ★부모가 **승인자**여야 수수료 체인이 승인자의 체인을 물려받는다.
    """
    from app.services.sales.org import join as mod

    seen: dict = {}

    async def _create(_db, site_id, node_type, parent_id=None, **kw):
        seen.update(site_id=site_id, node_type=node_type, parent_id=parent_id, kw=kw)

    monkeypatch.setattr(mod, "create_node", _create, raising=True)

    approver = _Node("TEAM_LEADER")
    db = _RecordingDB(_rows_for(name=("홍길동",)))
    site, applicant = uuid.uuid4(), uuid.uuid4()
    reason = await mod.link_membership(db, site, applicant, approver)

    assert reason == "LINKED"
    assert seen["node_type"] == "MEMBER"
    assert seen["parent_id"] == approver.id, "승인자 아래가 아니라 다른 곳에 붙었다"
    assert seen["kw"]["user_id"] == applicant
    assert seen["kw"]["display_name"] == "홍길동", "이름 조회 결과를 안 썼다"


async def test_link_membership_is_idempotent_for_existing_member(monkeypatch) -> None:
    """★이미 멤버면 **다시 만들지 않는다** — 중복 노드는 역할 판정을 흔든다."""
    from app.services.sales.org import join as mod

    created: list = []

    async def _create(*a, **kw):
        created.append(1)

    monkeypatch.setattr(mod, "create_node", _create, raising=True)

    db = _RecordingDB(_rows_for(member=(uuid.uuid4(),)))
    reason = await mod.link_membership(db, uuid.uuid4(), uuid.uuid4(), _Node())
    assert reason == "ALREADY_MEMBER"
    assert created == [], "이미 멤버인데 노드를 또 만들었다"


async def test_link_membership_reports_reason_when_guard_rejects(monkeypatch) -> None:
    """★`create_node` 의 가드가 거부하면 **삼키지 않고 사유로 말한다**.

    삼키고 `LINKED` 를 돌려주면 «승인됐다» 는데 조직도엔 아무도 없는 유령 상태가 된다.
    """
    from app.services.sales.org import join as mod

    async def _create(*_a, **_k):
        raise ValueError("직속 위계 위반")

    monkeypatch.setattr(mod, "create_node", _create, raising=True)

    db = _RecordingDB(_rows_for(name=("홍길동",)))
    reason = await mod.link_membership(db, uuid.uuid4(), uuid.uuid4(), _Node())
    assert reason == "ORG_NOT_SEEDED", f"가드 거부를 삼켰다(사유={reason})"


async def test_approver_resolution_two_populations() -> None:
    """★★승인 권한 — **MEMBER 는 거부되고 TEAM_LEADER 는 통과**한다(같은 실행에서)."""
    from app.services.sales.org import join as mod

    plain = type("U", (), {"id": uuid.uuid4(), "role": "user", "tenant_id": None})()

    can, parent = await mod.resolve_approver_node(
        _RecordingDB(_rows_for(member=_Node("MEMBER"))), uuid.uuid4(), plain)
    assert can is False and parent is None, "말단 직원이 승인할 수 있다"

    can, parent = await mod.resolve_approver_node(
        _RecordingDB(_rows_for(member=_Node("TEAM_LEADER"))), uuid.uuid4(), plain)
    assert can is True and parent is not None, "팀장이 승인 못 하면 파이프라인이 죽는다"
    assert parent.node_type == "TEAM_LEADER", "부모로 쓸 노드를 **함께** 돌려줘야 한다"


async def test_approver_node_is_chosen_by_authority_not_by_path() -> None:
    """★★복수 노드일 때 **권한 우선순위**로 고른다 — `path` 순이 아니다(리뷰 B-2).

    `deps_sales:41` 이 명문으로 적는다: *"한 사용자가 같은 현장에 복수의 살아있는 조직노드를
    가질 수 있다((site_id,user_id) UNIQUE 부재)."*

    ★실패 시나리오: 대행사 둘인 현장에서 `agc_00aa` 아래 **MEMBER**, `agc_ffbb` 아래
      **DIRECTOR** 인 사람. `path` 오름차순이면 MEMBER 가 먼저 나와 **정당한 DIRECTOR 가 403**.
      형제 둘(`resolve_site_membership`·`my_sites`)은 이미 `_node_priority` 로 고른다.
    """
    from app.services.sales.org import join as mod

    low = _Node("MEMBER", "agc_00aa.m1")        # path 가 **앞선다**
    high = _Node("DIRECTOR", "agc_ffbb.d1")     # 권한이 **높다**

    class _MultiDB(_RecordingDB):
        async def execute(self, stmt, params=None):
            await super().execute(stmt, params)
            return _Result([low, high])

    plain = type("U", (), {"id": uuid.uuid4(), "role": "user", "tenant_id": None})()
    can, parent = await mod.resolve_approver_node(_MultiDB(), uuid.uuid4(), plain)

    assert can is True, "★path 순으로 골라 정당한 상위 권한자를 막았다"
    assert parent is high, f"권한이 아니라 path 로 골랐다(고른 것: {parent.node_type})"


async def test_platform_operator_can_approve_without_a_node() -> None:
    """★조직도에 노드가 없는 **총괄관리자**도 승인할 수 있다(부모는 None → AGENCY 루트로).

    ★이 분기가 없으면 «조직도를 아직 안 만든 현장» 은 **아무도 승인할 수 없어** 영원히 막힌다.
    """
    from app.services.sales.org import join as mod

    admin = type("U", (), {"id": uuid.uuid4(), "role": "superadmin", "tenant_id": None})()
    can, parent = await mod.resolve_approver_node(_RecordingDB(), uuid.uuid4(), admin)
    assert can is True and parent is None


async def test_platform_role_set_comes_from_the_shared_ssot() -> None:
    """★★역할 집합을 **손으로 복사하지 않는다**(리뷰 B-3).

    앞 판은 `{"superadmin","super_admin","admin","owner","developer"}` 를 직접 적어
    **`총괄관리자`·`platform_admin`·`시행사`·`dev` 네 토큰을 떨어뜨렸다**.
    그 역할들은 `my_sites` 에서 전 현장을 보면서 승인만 403 을 받았고, 조직도가 없는 현장이면
    **아무도 승인할 수 없어 영원히 막혔다** — 이 모듈이 막겠다고 선언한 바로 그 상황이다.
    """
    from app.services.sales.org import join as mod
    from app.services.sales.org import roles as ssot

    assert frozenset(ssot.SUPERADMIN_ROLES) == mod.APPROVER_PLATFORM_ROLES
    assert frozenset(ssot.DEVELOPER_ROLES) == mod.TENANT_SCOPED_APPROVER_ROLES
    # ★공허 방지 — SSOT 자체가 비면 위 두 단언은 참이지만 아무것도 안 지킨다.
    assert {"총괄관리자", "platform_admin"} <= mod.APPROVER_PLATFORM_ROLES


async def test_developer_approves_only_inside_its_own_tenant() -> None:
    """★★**쓰기 경로의 테넌트 경계**(리뷰 B-7) — 시행사는 자기 테넌트 현장만 승인한다.

    ★형제들은 전부 **읽기**라 이 비대칭이 안 보였다. 이 모듈은 **쓰기**다 —
      승인은 타 테넌트 현장의 조직도에 제3자를 MEMBER 로 넣는 행위이고,
      그 노드가 곧 `enter_site` 의 게이트다.
    """
    from app.services.sales.org import join as mod

    mine, theirs = uuid.uuid4(), uuid.uuid4()
    dev = type("U", (), {"id": uuid.uuid4(), "role": "developer", "tenant_id": mine})()

    def _tenant(org_id):
        def route(sql: str):
            return [org_id] if "sales_sites" in sql else []
        return route

    can, _ = await mod.resolve_approver_node(_RecordingDB(_tenant(mine)), uuid.uuid4(), dev)
    assert can is True, "자기 테넌트 현장도 승인 못 한다 — 정상 사용을 막았다"

    can, _ = await mod.resolve_approver_node(_RecordingDB(_tenant(theirs)), uuid.uuid4(), dev)
    assert can is False, "★타 테넌트 현장의 조직도에 사람을 넣을 수 있다"


# C. 상태 어휘 — 코드가 내는 값이 목록 안에 있는가
# ═══════════════════════════════════════════════════════════════════════════

def test_every_emitted_status_is_declared() -> None:
    r"""★`JOIN_STATUSES` 밖의 상태를 **어디서도** 쓰지 않는가 — 프론트가 번역 못 하는 값 금지.

    ★★2026-09-09 적대 리뷰 A-4 정정. 앞 판은 정규식 `status\s*=\s*'([a-z_]+)'` 로
      **리터럴 SQL 안만** 훑었다. 그런데 결정 경로는 `SET status = :st` 로 **파라미터 바인딩**한다
      — 즉 이 파이프라인의 결정 상태 둘이 **원리적으로 스캔 밖**이었다. 대조군으로 재 봤을 때:

          declared     : approved · pending · rejected · cancelled
          scanned      : pending · cancelled
          NEVER scanned: **approved · rejected**

      그래서 `new_status = "approved" if …` 를 `"APPROVED_XX"` 로 바꿔도 초록이었다
      (`::VERDICT=SURVIVED`). DB 에 프론트가 못 읽는 값을 써도 아무것도 안 빨개진다.

    ⇒ 축을 **「상태 이름이 되는 문자열」 전부**로 넓힌다: ①리터럴 SQL 의 `status = 'x'`
      ②`status`/`new_status` 계열 변수·키워드에 대입되는 문자열 상수
      ③`"status": "x"` 형태의 응답 dict 값.
    """
    import re

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
    decl_ids = {id(c) for c in ast.walk(decl_node)} if decl_node else set()

    def _consts(node) -> set[str]:
        return {c.value for c in ast.walk(node)
                if isinstance(c, ast.Constant) and isinstance(c.value, str)
                and id(c) not in decl_ids}

    emitted: set[str] = set()

    # ① 리터럴 SQL 안의 `status = 'x'`
    for c in ast.walk(tree):
        if isinstance(c, ast.Constant) and isinstance(c.value, str) and id(c) not in decl_ids:
            emitted |= set(re.findall(r"status\s*=\s*'([a-z_]+)'", c.value))

    # ② `status` 계열 **변수**에 대입되는 상수(파라미터 바인딩 경로가 여기 산다)
    _NAMES = {"status", "new_status", "cur_status", "next_status"}
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in _NAMES for t in n.targets):
            emitted |= _consts(n.value)
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) \
                and n.target.id in _NAMES and n.value is not None:
            emitted |= _consts(n.value)

    # ③ `"status": "x"` 형태의 dict 값(응답 계약)
    for d in ast.walk(tree):
        if isinstance(d, ast.Dict):
            for k, v in zip(d.keys, d.values, strict=False):
                if isinstance(k, ast.Constant) and k.value == "status" \
                        and isinstance(v, ast.Constant) and isinstance(v.value, str):
                    if id(v) not in decl_ids:
                        emitted.add(v.value)

    # ★공허 방지 — 결정 상태 둘이 실제로 잡히는지까지 본다(앞 판이 여기서 샜다).
    assert {"approved", "rejected"} <= emitted, (
        f"결정 상태가 스캔에 안 잡힌다 — 축이 좁다. 잡힌 것: {sorted(emitted)}"
    )
    assert emitted <= declared, f"목록에 없는 상태를 쓴다: {sorted(emitted - declared)}"


def test_module_has_no_mutation_sentinel_in_head() -> None:
    """★변이 표식이 **커밋된** 소스에 실려 있지 않은가.

    ★★2026-09-09 적대 리뷰 A-5 정정. 앞 판은 git 경로를 `_API.parents[1]`(=`propai-platform`)
      기준으로 만들어 `apps/api/app/...` 를 조회했다. git 경로는 **저장소 루트 기준**이라
      `rc=128` 이 났고, 테스트는 그것을 «아직 커밋되지 않은 신규 파일» 로 읽어 **항상 skip** 했다.
      **그 skip 사유가 거짓이었다** — 파일은 커밋돼 있었다. 리뷰어는 «커밋되면 잡힌다» 로 오독한다.

    ⇒ 저장소 루트를 `git rev-parse --show-toplevel` 로 **파생**하고, 조회 실패는
      **skip 이 아니라 실패**로 만든다(조용한 초록이 이 결함의 본체였다).
    """
    sentinel = "__MUT" + "ATED__"
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=_API, capture_output=True, text=True, check=True).stdout.strip()

    for path in (_MODULE, _SVC):
        rel = str(path.relative_to(root))
        # ★대조군 먼저 — 파일이 추적되고 있음을 증명한다(아니면 아래 «표식 없음» 이 공허하다).
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                                 cwd=root, capture_output=True, text=True, check=False)
        assert tracked.returncode == 0, f"추적되지 않는 파일이다: {rel}"

        blob = subprocess.run(["git", "show", f"HEAD:{rel}"],
                              cwd=root, capture_output=True, text=True, check=False)
        assert blob.returncode == 0, f"HEAD 에서 읽지 못했다(rc={blob.returncode}): {rel}"
        assert "import" in blob.stdout, f"조회기가 내용을 못 읽는다: {rel}"   # 대조군 2
        assert sentinel not in blob.stdout, f"변이 표식이 커밋돼 있다: {rel}"


# ═══════════════════════════════════════════════════════════════════════════
# D. 현장 격리 — **조회하는 함수를 AST 로 파생해 전수로** 태운다
# ═══════════════════════════════════════════════════════════════════════════
#
# ★★2026-09-09 R2 리뷰 C-1(CRITICAL). 앞 판은 `link_membership` 에만 쿼리 락을 걸었고,
#   **정작 인가 판정을 하는 `resolve_approver_node` 는 무잠금**이었다:
#
#       SalesOrgNode.site_id == site_id  삭제        ::VERDICT=SURVIVED
#       deleted_at.is_(None) → id.isnot(None)        ::VERDICT=SURVIVED
#
#   그 함수는 `list_join_requests`(신청자 **이름·이메일** 반환)와 `decide_join_request` 의
#   403 게이트다. 술어가 사라지면 **타 현장 관리자가 이 현장 신청을 보고 승인**한다.
#
#   ★내 테스트 파일이 그 실패 시나리오를 **이름으로 적어 두고도** 형제 함수엔 안 걸었다.
#     R1 의 처방을 「지적된 함수」에만 적용한 것 — 이 저장소가 5연속 겪은 그 패턴이다.
#
# ⇒ 축을 **함수 목록이 아니라 「`SalesOrgNode` 를 조회하는 모든 함수」의 AST 파생**으로 바꾼다.
#   세 번째 함수가 생겨도 자동으로 들어온다.


def _functions_querying_org_nodes() -> list[str]:
    """`SalesOrgNode` 를 `select()` 하는 서비스 층 함수 — **파생**(손 목록 아님)."""
    tree = _tree(_SVC)
    out: list[str] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef):
            continue
        for c in ast.walk(fn):
            if (isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                    and c.func.id == "select"
                    and any(isinstance(a, ast.Name | ast.Attribute)
                            and "SalesOrgNode" in ast.unparse(a) for a in c.args)):
                out.append(fn.name)
                break
    return out


def test_org_node_query_population_is_not_empty() -> None:
    """★공허 진리 가드 — 파생이 비면 아래 전수 단언이 «0개를 검사» 가 된다."""
    fns = _functions_querying_org_nodes()
    assert len(fns) >= 2, f"조직노드를 조회하는 함수 수집이 비정상: {fns}"
    # 두 축이 **모두** 들어왔는가 — 하나만 세면 그 형제가 무잠금이 된다(R2 C-1 의 본체).
    assert {"resolve_approver_node", "link_membership"} <= set(fns), f"실측: {fns}"


@pytest.mark.parametrize("fn_name", _functions_querying_org_nodes())
async def test_every_org_node_query_is_site_scoped(fn_name: str, monkeypatch) -> None:
    """★★**전수** — 조직노드를 조회하는 **모든** 함수가 현장·소유자·soft-delete 로 묶는가.

    ★단언 대상은 **함수가 실제로 보낸 쿼리**다(소스 문자열이 아니라 컴파일된 SQL).
      술어를 지우면 기록에서 사라져 여기서 깨진다.
    """
    from app.services.sales.org import join as mod

    async def _noop(*_a, **_k):
        pass

    monkeypatch.setattr(mod, "create_node", _noop, raising=True)

    site = uuid.uuid4()
    user = type("U", (), {"id": uuid.uuid4(), "role": "user", "tenant_id": None})()
    db = _RecordingDB(_rows_for(name=("홍길동",)))

    if fn_name == "resolve_approver_node":
        await mod.resolve_approver_node(db, site, user)
    elif fn_name == "link_membership":
        await mod.link_membership(db, site, uuid.uuid4(), _Node())
    elif fn_name == "site_has_approver_nodes":
        await mod.site_has_approver_nodes(db, site)
    elif fn_name == "reload_sponsor_node":
        await mod.reload_sponsor_node(db, site, uuid.uuid4())
    elif fn_name == "resolve_sponsor_node":
        # ★sponsor 해석도 «그 현장의» 노드만 봐야 한다 — 타 현장 사람을 상위로 앉히면
        #   조상 체인이 현장을 넘고 정산이 통째로 어긋난다.
        # `FROM users` 는 사용자 id 를 주고(그래야 조직 조회까지 간다), 조직 조회는 비운다.
        db = _RecordingDB(_rows_for(name=(uuid.uuid4(),)))
        with contextlib.suppress(ValueError):
            await mod.resolve_sponsor_node(db, site, "who@example.com")
    else:  # 새로 생긴 함수 — 태우는 법을 모르면 **조용히 넘기지 않는다**
        pytest.fail(
            f"`{fn_name}` 이 조직노드를 조회하는데 이 락이 태우는 법을 모른다.\n"
            "  ★새 함수를 추가했으면 여기 분기도 함께 추가하라 — 그게 이 파생의 계약이다."
        )

    q = db.find("sales_org_nodes")
    assert "site_id" in q, f"[{fn_name}] 현장으로 묶지 않는다: {q}"
    assert (str(site) in q) or (site.hex in q), f"[{fn_name}] **이 현장**이 아니다"
    assert "deleted_at IS NULL" in q, f"[{fn_name}] 소프트 삭제된 노드를 살아 있다고 센다"
    assert "active" in q, f"[{fn_name}] 비활성 노드를 멤버로 센다"


# ═══════════════════════════════════════════════════════════════════════════
# E. 재승인 — **멱등이 「아무것도 안 함」이 되면 막다른 길이 된다**(R2 리뷰 J-1)
# ═══════════════════════════════════════════════════════════════════════════

def test_reapproval_retries_membership_instead_of_short_circuiting() -> None:
    """★★이미 `approved` 인 신청을 **다시 승인**하면 멤버십 연결을 **재시도**하는가.

    ★`ORG_NOT_SEEDED` 로 보류되면 신청은 이미 `approved` 다. 앞 판은 «같은 상태면 단락» 이라
      조직도를 시드하고 다시 승인해도 **연결이 원리적으로 다시 안 불렸다.**
      그리고 이 PR 이 그 안내를 화면에 올렸다 — «조직도를 만든 뒤 **다시 승인해 주세요**» →
      지시대로 하면 «이미 처리된 신청이라 변경된 것이 없습니다». **승인자가 갇힌다.**
      라이브 13현장 중 10현장이 조직도 미시드라 **드문 경로가 아니다.**

    ★축은 **재승인 분기의 호출**이다 — 「단락 분기가 있다」가 아니라
      **「그 분기 안에서 `link_membership` 이 불린다」**.
    """
    fn = _fn("decide_join_request")

    branch = None
    for node in ast.walk(fn):
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                and "cur_status" in ast.unparse(node.test)):
            branch = node
            break
    assert branch is not None, "멱등 단락 분기를 못 찾았다 — 축이 죽었다"

    calls = {
        c.func.id for c in ast.walk(branch)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
    }
    assert "link_membership" in calls, (
        "재승인이 멤버십 연결을 **다시 태우지 않는다** — 보류된 승인이 영원히 복구 불가다.\n"
        "  ★멱등은 「부작용 없음」이지 「아무것도 안 함」이 아니다."
    )

    # ★반대편 — **거절** 재시도는 연결을 부르지 않는다(불필요한 조회·부작용 금지).
    src = ast.unparse(branch)
    assert "not body.approve" in src, (
        "승인/거절을 가르지 않는다 — 거절 재시도에서도 멤버십 연결을 태우게 된다"
    )


# ═══════════════════════════════════════════════════════════════════════════
# F. 라우터의 술어 — 임포트 없이 **AST 로** 잠근다 (R2 리뷰 J-2)
# ═══════════════════════════════════════════════════════════════════════════
#
# ★★라우터 5문 중 4문이 **테스트 참조 0** 이었고, 리뷰 변이 2종이 생존했다:
#
#     cancel 의 `AND user_id = :u` 삭제        ::VERDICT=SURVIVED  ← **IDOR**(남의 신청 취소)
#     discover 의 soft-delete 필터 무력화       ::VERDICT=SURVIVED  ← 삭제된 현장이 목록에
#
#   라우터는 개발 환경(python 3.10)에서 임포트 자체가 불가하다(PEP 695 의존).
#   그래서 **판정은 서비스 층으로 내리는 것이 정답**이지만, 이 두 자리는 **한 문장짜리 SQL 계약**이라
#   옮길 본체가 없다 — 대신 **그 문장의 술어**를 AST 로 잠근다(주석·독스트링 제외).


def _executed_sql(fn_name: str) -> list[str]:
    """그 함수가 `text(...)` 로 실행하는 SQL — **실행 리터럴만**(독스트링 제외)."""
    fn = _fn(fn_name)
    out: list[str] = []

    def flatten(node) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            a, b = flatten(node.left), flatten(node.right)
            return None if a is None or b is None else a + b
        return None

    for call in ast.walk(fn):
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                and call.func.id == "text" and call.args):
            raw = flatten(call.args[0])
            if raw:
                out.append(" ".join(raw.split()))
    return out


def test_cancel_is_scoped_to_the_owner_and_pending() -> None:
    """★★취소는 **본인의 대기 중 신청만** 건드린다 — 소유자 술어가 빠지면 IDOR 다.

    빠지면 아무나 `request_id` 만 알면 **남의 신청을 취소**할 수 있고,
    부분 유니크 인덱스 때문에 그 사람은 **재신청도 못 하게 된다.**
    """
    stmts = [s for s in _executed_sql("cancel_join_request") if s.lower().startswith("update")]
    assert len(stmts) == 1, f"취소의 UPDATE 를 {len(stmts)}개 찾았다 — 축이 죽었다"
    sql = stmts[0].lower()
    where = sql.split(" where ", 1)
    assert len(where) == 2, f"WHERE 가 없다: {sql}"
    assert "user_id" in where[1], f"★소유자로 묶지 않는다 — 남의 신청을 취소할 수 있다: {sql}"
    assert "status = 'pending'" in where[1], "이미 처리된 신청까지 뒤집는다"
    assert "returning" in sql, "몇 행을 바꿨는지 모르면 «취소 못 함» 을 구별할 수 없다"


def test_discover_excludes_deleted_sites() -> None:
    """★삭제된 현장이 발견 목록에 뜨지 않는다 — 신청할 수 없는 곳을 권하면 안 된다.

    ★축은 **`select(SalesSite)` 의 `.where()` 인자**다(파일 grep 아님 —
      `deleted_at` 이라는 낱말은 이 파일에 여러 번 나온다).
    """
    fn = _fn("discover_sites")
    found = False
    for call in ast.walk(fn):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "where"):
            continue
        base = ast.unparse(call.func.value)
        if "SalesSite" not in base:
            continue
        found = True
        conds = " ".join(ast.unparse(a) for a in call.args)
        assert "SalesSite.deleted_at" in conds, (
            f"현장 조회가 소프트 삭제를 안 거른다: {conds}"
        )
    assert found, "`select(SalesSite).where(...)` 를 못 찾았다 — 축이 죽었다"


# ═══════════════════════════════════════════════════════════════════════════
# G. sponsor(희망 직속 상위) — **클릭 순서가 수수료 체인을 정하지 못하게** 한다
# ═══════════════════════════════════════════════════════════════════════════
#
# ★볼트 §0 조회가 짚은 누락(2026-09-09). 채택된 설계(벤치마킹 R2)가
#   *"신청 시 **희망 직속 상위 필수** + 승인·삽입 원자성"* 인데 구현에서 빠져 있었다.
#   그래서 부모가 **승인자의 노드**였고, 승인자가 여럿인 현장에서는
#   **누가 먼저 누르느냐로 신입의 조상 체인이 갈렸다** — 정산이 `chain[0]` 을 보므로
#   **수수료 귀속이 클릭 순서에 좌우된다.** 조용하다.


async def test_sponsor_beats_the_approver_as_parent(monkeypatch) -> None:
    """★★**같은 신청을 누가 승인해도 같은 자리**에 붙는다 — 두 승인자로 갈라 본다.

    ★이것이 sponsor 의 존재 이유다. 두 모집단(팀장이 승인 / 본부장이 승인)에서
      **부모가 동일**해야 한다 — 그래야 수수료 체인이 클릭 순서와 무관해진다.
    """
    from app.services.sales.org import join as mod

    seen: list = []

    async def _create(_db, _site, _type, parent_id=None, **_kw):
        seen.append(parent_id)

    monkeypatch.setattr(mod, "create_node", _create, raising=True)

    sponsor = _Node("TEAM_LEADER", "a1.t1")
    site, applicant = uuid.uuid4(), uuid.uuid4()

    for approver in (_Node("TEAM_LEADER", "a1.t9"), _Node("GM_DIRECTOR", "a1")):
        db = _RecordingDB(_rows_for(name=("홍길동",)))
        reason = await mod.link_membership(db, site, applicant, approver, sponsor_node=sponsor)
        assert reason == "LINKED"

    assert seen == [sponsor.id, sponsor.id], (
        f"승인자에 따라 부모가 달라진다 — 클릭 순서가 수수료 체인을 정한다: {seen}"
    )


async def test_without_sponsor_the_approver_still_places(monkeypatch) -> None:
    """★★**반대편 모집단** — sponsor 가 없으면(옛 신청) 승인자 노드로 붙는다.

    이것이 없으면 위 단언이 «항상 sponsor 만 본다» 와 구별되지 않고,
    컬럼 추가 이전에 만들어진 신청이 **영원히 보류**된다.
    """
    from app.services.sales.org import join as mod

    seen: list = []

    async def _create(_db, _site, _type, parent_id=None, **_kw):
        seen.append(parent_id)

    monkeypatch.setattr(mod, "create_node", _create, raising=True)

    approver = _Node("GM_DIRECTOR", "a1")
    db = _RecordingDB(_rows_for(name=("홍길동",)))
    reason = await mod.link_membership(db, uuid.uuid4(), uuid.uuid4(), approver, sponsor_node=None)
    assert reason == "LINKED"
    assert seen == [approver.id]


async def test_sponsor_must_be_able_to_have_subordinates() -> None:
    """★말단(MEMBER)을 희망 상위로 지정하면 **거부**한다 — 서열 최하위는 아래를 못 둔다."""
    from app.services.sales.org import join as mod

    db = _RecordingDB(_rows_for(name=(uuid.uuid4(),), member=_Node("MEMBER", "a1.t1.m1")))
    with pytest.raises(mod.SponsorNotEligibleError):
        await mod.resolve_sponsor_node(db, uuid.uuid4(), "member@example.com")


async def test_sponsor_outside_the_site_is_not_found() -> None:
    """★★**반대편** — 그 현장에 노드가 없으면 «못 찾음» 이다(계정 존재 여부는 안 샌다).

    ★타 현장 사람을 상위로 앉히면 조상 체인이 **현장을 넘고** 정산이 통째로 어긋난다.
    """
    from app.services.sales.org import join as mod

    db = _RecordingDB(_rows_for(name=(uuid.uuid4(),)))   # 사용자는 있고, 이 현장 노드는 없다
    with pytest.raises(mod.SponsorNotFoundError):
        await mod.resolve_sponsor_node(db, uuid.uuid4(), "outsider@example.com")


def test_sponsor_requirement_is_conditional_on_the_site_having_an_org() -> None:
    """★★sponsor 는 «조직도가 있는 현장» 에서만 필수다 — **무조건 필수는 회귀였다**.

    ★★2026-09-09 R3 리뷰 C-1. 앞 판은 `sponsor_email` 을 무조건 필수로 만들었고,
      그러자 **조직 노드가 하나도 없는 현장은 어떤 이메일을 넣어도 400** 이 됐다 —
      신청이 **원리적으로 불가능**해졌다. 그런데 같은 PR 이
      *"라이브 13현장 중 10현장이 조직도 미시드"* 라고 적는다.
      **두 문장은 동시에 참일 수 없다** — 사용자 요구(«모든 회원이 모든 현장에 신청»)를
      다수 현장에서 막은 것이다.

    ⇒ 판정은 **현장의 상태**로 갈린다. 그 갈림이 서비스 층에 있는지를 본다
      (라우터에 있으면 태울 수 없다 — 이 PR 이 스스로 선언한 원칙).
    """
    fn = _fn("prepare_join_request", _SVC)
    calls = {c.func.id for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "site_has_approver_nodes" in calls, (
        "조직도 유무를 안 본다 — 무조건 필수면 조직도 없는 현장은 신청이 불가능하다"
    )
    assert "resolve_sponsor_node" in calls, "조직도가 있는 현장에서도 sponsor 를 안 본다"


async def test_site_without_org_accepts_a_request_with_no_sponsor(monkeypatch) -> None:
    """★★**모집단 A** — 조직 노드 0인 현장은 sponsor 없이도 신청이 만들어진다(C-1 회귀 방지)."""
    from app.services.sales.org import join as mod

    async def _no_org(_db, _site):
        return False

    monkeypatch.setattr(mod, "site_has_approver_nodes", _no_org, raising=True)
    out = await mod.prepare_join_request(_RecordingDB(), uuid.uuid4(), None)
    assert out is None, "조직도 없는 현장인데 sponsor 를 요구했다 — 신청이 원리적으로 불가해진다"


async def test_site_with_org_still_requires_a_valid_sponsor(monkeypatch) -> None:
    """★★**모집단 B** — 조직도가 있으면 sponsor 를 **여전히** 요구한다.

    이것이 없으면 위 단언이 «항상 통과» 와 구별되지 않고, 클릭 순서 의존이 되살아난다.
    """
    from app.services.sales.org import join as mod

    async def _has_org(_db, _site):
        return True

    monkeypatch.setattr(mod, "site_has_approver_nodes", _has_org, raising=True)
    db = _RecordingDB()                      # users 조회가 비어 sponsor 해석 실패
    with pytest.raises(mod.SponsorNotFoundError):
        await mod.prepare_join_request(db, uuid.uuid4(), "nobody@example.com")


async def test_sponsor_failures_are_indistinguishable(monkeypatch) -> None:
    """★★실패 문구가 **갈리지 않는다** — 갈리면 계정 열거·소속·직급 오라클이 된다(R3 M-2).

    ★앞 판은 세 갈래를 서로 다른 문구로 답했고, 바로 위 주석이 «계정 존재 여부가 새지 않게
      뭉뚱그린다» 고 **없는 면역을 주장**했다. 여기서 그 속성을 직접 태운다.
    """
    from app.services.sales.org import join as mod

    msgs: set[str] = set()

    # ① 플랫폼에 없는 이메일
    with pytest.raises(ValueError) as e1:
        await mod.resolve_sponsor_node(_RecordingDB(), uuid.uuid4(), "ghost@example.com")
    msgs.add(str(e1.value))

    # ② 있으나 이 현장 구성원이 아님
    with pytest.raises(ValueError) as e2:
        await mod.resolve_sponsor_node(
            _RecordingDB(_rows_for(name=(uuid.uuid4(),))), uuid.uuid4(), "outsider@example.com")
    msgs.add(str(e2.value))

    # ③ 구성원이나 직급이 아래를 못 둠
    with pytest.raises(ValueError) as e3:
        await mod.resolve_sponsor_node(
            _RecordingDB(_rows_for(name=(uuid.uuid4(),), member=_Node("MEMBER", "a1.t1.m1"))),
            uuid.uuid4(), "member@example.com")
    msgs.add(str(e3.value))

    assert len(msgs) == 1, f"세 실패가 서로 다른 말을 한다(오라클): {msgs}"
    # ★공허 방지 — 셋 다 빈 문자열이면 위 단언이 참이지만 아무것도 안 지킨다.
    assert len(next(iter(msgs))) > 10


async def test_self_approval_is_blocked() -> None:
    """★★자기 신청을 스스로 결정할 수 없다 — **행위로** 태운다.

    ★★2026-09-09 R3 리뷰 M-1: 앞 판은 이 락이 **AST 모양**(«비교문 + raise»)만 봤다.
      그래서 `==` 를 `is` 로 바꾸자 — `str(a) is str(b)` 는 새 객체라 **항상 False** 라
      차단이 **완전히 꺼지는데** — `::VERDICT=SURVIVED` 였다.
      **존재를 잠그면 행위는 안 잠긴다.** 이제 판정 함수를 직접 부른다.
    """
    from app.services.sales.org import join as mod

    same = uuid.uuid4()
    with pytest.raises(mod.SelfApprovalError):
        mod.assert_not_self_decision(same, same)
    # ★문자열/UUID 가 섞여 들어와도 같은 사람이면 막는다(라우터는 두 형을 섞어 넘긴다).
    with pytest.raises(mod.SelfApprovalError):
        mod.assert_not_self_decision(str(same), same)

    # ★★반대편 모집단 — 남의 신청은 **통과**한다(전부 막으면 파이프라인이 죽는다).
    mod.assert_not_self_decision(uuid.uuid4(), uuid.uuid4())


def test_router_maps_self_approval_to_403() -> None:
    """★배선 — 라우터가 그 판정을 부르고 **403 으로** 옮기는가."""
    fn = _fn("decide_join_request")
    calls = {c.func.id for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "assert_not_self_decision" in calls, "자기 승인 판정을 안 부른다"

    codes = {
        c.args[0].value
        for h in ast.walk(fn) if isinstance(h, ast.ExceptHandler) and h.type is not None
        and "SelfApprovalError" in ast.unparse(h.type)
        for c in ast.walk(h)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        and c.func.id == "HTTPException" and c.args and isinstance(c.args[0], ast.Constant)
    }
    assert codes == {403}, f"자기 승인이 403 이 아니다: {codes}"



# ═══════════════════════════════════════════════════════════════════════════
# H. 락이 **사라지지 않게** — 산문이 아니라 기계 검사 (R3 리뷰 M-5)
# ═══════════════════════════════════════════════════════════════════════════

def test_no_lock_was_deleted_in_this_branch() -> None:
    """★★이 브랜치가 만든 테스트 중 **사라진 것이 없는가** — 이름 집합의 차집합.

    ★★2026-09-09. R2 가 «내가 「락 무결성」 제목의 커밋에서 락 4건을 지웠다» 를 찾았다.
      신호가 둘 있었는데 둘 다 놓쳤다 — **테스트 수 15→16**(순증이 순삭제를 덮었다)과
      **삭제 가드 발화**(파일 소유만 확인하고 무엇이 지워졌는지는 안 봤다).

      R3 의 지적: 그 재발 방지가 **주석 한 블록**뿐이다.
      *"산문은 「다음에 조심」, 락은 「다음에 불가능」"* — 그래서 기계로 만든다.

    ★축은 **개수가 아니라 이름 집합**이다. 개수는 상쇄되지만 이름은 안 된다.
    """
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=_API, capture_output=True, text=True, check=True).stdout.strip()
    base = subprocess.run(
        ["git", "merge-base", "HEAD", "origin/fix/commission-orphan-node-integrity"],
        cwd=root, capture_output=True, text=True, check=False).stdout.strip()
    if not base:
        pytest.skip("base 를 해석하지 못했다(얕은 클론 등) — CI 에서 판정한다")

    import re
    pat = re.compile(r"^(?:async )?def (test_[a-z0-9_]+)", re.M)
    watched = [
        "propai-platform/apps/api/tests/test_site_join_pipeline.py",
        "propai-platform/apps/api/tests/test_transition_atomicity.py",
    ]

    # ★**정당한 개명은 사유를 적어야 통과한다** — 「사라짐」과 「더 강한 것으로 바뀜」은 다르다.
    #   비워 두면 개명이 삭제로 오인되고, 사유 없이 넣으면 삭제가 개명으로 위장한다.
    renamed: dict[str, str] = {
        "test_discover_does_not_leak_the_tenant_identifier":
            "→ …read_the_tenant_column_into_the_response (축: 응답 키 이름 → `ast.Attribute` 값의 출처)",
        "test_module_has_no_uncommitted_mutation_sentinel":
            "→ …mutation_sentinel_in_head (git 경로 파생 + 조용한 skip 을 assert 로)",
        "test_every_status_update_is_conditional":
            "→ …every_status_transition_is_conditional_or_exempted (2파일 목록 → 도메인 파생)",
        "test_sponsor_email_is_required_on_the_request_body":
            "→ …requirement_is_conditional_on_the_site_having_an_org "
            "(무조건 필수는 조직도 없는 현장의 신청을 원리적으로 막았다 — R3 C-1)",
    }

    lost: list[str] = []
    checked = 0
    for rel in watched:
        # 이 브랜치의 **모든 커밋**에서 그 파일이 가진 적 있는 이름을 모은다.
        revs = subprocess.run(
            ["git", "rev-list", f"{base}..HEAD", "--", rel],
            cwd=root, capture_output=True, text=True, check=True).stdout.split()
        ever: set[str] = set()
        for rev in revs:
            blob = subprocess.run(["git", "show", f"{rev}:{rel}"],
                                  cwd=root, capture_output=True, text=True, check=False)
            if blob.returncode == 0:
                ever |= set(pat.findall(blob.stdout))
        if not ever:
            continue
        now = set(pat.findall((Path(root) / rel).read_text(encoding="utf-8")))
        checked += len(ever)
        lost += [f"{rel}::{n}" for n in sorted(ever - now) if n not in renamed]

    # ★공허 진리 가드 — 이력에서 이름을 하나도 못 모으면 아래 «사라진 것 0» 이 무의미하다.
    assert checked >= 10, f"이력에서 테스트 이름을 {checked}개만 모았다 — 조회기가 죽었다"
    # ★죽은 개명 기록도 실패시킨다 — 안 그러면 목록이 «면제 창고» 가 된다.
    all_now: set[str] = set()
    for rel in watched:
        all_now |= set(pat.findall((Path(root) / rel).read_text(encoding="utf-8")))
    stale = [k for k in renamed if k in all_now]
    assert not stale, f"개명했다고 적었는데 그 이름이 아직 있다: {stale}"

    assert not lost, (
        "이 브랜치에서 **락이 사라졌다** — 개명이면 이 목록에 사유를 남기고, 아니면 되살려라:\n"
        + "\n".join(f"  - {x}" for x in lost)
        + "\n  ★개수(N passed)는 순삭제를 덮는다. 이름 집합으로 봐야 보인다."
    )
