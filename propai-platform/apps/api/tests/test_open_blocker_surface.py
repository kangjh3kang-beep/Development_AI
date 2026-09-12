"""`status='open'` 한 낱말이 **여러 사실을 뭉쳤다** — 가르는 축을 표면까지 나른다.

## 왜 (라이브 실측 — ★**shipped 함수로 직접 재분류** · 2026-09-12T13:40Z · `status=open` total **679**)

★★독립 적대 리뷰 MAJOR-1 이 **초판 표를 반증**했다. 초판은 배타 버킷(609/55/5/2)으로 적고
«진짜 후보 2 ← quality_drop» 이라 했는데, `quality_drop` 은 `HANDLED_INSIGHT_TYPES` 에 **없어
후보가 될 수 없다**. 배타 분할은 **우선순위**이고 `open_blockers` 독스트링이 그것을 **거부**한다 —
***같은 PR 안에서 내 원칙을 내가 어겼다.*** ⇒ 함수가 실제로 내는 **다중코드 분포**로 바꾼다:

| shipped 함수 분류(최신 500) | 건수 |
|---|---|
| `type_not_handled` + `window_expired` | **454** |
| `type_not_handled` + `action_not_healable` + `window_expired` | **35** |
| `type_not_handled` 단독 | **8** |
| `window_expired` 단독 | **3** |
| **`[]` (= 후보 쿼리 술어 통과)** | **0** |

종전에 가를 수 있었나: `recommended_action` 으로 **사람 산출물만** 갈렸고 나머지는 **같은 모양**이었다.

★**기계는 답을 알고 있었다** — `HEAL_UNHANDLED_REASONS` 에 사유가 한 문단으로 적혀 있는데
  **프로덕션 소비처가 0**이었다(라우터·스키마·프론트 참조 0건. 대조군: 같은 방법이 프론트에서
  `blocked_by_reason` 1파일 · `GrowthDashboard` 10파일을 찾아 **조회기 생존** 확인).

★선례를 그대로 쓴다 — `#1030` 이 `blocked_total` **한 숫자**가 「막혔다」와 「막을 것이 없었다」를
  뭉갠다고 `blocked_by_reason` 으로 쪼갰다. 같은 형태가 `status='open'` 에서 **네 배 규모로**
  반복되고 있었다. 새 설계가 아니라 그 처방을 **형제 축에 적용**한 것이다.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from datetime import UTC, datetime, timedelta

import pytest

from app.routers import growth as R
from app.services.growth import healing_rules as H

_NOW = datetime(2026, 9, 12, 12, 0, 0, tzinfo=UTC)
_FRESH = _NOW - timedelta(minutes=30)       # 창 안
_STALE = _NOW - timedelta(days=8)           # 창 밖


# ── 순수 판정 ────────────────────────────────────────────────────────────────

def test_two_populations_get_different_answers() -> None:
    """★두 모집단 — **후보**와 **타입 면제**가 갈린다. 차가 0인 픽스처는 잠금이 아니다."""
    candidate = H.open_blockers(
        insight_type="fallback_rate", recommended_action="heal",
        created_at=_FRESH, now=_NOW)
    exempt = H.open_blockers(
        insight_type="latency_regression", recommended_action="heal",
        created_at=_FRESH, now=_NOW)

    # ★공허 방지 선단언 — 「후보」 쪽이 정말 빈 리스트인가(전부 차단이면 아무것도 안 잠긴다).
    assert candidate == [], f"치유 후보인데 차단 사유가 붙었다: {candidate}"
    assert exempt == [H.OPEN_BLOCKER_TYPE_NOT_HANDLED], exempt


def test_window_expiry_is_reported_separately_from_type() -> None:
    """★창 만료는 **타입 면제와 다른 사실**이다 — 같은 타입으로 둘을 가른다."""
    fresh = H.open_blockers(insight_type="fallback_rate", recommended_action="heal",
                            created_at=_FRESH, now=_NOW)
    stale = H.open_blockers(insight_type="fallback_rate", recommended_action="heal",
                            created_at=_STALE, now=_NOW)
    assert fresh == []
    assert stale == [H.OPEN_BLOCKER_WINDOW_EXPIRED], stale


def test_human_artifact_is_reported_as_action_not_healable() -> None:
    """★사람이 처리하는 산출물(PR 제안·프롬프트 후보)은 **치유 실패가 아니다**."""
    got = H.open_blockers(insight_type="improvement_proposal",
                          recommended_action="propose_pr",
                          created_at=_FRESH, now=_NOW)
    assert H.OPEN_BLOCKER_ACTION_NOT_HEALABLE in got, got


def test_unknown_created_at_is_not_treated_as_pass() -> None:
    """★**모름을 「통과」로 쓰지 않는다** — 시각이 없으면 창 판정을 할 수 없다."""
    got = H.open_blockers(insight_type="fallback_rate", recommended_action="heal",
                          created_at=None, now=_NOW)
    assert H.OPEN_BLOCKER_WINDOW_EXPIRED in got, got


def test_naive_created_at_is_not_silently_wrong() -> None:
    """★DB 는 tz 없는 값을 줄 수 있다 — 그때 **창 판정이 뒤집히면 안 된다**."""
    naive_fresh = _FRESH.replace(tzinfo=None)
    assert H.open_blockers(insight_type="fallback_rate", recommended_action="heal",
                           created_at=naive_fresh, now=_NOW) == []


# ── 닫힌 어휘 ────────────────────────────────────────────────────────────────

def test_vocabulary_is_closed_both_ways() -> None:
    """★선언 ↔ 사유표가 **양방향**으로 일치한다(죽은 코드도 실패한다)."""
    declared = {
        H.OPEN_BLOCKER_TYPE_NOT_HANDLED,
        H.OPEN_BLOCKER_ACTION_NOT_HEALABLE,
        H.OPEN_BLOCKER_WINDOW_EXPIRED,
    }
    assert declared == set(H.OPEN_BLOCKER_REASONS), (
        f"선언={sorted(declared)} 사유표={sorted(H.OPEN_BLOCKER_REASONS)}")
    assert all(v.strip() for v in H.OPEN_BLOCKER_REASONS.values()), "빈 사유가 있다"


def test_codes_are_pinned_to_their_literals() -> None:
    """★**자기 자신과 비교하는 락 금지** — 코드 값은 **API 어휘**라 계약이다.

    기계 변이(2026-09-12 · `base: origin/main → 30f0dfbc0bec`)가 이 자리를 정확히 짚었다:
    `OPEN_BLOCKER_* = "..."` 의 **문자열을 바꿔도 생존**했다. 위 테스트들이 전부 **심볼**을
    참조하니 양쪽이 함께 움직여 **원리적으로 판별 불가**였기 때문이다.
    ⇒ 소비처(프론트·대시보드)는 **문자열**로 분기한다. 값이 조용히 바뀌면 그쪽이 깨진다.
    ★형제 선례를 그대로 쓴다 — `test_handled_types_are_literals` 가 같은 이유로 리터럴을 못 박는다.
    """
    assert H.OPEN_BLOCKER_TYPE_NOT_HANDLED == "type_not_handled"
    assert H.OPEN_BLOCKER_ACTION_NOT_HEALABLE == "action_not_healable"
    assert H.OPEN_BLOCKER_WINDOW_EXPIRED == "window_expired"


def test_every_emitted_code_has_a_reason() -> None:
    """★생산자가 내는 코드를 사유표가 **전부 덮는다**(목록은 곧 상한이 된다)."""
    emitted: set[str] = set()
    for itype in ("fallback_rate", "latency_regression", "improvement_proposal"):
        for action in ("heal", "propose_pr", None):
            for created in (_FRESH, _STALE, None):
                emitted |= set(H.open_blockers(
                    insight_type=itype, recommended_action=action,
                    created_at=created, now=_NOW))
    assert emitted, "아무 코드도 안 나왔다 — 수집기가 죽었다(공허한 참 방지)"
    assert emitted <= set(H.OPEN_BLOCKER_REASONS), emitted - set(H.OPEN_BLOCKER_REASONS)


def test_type_exemption_carries_its_own_recorded_reason() -> None:
    """★`HEAL_UNHANDLED_REASONS` 의 **소비처 0** 을 해소했는가 — 그 문구가 실제로 실린다."""
    why = H.open_blocker_reason([H.OPEN_BLOCKER_TYPE_NOT_HANDLED], "latency_regression")
    recorded = H.HEAL_UNHANDLED_REASONS["latency_regression"]
    assert why == recorded, "고유 사유가 아니라 일반 문구로 떨어졌다"
    # ★목록 밖 타입도 **말할 것이 있어야** 한다(덮지 않은 코드가 빈 칸이 되면 안 된다).
    other = H.open_blocker_reason([H.OPEN_BLOCKER_TYPE_NOT_HANDLED], "zzz_unknown_type")
    assert other and other.strip(), "고유 사유가 없는 타입에서 사유가 비었다"


def test_candidate_has_no_reason() -> None:
    """★후보에는 사유가 **없다** — 없는 사실을 지어내지 않는다."""
    assert H.open_blocker_reason([], "fallback_rate") is None


# ── 상수 공유(설명과 동작이 갈리지 않는가) ──────────────────────────────────

def _fn_src(fn) -> str:
    return textwrap.dedent(inspect.getsource(fn))


def _candidate_sql_of(fn) -> str:
    """함수 안 `text(...)` 의 `platform_insights` 질의 문자열(파서로 — 주석에 안 뚫린다)."""
    for sub in ast.walk(ast.parse(_fn_src(fn))):
        if isinstance(sub, ast.Call) and getattr(sub.func, "id", None) == "text" and sub.args:
            lits = [c.value for c in ast.walk(sub.args[0])
                    if isinstance(c, ast.Constant) and isinstance(c.value, str)]
            joined = "".join(lits)
            if "platform_insights" in joined:
                return joined
    raise AssertionError("후보 조회 SQL 을 못 찾았다 — 파서가 죽었다")


def _names_in(fn) -> set[str]:
    return {n.id for n in ast.walk(ast.parse(_fn_src(fn))) if isinstance(n, ast.Name)}


def test_explanation_and_query_read_the_same_window_constant() -> None:
    """★**복사하지 않는다** — 후보 쿼리와 설명이 같은 상수를 본다.

    종전 SQL 은 `timedelta(hours=2)` **리터럴**이었다. 설명하는 쪽이 그 값을 손으로 옮기면
    한쪽만 바뀌었을 때 **조용히 갈린다**(그리고 그 갈림은 초록이다).
    """
    # ★★독립 적대 리뷰 MEDIUM-1 — 독스트링은 **세 상수**를 공유한다고 선언하는데 초판 락은
    #   **창 상수만** 봤다. 실측: `not in CANDIDATE_ACTIONS` → 리터럴 튜플 복사 **SURVIVED** ·
    #   `not in HANDLED_INSIGHT_TYPES` → 복사 **SURVIVED**(대조군: 창 상수 복사는 CAUGHT).
    #   ⇒ **선언한 셋 전부**를 본다. 선언과 락의 범위가 갈리면 락이 선언보다 좁다.
    shared = ("CANDIDATE_WINDOW_HOURS", "CANDIDATE_ACTIONS", "HANDLED_INSIGHT_TYPES")
    q_names, e_names = _names_in(H._candidate_actions), _names_in(H.open_blockers)
    for name in shared:
        assert name in q_names, f"후보 쿼리가 {name} 을 안 쓴다(리터럴로 되돌아갔다)"
        assert name in e_names, f"설명이 {name} 을 안 쓴다(값을 복사했다)"
    assert H.CANDIDATE_WINDOW_HOURS == 2, f"창이 바뀌었다: {H.CANDIDATE_WINDOW_HOURS}"


def test_candidate_query_predicates_are_pinned() -> None:
    """★★독립 적대 리뷰 MEDIUM-2 — **술어가 하나 늘어나는 축**이 통째로 열려 있었다.

    실측: 후보 쿼리 WHERE 에 `severity <> 'info'` 를 **추가**하는 변이가 **SURVIVED**.
    설명(`open_blockers`)은 그 술어를 모르므로 **사용자에게 거짓 사유**를 주게 된다.
    ★기계 변이는 **삭제 축만** 만들어 이 자리를 원리적으로 못 겨눈다.
    ⇒ WHERE 절의 **술어 컬럼 집합을 파생**해 알려진 넷과 정확히 일치하는지 본다.
    """
    import re

    sql = _candidate_sql_of(H._candidate_actions)
    where = sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    cols = set(re.findall(r"\b([a-z_]+)\s*(?:=|<>|>=|<=|IN\b)", where))
    assert cols == {"status", "recommended_action", "insight_type", "created_at"}, (
        f"후보 쿼리의 술어 집합이 바뀌었다: {sorted(cols)} — "
        "`open_blockers` 가 그 술어를 모르면 사용자에게 거짓 사유를 준다"
    )


# ── 배선(라우터가 실제로 값을 싣는가) ────────────────────────────────────────

class _Res:
    def __init__(self, rows=(), scalar=0):
        self._rows, self._scalar = list(rows), scalar

    def scalar(self):
        return self._scalar

    def fetchall(self):
        return list(self._rows)


class _FakeDb:
    """`list_insights` 가 실제로 부르는 세 질의만 답한다."""

    def __init__(self, rows):
        self.rows = rows

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "COUNT(*)" in sql and "GROUP BY" not in sql:
            return _Res(scalar=len(self.rows))
        if "GROUP BY severity" in sql:
            return _Res(rows=[])
        return _Res(rows=self.rows)


def _row(iid, itype, status, action, created):
    # (id, insight_type, severity, status, window_start, window_end,
    #  metrics_json, narrative, recommended_action, created_at)
    return (iid, itype, "warn", status, None, None, None, None, action, created)


@pytest.mark.asyncio
async def test_router_actually_ships_the_blockers(monkeypatch) -> None:
    """★**응답 값으로** 태운다 — 필드 이름이 있는 것과 값이 오는 것은 다르다."""
    async def _ok(_request, _db):
        return None

    monkeypatch.setattr(R, "_require_admin", _ok)

    rows = [
        _row("1", "fallback_rate", "open", "heal", datetime.now(UTC) - timedelta(minutes=5)),
        _row("2", "latency_regression", "open", "heal", datetime.now(UTC) - timedelta(minutes=5)),
        _row("3", "fallback_rate", "open", "heal", datetime.now(UTC) - timedelta(days=8)),
        _row("4", "fallback_rate", "superseded", "heal", datetime.now(UTC)),
    ]
    # ★`Query(default=...)` 는 **함수 직접 호출에선 기본값이 아니다** — FastAPI 가 풀어 주는
    #   것이라, 인자를 생략하면 `Query` 객체가 그대로 들어가 검증에서 죽는다. 전부 명시한다.
    out = await R.list_insights(  # type: ignore[arg-type]
        request=None, db=_FakeDb(rows),
        insight_type=None, severity=None, status=None,
        since=None, until=None, sort="created_at", limit=100, offset=0,
    )
    by_id = {i.id: i for i in out.items}

    # ★공허 방지 — 네 행이 실제로 실렸는가.
    assert len(by_id) == 4, f"행이 유실됐다: {sorted(by_id)}"

    assert by_id["1"].open_blockers == [], "치유 후보에 사유가 붙었다"
    assert by_id["1"].open_blocker_reason is None

    assert by_id["2"].open_blockers == [H.OPEN_BLOCKER_TYPE_NOT_HANDLED]
    assert by_id["2"].open_blocker_reason == H.HEAL_UNHANDLED_REASONS["latency_regression"]

    assert H.OPEN_BLOCKER_WINDOW_EXPIRED in (by_id["3"].open_blockers or [])

    # ★열려 있지 않은 것에는 **붙이지 않는다**(없는 사실을 지어내지 않는다).
    assert by_id["4"].open_blockers is None, by_id["4"].open_blockers
    assert by_id["4"].open_blocker_reason is None
