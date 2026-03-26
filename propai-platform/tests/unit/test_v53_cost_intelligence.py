"""Regression tests for v53 cost intelligence APIs."""

from pathlib import Path

from apps.api.auth.rbac import check_permission
from apps.api.services.cost_escalation_engine import CostEscalationEngine
from apps.api.services.kcci_material_price_service import KCCIMaterialPriceService
from packages.schemas.models import (
    CostEscalationRequest,
    CostEscalationResponse,
    MaterialPriceRefreshRequest,
    MaterialPriceSnapshotResponse,
)

_BASE = Path(__file__).resolve().parents[2]
_MAIN_SOURCE = (_BASE / "apps" / "api" / "main.py").read_text(encoding="utf-8")
_ROUTER_SOURCE = (
    _BASE / "apps" / "api" / "routers" / "cost_intelligence.py"
).read_text(encoding="utf-8")


class TestV53CostIntelligenceContracts:
    def test_material_price_contract_fields(self) -> None:
        assert "material_codes" in MaterialPriceRefreshRequest.model_fields
        assert "region_code" in MaterialPriceRefreshRequest.model_fields
        assert "items" in MaterialPriceSnapshotResponse.model_fields
        assert "alerts" in MaterialPriceSnapshotResponse.model_fields

    def test_cost_escalation_contract_fields(self) -> None:
        assert "construction_duration_months" in CostEscalationRequest.model_fields
        assert "material_share_ratio" in CostEscalationRequest.model_fields
        assert "material_impacts" in CostEscalationResponse.model_fields
        assert "yearly_projection" in CostEscalationResponse.model_fields


class TestV53CostIntelligenceRouters:
    def test_main_registers_cost_intelligence_router(self) -> None:
        assert 'prefix="/api/v1/cost-intelligence"' in _MAIN_SOURCE

    def test_router_endpoints_exist(self) -> None:
        assert "/material-prices/refresh" in _ROUTER_SOURCE
        assert '@router.get("/material-prices/latest"' in _ROUTER_SOURCE
        assert "/escalation/analyze" in _ROUTER_SOURCE
        assert "/escalation/{project_id}/latest" in _ROUTER_SOURCE


class TestV53CostIntelligenceServices:
    def test_material_price_math_is_positive(self) -> None:
        price = KCCIMaterialPriceService._calc_unit_price(
            "ready_mix_concrete",
            KCCIMaterialPriceService._month_anchor(2026, 3),
        )
        assert price["unit_price_krw"] > 0
        assert price["price_index"] >= 100
        assert price["yoy_change_ratio"] >= 0

    def test_ppi_index_and_share_normalization(self) -> None:
        assert CostEscalationEngine._ppi_index(2027) > CostEscalationEngine._ppi_index(2024)
        material, labor, overhead = CostEscalationEngine._normalize_shares(
            material_share_ratio=0.62,
            labor_share_ratio=0.28,
            overhead_share_ratio=0.10,
        )
        assert round(material + labor + overhead, 4) == 1.0


class TestV53CostIntelligenceRbac:
    def test_viewer_can_read_cost_intelligence(self) -> None:
        assert check_permission("viewer", "cost_intelligence", "read") is True

    def test_analyst_can_write_cost_intelligence(self) -> None:
        assert check_permission("analyst", "cost_intelligence", "write") is True
