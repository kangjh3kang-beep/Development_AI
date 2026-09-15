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
import re
import uuid
from pathlib import Path

import pytest

from app.services.sales.transition import claim_status_transition

_API = Path(__file__).resolve().parents[1]

# ★★2026-09-09 R2 리뷰 J-3: 앞 판의 축은 **손으로 적은 2파일 목록**이었는데
#   이 파일의 독스트링이 *"새 문이 생겨도 이 락이 자동으로 잡는다 — 축이 「파일」이 아니라
#   「전이문」이다"* 라고 **거짓 주장**을 했다. 실측하니 `app/` 전체에 `SET status` 가 **18파일**,
#   내 도메인(sales)만 **9곳**이었다. 2파일은 «내가 고친 곳» 이지 «결함이 사는 곳» 이 아니다.
#
# ⇒ 축을 **파생**으로 바꾼다: sales 도메인의 모든 상태 전이를 훑고,
#   CAS 형태가 아니면 **사유를 적은 면제**에 있어야 한다. 죽은 면제도 실패시킨다.
_SCOPES = ("app/api/endpoints/sales", "app/services/sales")

# ★면제 — `{경로: (비-CAS 문 개수, 사유)}`. 개수를 함께 두는 이유:
#   사유만 적으면 **그 파일에 새 전이가 생겨도 조용히 면제**된다(면제가 파일 단위로 번진다).
_EXEMPT: dict[str, tuple[int, str]] = {
    "app/api/endpoints/sales/commission_agreement.py": (
        4, "★★**실제 경쟁이 있다 — 무해가 아니라 부채다**(2026-09-09 이 락이 찾았다).\n"
           "  `sales_commission_split_agreements.status` 를 쓰는 곳이 **둘**이다: "
           ":309 `'confirmed'`(마지막 동의자가 확정) · :344 `'rejected'`(참여자 거부). "
           "둘 다 읽고-무조건-쓰기라 **동시에 오면 나중 쓴 쪽이 남는다** — 거부된 합의가 "
           "`confirmed` 로, 또는 전원 동의한 합의가 `rejected` 로 끝날 수 있다(**수수료 배분** 축).\n"
           "  ★내가 앞 판에 «측정으로 무해 확인» 이라 적었던 것은 **거짓**이다. `grep` 이 :309 를 "
           "놓쳤고 이 락의 AST 파생이 잡았다. 아래 xfail 이 수정 시 뒤집혀 이 면제를 강제 제거한다."),
    "app/api/endpoints/sales/social.py": (
        2, "친구 요청 수락(:330)/거절(:365) — 읽고-쓰기라 동시 수락·거절이 교차하면 "
           "**나중 쓴 쪽이 남는다**. 양쪽 다 권한 있는 당사자의 정당한 결정이고 금전·격리 축이 "
           "아니라 이번 범위 밖. ★**부채이지 무해 판정이 아니다.**"),
    "app/api/endpoints/sales/crm_enhance.py": (
        1, "고객 단계 변경(:341) — `c.status` 를 읽어 이력의 `stage_from` 에 적은 뒤 무조건 쓴다. "
           "동시 변경 시 **이력의 stage_from 이 낡을 수 있다**(상태 자체는 마지막 값으로 수렴). "
           "★부채 — 금전·격리 축이 아니라 이번 범위 밖."),
}

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

def _sales_sources() -> list[str]:
    """sales 도메인의 파이썬 소스 — **glob 파생**(손 목록 아님)."""
    out: list[str] = []
    for scope in _SCOPES:
        out += [str(f.relative_to(_API)) for f in (_API / scope).rglob("*.py")]
    return sorted(out)


def _statement_texts(src: str) -> list[str]:
    """SQL **한 문(statement)** 단위의 텍스트 — 인접 리터럴을 침범하지 않는다.

    ★★2026-09-09 정정. 앞 판은 파일의 **모든 문자열 리터럴을 한 줄로 이어 붙이고**
      `UPDATE` 부터 300자 창을 떴다. 그래서 창이 **다음 리터럴까지 끌어와**
      엉뚱한 `status` 를 WHERE 절로 읽었다 — 실측:

          UPDATE friendships SET status = :s ... WHERE id = :id  s id 친구요청을 찾을 수 없음
          DELETE FROM friendships WHERE id = :id AND status != 'blocked' ...
                                                    ^^^^^^ 이 status 를 내 것으로 셌다

      결과: 비-CAS **3건이 1건으로** 줄어 보였다(위양성이 아니라 **위음성** — 더 나쁘다).
      저장소가 「파서 창이 인접 표를 침범한다」로 이미 기록해 둔 형태다.

    ⇒ 경계를 **문법**으로 잡는다: `text(...)` 호출의 **인자 하나**가 한 문이다.
      암시적 이어붙이기(`"a" "b"`)는 파이썬이 이미 하나의 `Constant` 로 합쳐 주고,
      `+` 로 이은 경우만 여기서 합친다.
    """
    tree = ast.parse(src)
    out: list[str] = []

    def flatten(node) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = flatten(node.left), flatten(node.right)
            return None if left is None or right is None else left + right
        return None

    for call in ast.walk(tree):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                and call.func.id == "text" and call.args):
            continue
        raw = flatten(call.args[0])
        if raw:
            out.append(" ".join(raw.split()))
    return out


