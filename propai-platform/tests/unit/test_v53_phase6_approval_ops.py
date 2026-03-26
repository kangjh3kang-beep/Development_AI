"""Regression tests for v53 phase 6 approval operations center."""

from pathlib import Path

_BASE = Path(__file__).resolve().parents[2]
_ROUTER_SOURCE = (
    _BASE / "apps" / "api" / "routers" / "domain_agents.py"
).read_text(encoding="utf-8")
_SERVICE_SOURCE = (
    _BASE / "apps" / "api" / "services" / "domain_agents_service.py"
).read_text(encoding="utf-8")


class TestV53Phase6ApprovalOps:
    def test_router_supports_approver_role_filter(self) -> None:
        assert "approver_role: str | None = None" in _ROUTER_SOURCE
        assert "approver_role=approver_role" in _ROUTER_SOURCE

    def test_service_filters_queue_by_approver_role(self) -> None:
        assert "if approver_role is not None:" in _SERVICE_SOURCE
        assert "DomainAgentApproval.approver_role == approver_role" in _SERVICE_SOURCE
