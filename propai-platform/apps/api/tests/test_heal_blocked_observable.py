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

from datetime import datetime, timedelta, timezone

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
    """실행된 SQL 로 질의를 가른다 — 핸들러를 **실물로** 태우기 위한 최소 스텁."""

    def __init__(self, actions=(), blocked=(), flags=()):
        self.actions, self.blocked, self.flags = list(actions), list(blocked), list(flags)
        self.seen: list[str] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.seen.append(sql)
        if "platform_settings" in sql:
            return _Res(rows=self.flags)
        if "heal_blocked" in sql:
            return _Res(scalar=len(self.blocked), rows=self.blocked) if "COUNT(*)" not in sql \
                else _Res(scalar=len(self.blocked))
        if "heal_action" in sql:
            return _Res(scalar=len(self.actions), rows=self.actions) if "COUNT(*)" not in sql \
                else _Res(scalar=len(self.actions))
        return _Res(scalar=0, rows=[])


NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
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
    out = await _call(_FakeDB(actions=[ACTION_ROW], blocked=[BLOCKED_ROW]))
    assert out.blocked_total == 1
    assert [b.reason for b in out.blocked] == ["cooldown"]
    assert [b.trigger_key for b in out.blocked] == ["fallback_rate:site_analysis"]


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
