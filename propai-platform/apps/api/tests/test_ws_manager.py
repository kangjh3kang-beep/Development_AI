"""Phase 4 잔여 — 실시간 WS 매니저(broadcast_risk_alert) 단위테스트. 가짜 WS로 검증."""
import pytest

pytestmark = pytest.mark.asyncio


class _FakeWS:
    def __init__(self):
        self.sent: list = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, msg):
        self.sent.append(msg)


async def test_connect_and_broadcast():
    from app.services.realtime.ws_manager import RealtimeManager
    m = RealtimeManager()
    ws = _FakeWS()
    await m.connect("c1", ws)
    assert ws.accepted
    sent = await m.broadcast("c1", {"x": 1})
    assert sent == 1 and ws.sent == [{"x": 1}]


async def test_broadcast_drops_dead_connections():
    from app.services.realtime.ws_manager import RealtimeManager
    m = RealtimeManager()

    class _Dead(_FakeWS):
        async def send_json(self, msg):
            raise RuntimeError("closed")

    good, dead = _FakeWS(), _Dead()
    await m.connect("c", good)
    await m.connect("c", dead)
    assert await m.broadcast("c", {"a": 1}) == 1   # good만 수신, dead 제거
    assert await m.broadcast("c", {"a": 2}) == 1   # dead는 더이상 없음


async def test_broadcast_risk_alert_routes_channels():
    from app.services.realtime import ws_manager
    risk_ws, proj_ws = _FakeWS(), _FakeWS()
    await ws_manager.manager.connect("risk-alerts", risk_ws)
    await ws_manager.manager.connect("project:PRJ-1", proj_ws)
    try:
        sent = await ws_manager.broadcast_risk_alert({"project_id": "PRJ-1", "risk_level": "high"})
        assert sent == 2
        assert risk_ws.sent[0]["type"] == "risk_alert" and proj_ws.sent[0]["risk_level"] == "high"
    finally:
        ws_manager.manager.disconnect("risk-alerts", risk_ws)
        ws_manager.manager.disconnect("project:PRJ-1", proj_ws)
