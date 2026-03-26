"""Part G live module regression tests."""

from pathlib import Path

from apps.api.services.ai_costs_service import AICostsService
from apps.api.services.energy_service import EnergyService
from apps.api.services.investor_report_service import InvestorReportService
from apps.api.services.portals_service import PortalsService

_BASE = Path(__file__).resolve().parents[2]
_PORTALS_SOURCE = (_BASE / "apps" / "api" / "routers" / "portals.py").read_text(encoding="utf-8")
_ENERGY_SOURCE = (_BASE / "apps" / "api" / "routers" / "energy.py").read_text(encoding="utf-8")
_AI_COSTS_SOURCE = (_BASE / "apps" / "api" / "routers" / "ai_costs.py").read_text(encoding="utf-8")


class TestPartGLiveRouters:
    def test_portal_endpoints_exist(self) -> None:
        assert '@router.post("/{portal_id}/post"' in _PORTALS_SOURCE
        assert '@router.post("/post-all"' in _PORTALS_SOURCE
        assert '@router.get("/market-data/{region_code}"' in _PORTALS_SOURCE

    def test_ai_cost_and_energy_endpoints_exist(self) -> None:
        assert '@router.post("/budget"' in _AI_COSTS_SOURCE
        assert '@router.post("/kepco/calculate"' in _ENERGY_SOURCE
        assert '@router.post("/certification"' in _ENERGY_SOURCE


class TestPartGLiveServices:
    def test_ai_cost_month_label(self) -> None:
        label = AICostsService.current_month_label()
        assert len(label) == 7
        assert "-" in label

    def test_energy_grade_helper(self) -> None:
        assert EnergyService.energy_grade(55) == "A+"
        assert EnergyService.energy_grade(140) == "C"

    def test_portal_defaults(self) -> None:
        defaults = PortalsService._portal_defaults("naver")
        assert defaults["views"] > 0
        assert defaults["ctr"] > 0

    def test_investor_report_translation_helper(self) -> None:
        title, translated, quality = InvestorReportService._translate(
            "Mapo Prime",
            "en",
            "Project: Mapo Prime",
        )
        assert "Mapo Prime" in title
        assert translated.startswith("[EN]")
        assert 0 < quality <= 1
