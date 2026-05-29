"""P0 회귀 테스트: 하드코딩 KPI/랜덤 스트림/고정 Redis DSN 방지."""

from pathlib import Path


_BASE = Path(__file__).resolve().parents[2]
_DASHBOARD_SOURCE = (_BASE / "apps" / "api" / "routers" / "dashboard.py").read_text(encoding="utf-8")
_KDX_SOURCE = (_BASE / "apps" / "api" / "routers" / "kdx.py").read_text(encoding="utf-8")
_DEMAND_SOURCE = (_BASE / "apps" / "api" / "services" / "demand_forecast_service.py").read_text(
    encoding="utf-8"
)


def test_dashboard_overview_does_not_use_hardcoded_investment_kpis() -> None:
    assert "3500.2" not in _DASHBOARD_SOURCE
    assert "avg_roi_pct\": 18.4" not in _DASHBOARD_SOURCE
    assert "FinancialAnalysis" in _DASHBOARD_SOURCE


def test_kdx_websocket_stream_is_not_random_mock_data() -> None:
    assert "random.uniform" not in _KDX_SOURCE
    assert "random.randint" not in _KDX_SOURCE
    assert "_build_market_tick_payload" in _KDX_SOURCE
    assert "KDXMarketMetric" in _KDX_SOURCE


def test_demand_forecast_redis_dsn_is_not_hardcoded() -> None:
    assert "redis://localhost:6379/1" not in _DEMAND_SOURCE
    assert "settings.redis_cache_url" in _DEMAND_SOURCE
