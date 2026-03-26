"""Regression tests for KDX live monitoring and feasibility endpoints."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from apps.api.auth.rbac import check_permission
from apps.api.services.feasibility_service import FeasibilityService
from apps.api.services.kdx_integration_service import KDXIntegrationService
from packages.schemas.models import (
    FeasibilityAnalysisRequest,
    FeasibilityAnalysisResponse,
    KDXOverviewResponse,
)

_BASE = Path(__file__).resolve().parents[2]
_FINANCE_SOURCE = (_BASE / "apps" / "api" / "routers" / "finance.py").read_text(encoding="utf-8")
_KDX_SOURCE = (_BASE / "apps" / "api" / "routers" / "kdx.py").read_text(encoding="utf-8")
_CHART_SOURCE = (
    _BASE / "apps" / "web" / "components" / "dashboard" / "kdx" / "KdxRealtimeChart.tsx"
).read_text(encoding="utf-8")


class TestKdxFeasibilityContracts:
    def test_feasibility_request_and_response_fields(self) -> None:
        assert "scenario_name" in FeasibilityAnalysisRequest.model_fields
        assert "annual_revenue_krw" in FeasibilityAnalysisRequest.model_fields
        assert "cashflows" in FeasibilityAnalysisResponse.model_fields
        assert "exit_value_krw" in FeasibilityAnalysisResponse.model_fields

    def test_kdx_overview_response_fields(self) -> None:
        assert "connection_status" in KDXOverviewResponse.model_fields
        assert "throughput_tps" in KDXOverviewResponse.model_fields
        assert "recent_logs" in KDXOverviewResponse.model_fields


class TestKdxFeasibilityRouters:
    def test_finance_endpoints_exist(self) -> None:
        assert '@router.post("/feasibility"' in _FINANCE_SOURCE
        assert '@router.get("/feasibility/{project_id}/latest"' in _FINANCE_SOURCE

    def test_kdx_overview_endpoint_and_router_prefix_fix_exist(self) -> None:
        assert 'router = APIRouter()' in _KDX_SOURCE
        assert '@router.get("/overview"' in _KDX_SOURCE

    def test_kdx_chart_uses_api_base_origin_for_websocket(self) -> None:
        assert "apiClient.getRuntimeConfig()" in _CHART_SOURCE
        assert "/api/v1/kdx/stream" in _CHART_SOURCE


class TestKdxFeasibilityServices:
    def test_feasibility_cashflow_shape(self) -> None:
        cashflows = FeasibilityService._build_cashflows(
            annual_revenue_krw=280_000_000,
            annual_operating_cost_krw=95_000_000,
            annual_growth_rate=0.02,
            discount_rate=0.05,
            analysis_years=5,
        )
        assert len(cashflows) == 5
        assert cashflows[0].year == 1
        assert cashflows[-1].revenue_krw > cashflows[0].revenue_krw
        assert cashflows[0].discounted_cashflow_krw < cashflows[0].net_cashflow_krw

    def test_feasibility_irr_and_payback_are_positive_for_profitable_case(self) -> None:
        cashflows = FeasibilityService._build_cashflows(
            annual_revenue_krw=320_000_000,
            annual_operating_cost_krw=90_000_000,
            annual_growth_rate=0.015,
            discount_rate=0.05,
            analysis_years=8,
        )
        irr = FeasibilityService._calc_irr(
            [-1_200_000_000]
            + [row.net_cashflow_krw for row in cashflows[:-1]]
            + [cashflows[-1].net_cashflow_krw + 1_600_000_000]
        )
        payback = FeasibilityService._calc_payback_period_months(
            total_investment_krw=1_200_000_000,
            annual_cashflows=cashflows,
            exit_value_krw=1_600_000_000,
        )
        assert irr > 0
        assert payback > 0
        assert payback <= 96

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
