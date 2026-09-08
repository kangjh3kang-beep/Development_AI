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


class _Node:
    def __init__(self, node_type="TEAM_LEADER", path="a1.t1"):
        self.id = uuid.uuid4()
        self.node_type = node_type
        self.path = path


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
