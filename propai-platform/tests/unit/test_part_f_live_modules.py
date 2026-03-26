"""Part F live module regression tests for marketing and domain agents."""

from pathlib import Path

from apps.api.services.domain_agents_service import DomainAgentsService
from apps.api.services.marketing_service import MarketingService
from packages.schemas.models import (
    DomainAgentApprovalBatchDecisionRequest,
    DomainAgentApprovalBatchDecisionResponse,
    DomainAgentApprovalDecisionRequest,
    DomainAgentApprovalQueueResponse,
    DomainAgentHistoryResponse,
    DomainAgentRunRequest,
    DomainAgentRunResponse,
    DomainMultiAnalysisRequest,
    DomainMultiAnalysisResponse,
    MarketingContentRequest,
    MarketingContentResponse,
    OMReportRequest,
    OMReportResponse,
)

_BASE = Path(__file__).resolve().parents[2]
_MARKETING_SOURCE = (_BASE / "apps" / "api" / "routers" / "marketing.py").read_text(encoding="utf-8")
_DOMAIN_AGENTS_SOURCE = (_BASE / "apps" / "api" / "routers" / "domain_agents.py").read_text(encoding="utf-8")


class TestPartFLiveContracts:
    def test_marketing_request_and_response_fields(self) -> None:
        assert "highlights" in MarketingContentRequest.model_fields
        assert "call_to_action" in MarketingContentResponse.model_fields
        assert "risk_factors" in OMReportRequest.model_fields
        assert "sections" in OMReportResponse.model_fields

    def test_domain_agent_request_and_response_fields(self) -> None:
        assert "approval_role" in DomainAgentRunRequest.model_fields
        assert "approval_required" in DomainAgentRunResponse.model_fields
        assert "domains" in DomainMultiAnalysisRequest.model_fields
        assert "portfolio_summary" in DomainMultiAnalysisResponse.model_fields
        assert "decision" in DomainAgentApprovalDecisionRequest.model_fields
        assert "project_id" in DomainAgentApprovalBatchDecisionRequest.model_fields
        assert "updated_count" in DomainAgentApprovalBatchDecisionResponse.model_fields
        assert "items" in DomainAgentHistoryResponse.model_fields
        assert "items" in DomainAgentApprovalQueueResponse.model_fields


class TestPartFLiveRouters:
    def test_marketing_endpoints_exist(self) -> None:
        assert '@router.post("/generate"' in _MARKETING_SOURCE
        assert '@router.post("/om-report"' in _MARKETING_SOURCE

    def test_domain_agent_endpoints_exist(self) -> None:
        assert '@router.post("/run"' in _DOMAIN_AGENTS_SOURCE
        assert '@router.post("/multi-analysis"' in _DOMAIN_AGENTS_SOURCE
        assert '@router.get("/history"' in _DOMAIN_AGENTS_SOURCE
        assert '@router.get("/approvals"' in _DOMAIN_AGENTS_SOURCE
        assert 'status in {None, "all"}' in _DOMAIN_AGENTS_SOURCE
        assert "/approvals/decision-batch" in _DOMAIN_AGENTS_SOURCE
        assert "/approvals/{approval_id}/decision" in _DOMAIN_AGENTS_SOURCE


class TestPartFLiveServices:
    def test_marketing_helpers(self) -> None:
        headline = MarketingService._headline("Han River Hub", "office", "linkedin")
        body = MarketingService._body(
            project_name="Han River Hub",
            asset_type="office",
            target_audience="institutional investors",
            tone="professional",
            highlights=["transit access", "pre-leasing momentum"],
        )
        assert "Han River Hub" in headline
        assert "institutional investors" in body

    def test_domain_agent_scoring(self) -> None:
        confidence, recommendation, findings = DomainAgentsService._score(
            "Assess downside risk and capital structure.",
            {
                "ltv": 0.72,
                "occupancy_rate": 0.93,
                "schedule_buffer_months": 4,
            },
        )
        assert 0.35 <= confidence <= 0.95
        assert recommendation in {"proceed", "proceed-with-conditions", "escalate"}
        assert findings