def _status_updates(src: str) -> list[str]:
    """`UPDATE <table> SET status …` **문** 전수(문 단위라 인접 침범이 없다)."""
    return [
        stmt for stmt in _statement_texts(src)
        if re.match(r"^update\s+[a-z_]+\s+set\s+status", stmt, re.I)
    ]


def _is_cas(stmt: str) -> bool:
    """전이가 **읽은 상태를 조건에 실었는가** — `WHERE … status …`."""
    low = stmt.lower()
    where = low.split(" where ", 1)
    return len(where) == 2 and "status" in where[1]


def test_transition_population_is_not_empty() -> None:
    """★공허 진리 가드 — 파생이 비면 아래 전수 단언이 «0개를 검사» 가 된다."""
    files = _sales_sources()
    assert len(files) > 30, f"sales 소스 수집이 비정상: {len(files)}"
    total = sum(len(_status_updates((_API / f).read_text(encoding="utf-8"))) for f in files)
    assert total >= 8, f"상태 전이문 수집이 비정상: {total}"


def test_every_status_transition_is_conditional_or_exempted() -> None:
    """★★**축 락** — sales 도메인의 **모든** 상태 전이가 CAS 이거나 **사유 있는 면제**다.

    ★한 문만 고치면 형제가 남는다(실측: 앞 판의 축은 손으로 적은 2파일이었고,
      실제 sales 전이는 **9곳**이었다). 새 문이 생기면 여기서 **사유를 요구**한다.
    """
    offenders: list[str] = []
    used: dict[str, int] = {}
    checked = 0

    for rel in _sales_sources():
        for stmt in _status_updates((_API / rel).read_text(encoding="utf-8")):
            checked += 1
            if _is_cas(stmt):
                continue
            used[rel] = used.get(rel, 0) + 1
            if rel not in _EXEMPT:
                offenders.append(f"{rel} :: {stmt[:130]}")

    assert checked >= 8, f"전이문을 {checked}개만 찾았다 — 파서가 죽었다"
    assert not offenders, (
        "상태를 **조건 없이** 바꾸는 전이가 면제 목록 밖에 있다:\n"
        + "\n".join(f"  - {o}" for o in offenders)
        + "\n  ★`claim_status_transition()` 을 쓰거나, 왜 안전한지 `_EXEMPT` 에 **사유와 함께** 적어라."
    )

    # ★죽은 면제도 실패시킨다 — 고쳐 놓고 면제를 안 지우면 다음 회귀가 조용히 통과한다.
    for rel, (n, _why) in _EXEMPT.items():
        assert rel in used, f"면제가 죽었다(그 파일에 비-CAS 전이가 없다): {rel}"
        assert used[rel] == n, (
            f"면제 개수가 어긋난다: {rel} 선언 {n} · 실측 {used[rel]}\n"
            "  ★새 전이가 생겼다면 그것도 안전한지 **따로 판단**하라 — 면제는 파일 단위로 번지면 안 된다."
        )


def test_both_decide_doors_use_the_shared_helper() -> None:
    """★배선 — 두 승인 문이 **같은 헬퍼**를 부른다(각자 구현하면 다시 갈린다)."""
    for rel in ("app/api/endpoints/sales/site_join.py", "app/api/endpoints/sales/market.py"):
        tree = ast.parse((_API / rel).read_text(encoding="utf-8"))
        calls = {
            c.func.id for c in ast.walk(tree)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        }
        assert "claim_status_transition" in calls, (
            f"{rel} 이 공용 전이 헬퍼를 쓰지 않는다 — 원자성이 문마다 갈린다"
        )


@pytest.mark.xfail(
    strict=True,
    reason="★부채를 **초록 안에 보이게** 둔다 — `sales_commission_split_agreements` 의 "
           "confirm(:309)/reject(:344) 이 서로 다른 값을 무조건 쓴다(수수료 배분 축의 실제 경쟁). "
           "고치면 이 xfail 이 XPASS 로 뒤집혀 **면제와 함께 지우도록 강제**한다.",
)
def test_commission_agreement_transitions_are_conditional() -> None:
    """★수수료 배분 합의의 두 전이가 CAS 인가 — **지금은 아니다**(의도적 xfail).

    ★이 자리를 «면제» 로만 두면 부채가 **주석 속에서 조용히 늙는다.**
      `xfail(strict=True)` 는 고쳐지는 순간 실패해 다음 사람에게 «면제를 지워라» 를 알린다.
    """
    rel = "app/api/endpoints/sales/commission_agreement.py"
    stmts = _status_updates((_API / rel).read_text(encoding="utf-8"))
    agreements = [x for x in stmts if "split_agreements" in x.lower()]
    assert len(agreements) == 2, f"합의 상태 전이 수집 실패: {len(agreements)}"
    assert all(_is_cas(x) for x in agreements), (
        "confirm/reject 이 조건 없이 쓴다 — 동시 결정이 서로를 덮어쓴다"
    )
