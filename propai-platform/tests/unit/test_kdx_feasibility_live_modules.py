"""Regression tests for KDX live monitoring endpoints."""

from datetime import datetime, timedelta, timezone
UTC = timezone.utc
from pathlib import Path

from apps.api.auth.rbac import check_permission
from apps.api.services.kdx_integration_service import KDXIntegrationService
from packages.schemas.models import KDXOverviewResponse

_BASE = Path(__file__).resolve().parents[2]
_KDX_SOURCE = (_BASE / "apps" / "api" / "routers" / "kdx.py").read_text(encoding="utf-8")
_CHART_SOURCE = (
    _BASE / "apps" / "web" / "components" / "dashboard" / "kdx" / "KdxRealtimeChart.tsx"
).read_text(encoding="utf-8")


class TestKdxFeasibilityContracts:
    def test_kdx_overview_response_fields(self) -> None:
        assert "connection_status" in KDXOverviewResponse.model_fields
        assert "throughput_tps" in KDXOverviewResponse.model_fields
        assert "recent_logs" in KDXOverviewResponse.model_fields


class TestKdxFeasibilityRouters:
    def test_kdx_overview_endpoint_and_router_prefix_fix_exist(self) -> None:
        assert 'router = APIRouter()' in _KDX_SOURCE
        assert '@router.get("/overview"' in _KDX_SOURCE

    def test_kdx_chart_uses_api_base_origin_for_websocket(self) -> None:
        assert "apiClient.getRuntimeConfig()" in _CHART_SOURCE
        assert "/api/v1/kdx/stream" in _CHART_SOURCE


class TestKdxFeasibilityServices:
    def test_kdx_status_helpers(self) -> None:
        stable_seen_at = datetime.now(UTC) - timedelta(seconds=60)
        stale_seen_at = datetime.now(UTC) - timedelta(hours=2)
        assert KDXIntegrationService._connection_status(latest_seen_at=stable_seen_at) == "stable"
        assert KDXIntegrationService._connection_status(latest_seen_at=stale_seen_at) == "stale"
        assert KDXIntegrationService._throughput_tps(recent_log_count=4, recent_metric_count=10) == 96
        assert KDXIntegrationService._latency_ms(latest_seen_at=stable_seen_at) >= 0


class TestKdxFeasibilityRBAC:
    def test_viewer_can_read_kdx(self) -> None:
        assert check_permission("viewer", "kdx", "read") is True

    def test_analyst_can_write_kdx(self) -> None:
        assert check_permission("analyst", "kdx", "write") is True
