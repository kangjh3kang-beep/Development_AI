"""★상태 전이가 **원자적**인가 — 승인 경로 **전수**(축은 문 하나가 아니다).

## 왜 (2026-09-09 · 적대 리뷰 B-1)

승인 경로 둘이 전부 읽고-판정하고-**조건 없이** 썼다:

    row = SELECT status WHERE id = :i      # 읽고
    if row.status != 'pending': 409        # 판정하고
    UPDATE ... SET status WHERE id = :i    # 조건 없이 쓴다

두 승인자가 동시에 누르면 **둘 다 통과**하고 둘 다 멤버십 연결로 들어간다.
`sales_org_nodes` 에 `(site_id, user_id)` UNIQUE 가 **없어**(`deps_sales:41` 명문)
`create_node` 가 두 번 실행되고, 한 사람이 **두 개의 조상 체인**에 소속된다.
수수료 배분이 `chain[0]` 을 보므로 귀속이 흔들린다 — **어떤 오류도 안 난다.**

★그리고 이 락 자체가 **없었다.** B-1 을 고친 뒤 변이를 넣었더니
`::VERDICT=UNDECIDED`(기준선 rc=127 — 참조한 테스트 파일이 존재하지 않았다) 가 나왔다.
**「고쳤다」와 「고친 것을 잠갔다」는 다른 명제다.**

## 축

**문 하나가 아니라 「상태 전이를 하는 모든 곳」**이다. 실측(파생 전수)으로 전이 3건 중
원자적인 것은 1건뿐이었다 — `cancel`(정답 패턴이 같은 파일 80줄 위에 있었다).
그래서 이 파일은 **헬퍼의 행위**와 **모든 문이 그것을 쓰는가**를 함께 잠근다.
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest

from app.services.sales.transition import claim_status_transition

_API = Path(__file__).resolve().parents[1]
_DOORS = (
    "app/api/endpoints/sales/site_join.py",
    "app/api/endpoints/sales/market.py",
)


class _Res:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _DB:
    """★쿼리를 **읽는** 스텁 — 어떤 SQL 이 나갔는지가 이 락의 본체다."""

    def __init__(self, row=("ok",)):
        self.sql: list[str] = []
        self.params: list[dict] = []
        self._row = row

    async def execute(self, stmt, params=None):
        self.sql.append(" ".join(str(stmt).split()))
        self.params.append(dict(params or {}))
        return _Res(self._row)


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼의 행위
# ─────────────────────────────────────────────────────────────────────────────

async def test_transition_is_conditional_on_the_expected_status() -> None:
    """★★전이가 **읽은 상태를 조건에 싣는다**(CAS) — 이게 없으면 경쟁이 열린다."""
    db = _DB()
    ok = await claim_status_transition(
        db, "sales_site_join_requests", uuid.uuid4(),
        expected_status="pending", new_status="approved")

    assert ok is True
    sql = db.sql[0]
    assert "status = :__expected" in sql, f"조건 없이 쓴다(경쟁 열림): {sql}"
    assert "RETURNING id" in sql, "몇 행을 바꿨는지 못 알면 경쟁을 감지할 수 없다"
    assert db.params[0]["__expected"] == "pending"
    assert db.params[0]["__new"] == "approved"


async def test_transition_reports_loss_when_someone_else_won() -> None:
    """★★**반대편 모집단** — 0행이면 `False`(남이 먼저 바꿨다).

    이것이 없으면 «항상 True» 와 구별되지 않는다 — 그러면 CAS 를 넣은 의미가 없다.
    """
    db = _DB(row=None)
    ok = await claim_status_transition(
        db, "job_applications", uuid.uuid4(),
        expected_status="pending", new_status="accepted")
    assert ok is False, "★남이 먼저 바꿨는데 내가 주인이라고 답했다 — 부작용이 두 번 실행된다"


async def test_extra_set_values_are_bound_not_interpolated() -> None:
    """★추가 대입절의 값은 **바인딩**된다 — 문자열 보간이면 주입 표면이 된다."""
    db = _DB()
    await claim_status_transition(
        db, "sales_site_join_requests", uuid.uuid4(),
        expected_status="pending", new_status="rejected",
        extra_set=", decided_by = :by", params={"by": "u-1"})
    assert ":by" in db.sql[0]
    assert db.params[0]["by"] == "u-1"


async def test_unknown_table_is_refused() -> None:
    """★테이블 이름은 SQL 에 **문자열로** 들어간다 — 화이트리스트 밖은 fail-closed."""
    with pytest.raises(ValueError):
        await claim_status_transition(
            _DB(), "users; DROP TABLE x", uuid.uuid4(),
            expected_status="pending", new_status="approved")


# ─────────────────────────────────────────────────────────────────────────────
# 축 — **모든 문**이 그것을 쓰는가 (파생 전수)
# ─────────────────────────────────────────────────────────────────────────────

def _status_updates(src: str) -> list[str]:
    """`UPDATE <table> SET status ...` 를 담은 **실행 문자열 리터럴**만(주석·독스트링 제외)."""
    tree = ast.parse(src)
    docs = {
        id(n.body[0].value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and n.body and isinstance(n.body[0], ast.Expr)
        and isinstance(n.body[0].value, ast.Constant)
        and isinstance(n.body[0].value.value, str)
    }
    # 이어 붙인 리터럴이 한 조회문이므로 파일 단위로 합쳐 훑는다.
    joined = " ".join(
        " ".join(c.value.split())
        for c in ast.walk(tree)
        if isinstance(c, ast.Constant) and isinstance(c.value, str) and id(c) not in docs
    )
    out: list[str] = []
    low = joined.lower()
    idx = 0
    while True:
        i = low.find("update ", idx)
        if i < 0:
            break
        chunk = joined[i:i + 260]
        if "set status" in " ".join(chunk.lower().split()):
            out.append(" ".join(chunk.split()))
        idx = i + 7
    return out


def test_every_status_update_is_conditional() -> None:
    """★★**축 락** — 상태를 바꾸는 SQL 은 **전부** 상태 조건 + RETURNING 을 갖는다.

    ★한 문만 고치면 형제가 그대로 남는다(실측: 전이 3건 중 **1건만** 원자적이었다).
      새 문이 생겨도 이 락이 자동으로 잡는다 — 축이 «파일» 이 아니라 «전이문» 이다.
    """
    checked = 0
    offenders: list[str] = []
    for rel in _DOORS:
        for stmt in _status_updates((_API / rel).read_text(encoding="utf-8")):
            checked += 1
            low = stmt.lower()
            if "status =" not in low.split("where", 1)[-1] or "returning" not in low:
                offenders.append(f"{rel} :: {stmt[:130]}")

    # ★공허 진리 가드 — 하나도 못 찾으면 아래 «위반 0» 은 «파서가 죽었다» 와 같다.
    assert checked >= 1, f"상태 전이문을 하나도 못 찾았다({checked}) — 축이 죽었다"
    assert not offenders, (
        "상태를 **조건 없이** 바꾸는 SQL 이 있다 — 동시 결정이 둘 다 통과한다:\n"
        + "\n".join(f"  - {o}" for o in offenders)
        + "\n  ★`claim_status_transition()` 을 써라(공용 CAS)."
    )


def test_both_decide_doors_use_the_shared_helper() -> None:
    """★배선 — 두 승인 문이 **같은 헬퍼**를 부른다(각자 구현하면 다시 갈린다)."""
    for rel in _DOORS:
        tree = ast.parse((_API / rel).read_text(encoding="utf-8"))
        calls = {
            c.func.id for c in ast.walk(tree)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        }
        assert "claim_status_transition" in calls, (
            f"{rel} 이 공용 전이 헬퍼를 쓰지 않는다 — 원자성이 문마다 갈린다"
        )
