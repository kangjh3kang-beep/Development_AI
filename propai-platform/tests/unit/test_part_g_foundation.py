"""Part G foundation regression tests."""

from pathlib import Path

from apps.api.auth.rbac import check_permission
from apps.api.database.models.phase_g_ai_costs import AICostBudget
from apps.api.database.models.phase_g_energy import (
    EnergyCertificationRecord,
    EnergyCertScore,
    KepcoRateCache,
)
from apps.api.database.models.phase_g_multilingual import MultilingualReport, TranslationJob
from apps.api.database.models.phase_g_portal import PortalListing, PortalPerformance
from packages.schemas.models import (
    AICostBudgetRequest,
    AICostBudgetResponse,
    InvestorReportRequest,
    InvestorReportResponse,
    PortalBatchPostRequest,
    PortalBatchPostResponse,
    PortalMarketDataResponse,
    PortalPostRequest,
    PortalPostResponse,
)

_BASE = Path(__file__).resolve().parents[2]
_MAIN_SOURCE = (_BASE / "apps" / "api" / "main.py").read_text(encoding="utf-8")
_AI_COSTS_SOURCE = (_BASE / "apps" / "api" / "routers" / "ai_costs.py").read_text(encoding="utf-8")
_REPORTS_SOURCE = (_BASE / "apps" / "api" / "routers" / "reports.py").read_text(encoding="utf-8")


class TestPartGModels:
    def test_ai_cost_energy_models_have_expected_columns(self) -> None:
        assert {"endpoint", "month", "monthly_budget_usd", "alert_threshold_ratio"}.issubset(
            {column.name for column in AICostBudget.__table__.columns}
        )
        assert {"contract_type", "energy_rate_krw_per_kwh", "base_charge_krw_per_kw"}.issubset(
            {column.name for column in KepcoRateCache.__table__.columns}
        )
        assert {"project_id", "energy_grade", "bems_saving_kwh"}.issubset(
            {column.name for column in EnergyCertificationRecord.__table__.columns}
        )
        assert {"certification_id", "score_name", "score_value"}.issubset(
            {column.name for column in EnergyCertScore.__table__.columns}
        )

    def test_portal_and_report_models_have_expected_columns(self) -> None:
        assert {"region_code", "listing_title", "metadata_json"}.issubset(
            {column.name for column in PortalListing.__table__.columns}
        )
        assert {"project_id", "listing_id", "view_count", "metrics_json"}.issubset(
            {column.name for column in PortalPerformance.__table__.columns}
        )
        assert {"project_id", "target_language", "translated_text", "quality_score"}.issubset(
            {column.name for column in MultilingualReport.__table__.columns}
        )
        assert {"project_id", "report_id", "status", "word_count"}.issubset(
            {column.name for column in TranslationJob.__table__.columns}
        )


class TestPartGContracts:
    def test_budget_contracts(self) -> None:
        assert "endpoint" in AICostBudgetRequest.model_fields
        assert "alert_threshold_ratio" in AICostBudgetRequest.model_fields
        assert "budget_id" in AICostBudgetResponse.model_fields

    def test_portal_contracts(self) -> None:
        assert "region_code" in PortalPostRequest.model_fields
        assert "portals" in PortalBatchPostRequest.model_fields
        assert "success_count" in PortalBatchPostResponse.model_fields
        assert "top_portals" in PortalMarketDataResponse.model_fields
        assert "listing_url" in PortalPostResponse.model_fields

    def test_investor_report_contracts(self) -> None:
        assert "target_languages" in InvestorReportRequest.model_fields
        assert "variants" in InvestorReportResponse.model_fields


class TestPartGRoutersAndRbac:
    def test_main_registers_portals_router(self) -> None:
        assert 'prefix="/api/v1/portals"' in _MAIN_SOURCE

    def test_ai_budget_and_investor_report_endpoints_exist(self) -> None:
        assert '@router.post("/budget"' in _AI_COSTS_SOURCE
        assert '@router.post("/investor/generate"' in _REPORTS_SOURCE

    def test_part_g_permissions(self) -> None:
        assert check_permission("manager", "ai_costs", "write") is True
        assert check_permission("analyst", "ai_costs", "write") is False
        assert check_permission("manager", "portals", "write") is True
        assert check_permission("viewer", "portals", "read") is True
