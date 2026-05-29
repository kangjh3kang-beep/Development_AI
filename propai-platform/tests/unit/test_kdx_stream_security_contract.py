"""KDX 실시간 스트림 보안/테넌트 경계 계약 테스트."""

from pathlib import Path


_BASE = Path(__file__).resolve().parents[2]
_KDX_ROUTER_SOURCE = (_BASE / "apps" / "api" / "routers" / "kdx.py").read_text(encoding="utf-8")
_KDX_CHART_SOURCE = (
    _BASE / "apps" / "web" / "components" / "dashboard" / "kdx" / "KdxRealtimeChart.tsx"
).read_text(encoding="utf-8")


def test_kdx_websocket_requires_access_token() -> None:
    assert 'query_params.get("token"' in _KDX_ROUTER_SOURCE
    assert "decode_token(" in _KDX_ROUTER_SOURCE
    assert "token_type != \"access\"" in _KDX_ROUTER_SOURCE


def test_kdx_market_tick_is_tenant_scoped() -> None:
    assert "KDXMarketMetric.tenant_id == tenant_id" in _KDX_ROUTER_SOURCE
    assert "KDXTelemetryLog.tenant_id == tenant_id" in _KDX_ROUTER_SOURCE
    assert "tenant_id=tenant_id" in _KDX_ROUTER_SOURCE


def test_kdx_chart_sends_token_in_websocket_query() -> None:
    assert "propai_access_token" in _KDX_CHART_SOURCE
    assert "encodeURIComponent(accessToken)" in _KDX_CHART_SOURCE
    assert "/api/v1/kdx/stream?token=" in _KDX_CHART_SOURCE
