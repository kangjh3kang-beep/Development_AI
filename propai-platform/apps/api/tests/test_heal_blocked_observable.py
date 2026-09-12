"""게이트가 **막은** 치유가 조회 표면에 나오는가 — 그리고 실행된 액션과 **섞이지 않는가**.

## 왜 이 파일이 있나 (실측 2026-09-09 · sid=7af9eaa2)

`healing_rules` 는 게이트가 후보를 막을 때 `platform_events` 에 `heal_blocked` 를
**넣고 있었다**(`healing_rules.py:71,291` · 계약은 `test_heal_escalation_reachable.py` 가 잠금).
그런데 **그것을 읽는 경로가 하나도 없었다** — `routers/growth.py` 의 `heal_blocked` 언급 **0건**
(대조군: 같은 파일의 `heal-log` **6건** ⇒ 조회기 생존).

그 결과 **«게이트가 막고 있다» 와 «막을 후보가 없다» 가 같은 관측(침묵)** 이었다.
독립 추적이 «게이트 차단 가설(H2)» 을 **완전히 기각하지 못한 이유가 정확히 이것**이다
(그 세션 원문: *"`heal_blocked` 이벤트 자체를 노출하는 API 엔드포인트가 없어 직접 조회는 못 했다"*).

★***침묵은 성공이 아니다.*** 이 저장소가 반복해 데인 형태다.

## 락의 형태 — **오염 축을 함께 잠근다**

막힌 것을 `actions` 에 섞으면 기존 소비처의 «실행된 액션 수» 가 조용히 부푼다.
이 저장소에는 ***«두 필드가 함께 부풀면 정합성 검사가 눈이 먼다»*** 는 실측 전례가 있다.
그래서 **두 모집단이 서로 다른 자리로 가는지**를 같은 실행에서 단언한다.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.routers import growth as G


class _Res:
    def __init__(self, scalar=None, rows=()):
        self._s, self._r = scalar, list(rows)

    def scalar(self):
        return self._s

    def fetchall(self):
        return self._r


class _FakeDB:
    """실행된 SQL 로 질의를 가른다 — 핸들러를 **실물로** 태우기 위한 최소 스텁.

    ★2026-09-12 독립 리뷰(MAJOR-1): 종전 스텁은 `params` 를 **받아 놓고 한 번도 안 봤고**,
      행을 SELECT 목록과 **무관하게** 늘 같은 튜플로 돌려줬다. 그래서 **bind 값 축**과
      **컬럼 순서 축**이 원리적으로 무잠금이었고, 독립 변이 **6건이 전부 생존**했다
      (SELECT 순서 뒤집기 · `created_at` 삭제 · `at` 상수화 · `limit`→1 · `DESC`→`ASC` · `offset`→0).
      ★그중 순서 뒤집기는 실 Postgres 에서 `/growth/heal-log` **전체가 500** 이 되는 변이다.
      ⇒ 스텁이 **params 를 기록**하고 테스트가 그것을 단언한다. 「스텁도 계약이다.」
    """

    def __init__(self, actions=(), blocked=(), flags=(), reasons=()):
        self.actions, self.blocked, self.flags = list(actions), list(blocked), list(flags)
        self.reasons = list(reasons)
        self.seen: list[str] = []
        self.binds: list[dict] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.seen.append(sql)
        self.binds.append(dict(params or {}))
        if "payload->>'reason'" in sql and "GROUP BY" in sql:
            return _Res(rows=self.reasons)
        if "platform_settings" in sql:
            return _Res(rows=self.flags)
        if "heal_blocked" in sql:
            return _Res(scalar=len(self.blocked), rows=self.blocked) if "COUNT(*)" not in sql \
                else _Res(scalar=len(self.blocked))
        if "heal_action" in sql:
            return _Res(scalar=len(self.actions), rows=self.actions) if "COUNT(*)" not in sql \
                else _Res(scalar=len(self.actions))
        return _Res(scalar=0, rows=[])


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
# (severity, service, payload, created_at)
ACTION_ROW = ("warn", "site_analysis",
              {"action_id": "a1", "action_type": "threshold_relax", "executed": True}, NOW)
# (payload, created_at)
BLOCKED_ROW = ({"action_type": "threshold_relax", "reason": "cooldown",
                "params": {"trigger_key": "fallback_rate:site_analysis"}}, NOW)


@pytest.fixture(autouse=True)
def _no_admin(monkeypatch):
    async def _ok(_request, _db):
        return "admin"
    monkeypatch.setattr(G, "_require_admin", _ok)


async def _call(db, **kw):
    return await G.heal_log(request=object(), db=db, action_type=kw.get("action_type"),
                            since=kw.get("since"), limit=kw.get("limit", 100),
                            offset=kw.get("offset", 0))


@pytest.mark.asyncio
async def test_blocked_events_are_exposed():
    """★네 필드를 **전부** 단언한다 — 하나라도 빠지면 그 필드는 무잠금이다.

    기계 변이가 실증했다: `action_type`·`created_at` 을 안 단언했더니 그 줄을 지워도 초록이었다
    (`mutate_changed.py` 생존 6건 중 3건이 정확히 그 자리).
    """
    out = await _call(_FakeDB(actions=[ACTION_ROW], blocked=[BLOCKED_ROW]))
    assert out.blocked_total == 1
    b = out.blocked[0]
    assert b.reason == "cooldown"
    assert b.trigger_key == "fallback_rate:site_analysis"
    assert b.action_type == "threshold_relax", "action_type 이 실리지 않는다"
    assert b.created_at == NOW, "created_at 이 실리지 않는다"


@pytest.mark.asyncio
async def test_payload_may_arrive_as_json_string():
    """★실 DB 드라이버는 jsonb 를 **문자열로** 줄 수 있다 — 형제(`actions`)도 같은 분기를 갖는다."""
    import json
    row = (json.dumps(BLOCKED_ROW[0], ensure_ascii=False), NOW)
    out = await _call(_FakeDB(blocked=[row]))
    assert out.blocked and out.blocked[0].reason == "cooldown", "문자열 payload 를 못 읽는다"
    assert out.blocked[0].trigger_key == "fallback_rate:site_analysis"


@pytest.mark.asyncio
async def test_null_payload_does_not_explode():
    """★payload 가 NULL 인 행이 있어도 죽지 않는다(관측 장치가 관측 때문에 죽으면 안 된다)."""
    out = await _call(_FakeDB(blocked=[(None, NOW)]))
    assert out.blocked_total == 1
    assert out.blocked[0].reason is None and out.blocked[0].created_at == NOW


def _row_query(db) -> str:
    q = [x for x in db.seen if "heal_blocked" in x and "COUNT(*)" not in x and "GROUP BY" not in x]
    assert q, "blocked 행 질의가 없다"
    return q[0]


def _select_clause(sql: str) -> str:
    """★`created_at` 은 **ORDER BY 절에도** 있다 — 전체 문자열로 보면 SELECT 에서 지워도 참이다
    (독립 리뷰 MINOR-1 이 변이로 실증). 그래서 SELECT…FROM 구간만 잘라서 본다."""
    head = sql.upper().index("SELECT")
    tail = sql.upper().index("FROM")
    return sql[head:tail]


@pytest.mark.asyncio
async def test_blocked_query_selects_the_columns_it_reads_in_order():
    """★읽는 열을 **순서까지** 단언한다.

    `br[0]`=payload · `br[1]`=created_at 로 위치 인덱싱하므로, SELECT 순서가 뒤집히면
    실 Postgres 에서 `bpl.get(...)` 이 datetime 을 받아 **AttributeError → 500** 이다.
    신규 필드만 죽는 것이 아니라 **대시보드 기존 3필드가 함께** 죽는다.
    """
    db = _FakeDB(blocked=[BLOCKED_ROW])
    await _call(db)
    sel = _select_clause(_row_query(db))
    assert "payload" in sel, "payload 를 SELECT 하지 않는다"
    assert "created_at" in sel, "created_at 을 SELECT 하지 않는다(ORDER BY 절과 혼동 금지)"
    assert sel.index("payload") < sel.index("created_at"), \
        "SELECT 순서가 뒤집혔다 — br[0]/br[1] 위치 인덱싱과 어긋난다(실 DB 에서 500)"


@pytest.mark.asyncio
async def test_blocked_query_orders_newest_first():
    db = _FakeDB(blocked=[BLOCKED_ROW])
    await _call(db)
    sql = " ".join(_row_query(db).split()).upper()
    assert "ORDER BY CREATED_AT DESC" in sql, "최신순이 아니다 — 목록의 뜻이 바뀐다"


@pytest.mark.asyncio
async def test_filter_and_paging_bind_values_reach_the_query():
    """★**bind 값**을 단언한다 — 종전 스텁은 `params` 를 버려서 이 축이 무잠금이었다."""
    db = _FakeDB(blocked=[BLOCKED_ROW])
    await _call(db, action_type="threshold_relax", since=NOW - timedelta(hours=1), limit=7, offset=3)
    row_binds = [b for b, q in zip(db.binds, db.seen)
                 if "heal_blocked" in q and "COUNT(*)" not in q and "GROUP BY" not in q]
    assert row_binds, "blocked 행 질의의 bind 를 못 봤다"
    b = row_binds[0]
    assert b.get("at") == "threshold_relax", f"action_type 이 bind 되지 않았다: {b}"
    assert b.get("limit") == 7, f"limit 이 bind 되지 않았다: {b}"
    assert b.get("offset") == 3, f"offset 이 bind 되지 않았다: {b}"
    assert b.get("since") is not None, "since 가 bind 되지 않았다"


@pytest.mark.asyncio
async def test_limit_and_offset_are_not_the_same_population():
    """★limit·offset 이 **서로 다른 값**으로 도달하는지(한 변수로 뭉개면 둘 다 무잠금)."""
    db = _FakeDB(blocked=[BLOCKED_ROW])
    await _call(db, limit=11, offset=5)
    b = [x for x, q in zip(db.binds, db.seen)
         if "heal_blocked" in q and "COUNT(*)" not in q and "GROUP BY" not in q][0]
    assert (b.get("limit"), b.get("offset")) == (11, 5)


@pytest.mark.asyncio
async def test_blocked_by_reason_does_not_merge_two_states():
    """★★합산이 **저장소가 갈라 놓은 두 상태**를 뭉개지 않는가(독립 리뷰 MAJOR-2).

    `healing_rules` 는 `CAP_BLOCK_REASONS`(기록: global_cap+trigger_cap)와
    `ESCALATION_COUNT_REASONS`(판정: **trigger_cap 하나**)를 의도적으로 가른다.
    `blocked_total` 만 내면 그 구별이 다시 사라진다 — 사유별 계수가 **서로 다른 수**여야 한다.
    """
    out = await _call(_FakeDB(
        blocked=[BLOCKED_ROW, BLOCKED_ROW, BLOCKED_ROW],
        reasons=[("global_cap", 2), ("trigger_cap", 1)],
    ))
    assert out.blocked_by_reason == {"global_cap": 2, "trigger_cap": 1}
    assert out.blocked_by_reason["global_cap"] != out.blocked_by_reason["trigger_cap"], \
        "두 사유가 같은 수를 냈다 — 픽스처가 두 상태를 안 가른다"
    assert sum(out.blocked_by_reason.values()) == 3


@pytest.mark.asyncio
async def test_blocked_does_not_contaminate_actions():
    """★오염 축 — 두 모집단이 **서로 다른 자리**로 가야 한다."""
    out = await _call(_FakeDB(actions=[ACTION_ROW], blocked=[BLOCKED_ROW, BLOCKED_ROW]))
    assert len(out.actions) == 1, "막힌 것이 actions 에 섞였다"
    assert out.total == 1, "막힌 것이 기존 total 을 부풀렸다"
    assert out.blocked_total == 2


@pytest.mark.asyncio
async def test_two_populations_are_distinguishable():
    """★공허 진리 가드 — 「둘 다 0」·「둘 다 같은 수」면 이 락은 아무것도 안 가른다."""
    only_actions = await _call(_FakeDB(actions=[ACTION_ROW, ACTION_ROW], blocked=[]))
    only_blocked = await _call(_FakeDB(actions=[], blocked=[BLOCKED_ROW]))
    assert (only_actions.total, only_actions.blocked_total) == (2, 0)
    assert (only_blocked.total, only_blocked.blocked_total) == (0, 1)


@pytest.mark.asyncio
async def test_silence_is_not_success_both_zero_is_reported_as_zero():
    """막힌 것이 **없을 때**도 필드가 존재해야 한다 — 필드 부재와 0 을 구별한다."""
    out = await _call(_FakeDB(actions=[], blocked=[]))
    assert out.blocked == [] and out.blocked_total == 0


@pytest.mark.asyncio
async def test_filters_reach_the_blocked_query():
    """★필터가 한쪽에만 걸리면 두 수가 **다른 모집단**을 말하게 된다."""
    db = _FakeDB(actions=[ACTION_ROW], blocked=[BLOCKED_ROW])
    await _call(db, action_type="threshold_relax", since=NOW - timedelta(hours=1))
    blocked_sql = [s for s in db.seen if "heal_blocked" in s]
    assert blocked_sql, "heal_blocked 질의가 아예 나가지 않았다"
    for s in blocked_sql:
        assert "payload->>'action_type' = :at" in s, "action_type 필터가 blocked 에 안 걸렸다"
        assert "created_at >= :since" in s, "since 필터가 blocked 에 안 걸렸다"


@pytest.mark.asyncio
async def test_action_query_is_still_scoped_to_heal_action():
    """★대조군 — blocked 를 추가하며 기존 질의의 스코프를 넓히지 않았는가."""
    db = _FakeDB(actions=[ACTION_ROW], blocked=[BLOCKED_ROW])
    await _call(db)
    act_sql = [s for s in db.seen if "heal_action" in s]
    assert act_sql, "heal_action 질의가 사라졌다"
    assert all("heal_blocked" not in s for s in act_sql), "기존 질의가 blocked 까지 긁는다"
