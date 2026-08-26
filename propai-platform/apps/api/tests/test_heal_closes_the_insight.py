"""자가치유가 **인사이트를 닫는가** — 성장루프 피드백 고리의 마지막 한 줄.

## 왜 필요한가 (라이브 실측 2026-08-27)

자가치유는 **돌고 있었다**: `/growth/heal-log` **520건**(최신 `2026-08-24T18:50`).
그리고 어느 인사이트에 조치했는지 **알고 있었다** — 액션 `params` 에 `insight_id` 가 실린다.

    {"action_type":"threshold_relax","service":"site_analysis",
     "params":{"insight_id":"2e86008f-…","trigger_key":"fallback_rate:site_analysis"}}

그런데 그 인사이트를 **닫는 코드가 0건**이었다:

| 재료 | 상태(수정 전) |
|---|---|
| `acted` 상태값 | `_INSIGHT_STATUSES` 에 **있음** |
| `acted` 쓰기 코드 | **0건** |
| 라이브 `status=acted` | **0건** |
| 프론트 라벨 `"조치됨"` | **실재** |

**재료가 다 있는데 한 줄이 없었다.**

## ★`acted → dismissed` 를 연 근거(이론 아님)

*"무효한 치유는 `heal_escalation` 이 잡으니 `acted` 는 종단이어도 된다"* 를 **재서 죽였다**:

    heal_escalation  open/acknowledged/dismissed/acted  →  전부 **0건**
    ★대조군 fallback_rate open = 21   ← 조회기 생존
    ★음성 zzz_not_a_type       = 0    ← 판별력
    heal 액션 total            = 520

**520건이 쌓이는 동안 에스컬레이션은 한 번도 발화하지 않았다.**
발화한 적 없는 안전망 위에 *"사람은 못 건드려도 된다"* 를 세울 수 없다.
그래서 **사람이 기계를 부정하는 방향 하나만** 연다(규율 §D-19 — 경계는 양방향으로).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.growth import healing_rules

_API = Path(__file__).resolve().parents[1]
_RULES = _API / "app" / "services" / "growth" / "healing_rules.py"
_ROUTER = _API / "app" / "routers" / "growth.py"


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeDB:
    """UPDATE 를 가로채 **어떤 SQL 이 어떤 파라미터로** 갔는지 본다.

    ★스텁이 실제 층을 우회하는지 확인했다 — `mark_insight_acted` 의 계약은
    *"`open` 인 행만 `acted` 로 바꾼다"* 이고, 그 조건은 **SQL 문자열 안에** 있다.
    그래서 SQL 본문을 단언한다(호출 여부만 보면 조건을 지워도 초록이다).
    """

    def __init__(self, *, affected: bool = True):
        self.calls: list[tuple[str, dict]] = []
        self.commits = 0
        self._affected = affected

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), dict(params or {})))
        return _FakeResult(("row-id",) if self._affected else None)

    async def commit(self):
        self.commits += 1

    async def rollback(self):  # pragma: no cover - 실패 경로 전용
        pass


def _action(insight_id: str | None = "11111111-1111-1111-1111-111111111111"):
    params: dict[str, object] = {"trigger_key": "fallback_rate:site_analysis"}
    if insight_id is not None:
        params["insight_id"] = insight_id
    return {"type": "threshold_relax", "service": "site_analysis", "params": params}


# ── ① 두 모집단: heal 성공 → 닫는다 / 미실행 → 안 닫는다 ─────────────────────


@pytest.mark.asyncio
async def test_executed_heal_closes_its_insight() -> None:
    db = _FakeDB()
    closed = await healing_rules.mark_insight_acted(db, _action(), {"executed": True})
    assert closed == 1, "실행된 치유가 인사이트를 안 닫았다"
    assert db.commits == 1
    sql = db.calls[0][0]
    assert "UPDATE platform_insights" in sql
    assert "'acted'" in sql, "acted 로 전이하지 않는다"
    # ★사람이 이미 판단한 행은 건드리지 않는다 — 조건이 SQL 안에 있어야 한다.
    assert "status = 'open'" in sql, (
        "open 조건이 없다 — acknowledged/dismissed 를 덮어쓸 수 있다"
    )


@pytest.mark.asyncio
async def test_unexecuted_heal_closes_nothing() -> None:
    """★대조 모집단 — 이게 없으면 '항상 닫는' 구현도 위 테스트로 초록이다."""
    db = _FakeDB()
    closed = await healing_rules.mark_insight_acted(db, _action(), {"executed": False})
    assert closed == 0
    assert db.calls == [], "실행되지 않은 치유가 DB 를 건드렸다"


@pytest.mark.asyncio
async def test_action_without_insight_id_closes_nothing() -> None:
    db = _FakeDB()
    assert await healing_rules.mark_insight_acted(db, _action(None), {"executed": True}) == 0
    assert db.calls == []


@pytest.mark.asyncio
async def test_already_closed_row_reports_zero() -> None:
    """이미 사람이 처리한 행이면 UPDATE 가 0행 — 그것을 1로 세면 요약이 거짓이 된다."""
    db = _FakeDB(affected=False)
    assert await healing_rules.mark_insight_acted(db, _action(), {"executed": True}) == 0


# ── ② 배선: 디스패처가 실제로 그 함수를 태우는가 ────────────────────────────


def _code(path: Path) -> str:
    src = path.read_text(encoding="utf-8")
    src = re.sub(r"^\s*#[^\n]*$", "", src, flags=re.M)  # 주석 배제
    return src


def test_dispatcher_closes_on_success_only() -> None:
    """★헬퍼가 **있는 것**과 디스패처가 **태우는 것**은 다른 명제다."""
    code = _code(_RULES)
    assert "mark_insight_acted(db, cand, result)" in code, (
        "디스패처가 mark_insight_acted 를 안 태운다 — 헬퍼만 있고 배선이 없다."
    )
    # 성공 분기 안에서만 불려야 한다.
    idx = code.find("mark_insight_acted(db, cand, result)")
    head = code[:idx]
    assert head.rstrip().endswith("+=") or 'if result.get("executed")' in head[-400:], (
        "성공 판정(`if result.get(\"executed\")`) 안에서 불리지 않는다."
    )


# ── ③④ 전이 가드: 사람이 기계를 부정할 수 있고, 전면 개방은 아니다 ──────────


def test_dismissed_may_come_from_acted() -> None:
    """③ `acted → dismissed` 가 열려야 한다(사람의 탈출구)."""
    code = _code(_ROUTER)
    m = re.search(r'if req\.status == "dismissed":\s*\n\s*allowed_from = (\[[^\]]*\])', code)
    assert m, "dismissed 전용 허용 목록이 없다 — acted 에서 못 빠져나온다."
    assert "acted" in m.group(1), f"dismissed 허용 출발 상태에 acted 가 없다: {m.group(1)}"


def test_transition_is_not_wide_open() -> None:
    """④ ★전면 개방이 아니어야 한다 — 이게 없으면 '가드를 다 열어 버린' 구현도 ③으로 초록이다."""
    code = _code(_ROUTER)
    m = re.search(r"^\s*allowed_from = (\[[^\]]*\])", code, re.M)
    assert m, "기본 허용 목록을 못 찾았다(위반 아님 — 구조가 바뀌었다)."
    base = m.group(1)
    assert "acted" not in base, (
        f"기본 전이가 acted 를 허용한다 — 기계 상태를 아무 방향으로나 되돌릴 수 있다: {base}"
    )
    assert "dismissed" not in base, f"dismissed 에서 재전이가 열렸다: {base}"
    # `acted → open` 은 어떤 분기에서도 열리면 안 된다.
    for hit in re.finditer(r"allowed_from = (\[[^\]]*\])", code):
        lst = hit.group(1)
        if "acted" in lst:
            ctx = code[max(0, hit.start() - 200): hit.start()]
            assert '== "dismissed"' in ctx, (
                f"acted 를 허용하는 분기가 dismissed 전용이 아니다: {lst}"
            )
