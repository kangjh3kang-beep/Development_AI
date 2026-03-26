"""Part G G95 live module regression tests."""

from pathlib import Path
from uuid import uuid4

from apps.api.auth.rbac import check_permission
from apps.api.database.models.phase_g_chatbot import ChatbotMessage, ChatbotSession
from apps.api.database.models.phase_g_operations import AuctionListing, Contractor
from apps.api.services.auction_service import AuctionService
from apps.api.services.chatbot_service import ChatbotService
from apps.api.services.contractor_service import ContractorService
from packages.schemas.models import (
    AuctionAnalysisRequest,
    AuctionListingResponse,
    ChatbotConversationResponse,
    ChatbotReplyResponse,
    ChatbotSessionCreateRequest,
    ContractorCreateRequest,
    ContractorRecommendationRequest,
    ContractorRecommendationResponse,
)

_BASE = Path(__file__).resolve().parents[2]
_MAIN_SOURCE = (_BASE / "apps" / "api" / "main.py").read_text(encoding="utf-8")
_CHATBOT_SOURCE = (_BASE / "apps" / "api" / "routers" / "chatbot.py").read_text(encoding="utf-8")
_AUCTION_SOURCE = (_BASE / "apps" / "api" / "routers" / "auction.py").read_text(encoding="utf-8")
_CONTRACTORS_SOURCE = (_BASE / "apps" / "api" / "routers" / "contractors.py").read_text(
    encoding="utf-8"
)


class TestG95Models:
    def test_chatbot_models_have_expected_columns(self) -> None:
        assert {"tenant_id", "user_id", "domain", "message_count"}.issubset(
            {column.name for column in ChatbotSession.__table__.columns}
        )
        assert {"session_id", "role", "content", "sequence_number"}.issubset(
            {column.name for column in ChatbotMessage.__table__.columns}
        )

    def test_auction_and_contractor_models_have_expected_columns(self) -> None:
        assert {"case_number", "auction_type", "analysis_json"}.issubset(
            {column.name for column in AuctionListing.__table__.columns}
        )
        assert {"business_number", "category", "specialties_json", "is_active"}.issubset(
            {column.name for column in Contractor.__table__.columns}
        )


class TestG95Contracts:
    def test_chatbot_contracts(self) -> None:
        assert "domain" in ChatbotSessionCreateRequest.model_fields
        assert "messages" in ChatbotConversationResponse.model_fields
        assert "assistant_message" in ChatbotReplyResponse.model_fields

    def test_auction_and_contractor_contracts(self) -> None:
        assert "occupancy_status" in AuctionAnalysisRequest.model_fields
        assert "investment_score" in AuctionListingResponse.model_fields
        assert "specialties" in ContractorCreateRequest.model_fields
        assert "recommendations" in ContractorRecommendationResponse.model_fields
        assert "required_specialties" in ContractorRecommendationRequest.model_fields


class TestG95RoutersAndRbac:
    def test_main_registers_g95_routers(self) -> None:
        assert 'prefix="/api/v1/chatbot"' in _MAIN_SOURCE
        assert 'prefix="/api/v1/auction"' in _MAIN_SOURCE
        assert 'prefix="/api/v1/contractors"' in _MAIN_SOURCE

    def test_router_endpoints_exist(self) -> None:
        assert '@router.post("/sessions"' in _CHATBOT_SOURCE
        assert '@router.post("/messages"' in _CHATBOT_SOURCE
        assert '@router.post("/analyze"' in _AUCTION_SOURCE
        assert '@router.get("/opportunities"' in _AUCTION_SOURCE
        assert '@router.post("/register"' in _CONTRACTORS_SOURCE
        assert '@router.post("/recommend"' in _CONTRACTORS_SOURCE

    def test_g95_permissions(self) -> None:
        assert check_permission("manager", "chatbot", "write") is True
        assert check_permission("viewer", "chatbot", "read") is False
        assert check_permission("viewer", "auction", "read") is True
        assert check_permission("analyst", "auction", "write") is True
        assert check_permission("manager", "contractors", "write") is True
        assert check_permission("analyst", "contractors", "write") is False


class TestG95Services:
    def test_chatbot_reply_template(self) -> None:
        reply, actions = ChatbotService._reply("investment", "Review debt sizing and downside.")
        assert "investment" in reply
        assert len(actions) == 3
        assert "underwriting" in reply

    def test_auction_analysis_snapshot(self) -> None:
        analysis = AuctionService._analysis_snapshot(
            appraised_value_krw=1_000_000_000,
            minimum_bid_krw=760_000_000,
            bid_count=1,
            occupancy_status="vacant",
            senior_lien_exists=False,
            expected_repair_cost_krw=20_000_000,
            nearby_market_price_krw=1_050_000_000,
        )
        assert analysis["investment_score"] > 0
        assert analysis["recommended_max_bid_krw"] >= 760_000_000
        assert analysis["expected_margin_krw"] >= 0

    def test_contractor_match_score(self) -> None:
        contractor = Contractor(
            tenant_id=uuid4(),
            company_name="Build Prime",
            business_number="1234567890",
            category="general_contractor",
            specialties_json=["facade", "mep", "interior"],
            address="Seoul Gangnam-gu",
            rating=4.5,
        )
        score, reasons = ContractorService._score_candidate(
            category="general_contractor",
            required_specialties=["mep", "interior"],
            region_hint="Gangnam",
            contractor=contractor,
        )
        assert score > 70
        assert reasons
