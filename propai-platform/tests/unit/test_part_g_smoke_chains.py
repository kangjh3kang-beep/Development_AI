"""Part G cross-module smoke-chain regression tests."""

from types import SimpleNamespace
from uuid import uuid4

from apps.api.database.models.phase_g_operations import Contractor
from apps.api.services.auction_service import AuctionService
from apps.api.services.contractor_service import ContractorService
from apps.api.services.investor_report_service import InvestorReportService
from apps.api.services.portals_service import PortalsService


class TestPartGSmokeChains:
    def test_underwriting_reports_portals_chain(self) -> None:
        source_text = InvestorReportService._compose_source_text(
            project_name="Mapo Prime",
            asset_type="mixed-use",
            include_sections=["executive-summary", "financials", "esg", "risks", "market"],
            investment_highlights=["prime transit access", "institutional demand"],
            risks=["capital markets timing"],
            underwriting=SimpleNamespace(
                recommendation="proceed",
                profit_margin_ratio=0.182,
                risk_level="moderate",
            ),
            esg_report=SimpleNamespace(
                environmental_score=84.0,
                social_score=79.0,
                governance_score=81.0,
            ),
            climate_report=SimpleNamespace(
                flood_risk_score=0.22,
                heat_risk_score=0.35,
                annual_expected_loss_krw=13000000.0,
            ),
            asset_snapshot=SimpleNamespace(
                composite_score=88.0,
                grade="A",
                adjusted_value_krw=187000000000.0,
            ),
        )
        title, translated, quality = InvestorReportService._translate(
            "Mapo Prime",
            "en",
            source_text,
        )
        portal_defaults = PortalsService._portal_defaults("naver")

        assert "Underwriting: proceed" in source_text
        assert "Asset intelligence" in source_text
        assert title.startswith("Mapo Prime")
        assert translated.startswith("[EN]")
        assert quality > 0.9
        assert portal_defaults["views"] > 0
        assert portal_defaults["ctr"] > 0

    def test_auction_contractors_chain(self) -> None:
        analysis = AuctionService._analysis_snapshot(
            appraised_value_krw=1_200_000_000,
            minimum_bid_krw=860_000_000,
            bid_count=2,
            occupancy_status="vacant",
            senior_lien_exists=False,
            expected_repair_cost_krw=25_000_000,
            nearby_market_price_krw=1_260_000_000,
        )
        contractor = Contractor(
            tenant_id=uuid4(),
            company_name="Metro Build Partners",
            business_number="1234567890",
            category="general_contractor",
            specialties_json=["mep", "interior", "facade"],
            address="Seoul Mapo-gu",
            rating=4.3,
        )
        score, reasons = ContractorService._score_candidate(
            category="general_contractor",
            required_specialties=["mep", "interior"],
            region_hint="Mapo",
            contractor=contractor,
        )

        assert analysis["investment_score"] > 60
        assert analysis["expected_margin_krw"] >= 0
        assert score > 70
        assert reasons
