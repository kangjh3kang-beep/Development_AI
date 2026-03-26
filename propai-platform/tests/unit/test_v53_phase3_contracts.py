"""Regression tests for v53 phase 3 contract automation and i18n hardening."""

from datetime import UTC, datetime
from pathlib import Path

from apps.api.auth.rbac import check_permission
from apps.api.services.contract_generator import ContractGeneratorService
from packages.schemas.models import (
    ContractClauseResponse,
    ContractDraftResponse,
    ContractESignRequest,
    ContractGenerationRequest,
)

_BASE = Path(__file__).resolve().parents[2]
_MAIN_SOURCE = (_BASE / "apps" / "api" / "main.py").read_text(encoding="utf-8")
_CONTRACTS_SOURCE = (
    _BASE / "apps" / "api" / "routers" / "contracts.py"
).read_text(encoding="utf-8")


class TestV53Phase3Contracts:
    def test_contract_request_contract_fields(self) -> None:
        assert "target_language" in ContractGenerationRequest.model_fields
        assert "special_clauses" in ContractGenerationRequest.model_fields
        assert "signer_email" in ContractESignRequest.model_fields

    def test_contract_response_fields(self) -> None:
        assert "sign_status" in ContractDraftResponse.model_fields
        assert "esign_request_id" in ContractDraftResponse.model_fields
        assert "title" in ContractClauseResponse.model_fields


class TestV53Phase3Routers:
    def test_main_registers_contract_router(self) -> None:
        assert 'prefix="/api/v1/contracts"' in _MAIN_SOURCE

    def test_contract_endpoints_exist(self) -> None:
        assert '@router.post("/generate"' in _CONTRACTS_SOURCE
        assert '@router.get("/{project_id}/latest"' in _CONTRACTS_SOURCE
        assert '@router.post("/{draft_id}/esign"' in _CONTRACTS_SOURCE


class TestV53Phase3ServiceLogic:
    def test_language_normalization_and_contract_label(self) -> None:
        assert ContractGeneratorService._normalize_language("fr") == "ko"
        assert (
            ContractGeneratorService._contract_type_label("construction", "en")
            == "Construction agreement"
        )

    def test_multilingual_clause_generation(self) -> None:
        effective_date = datetime(2026, 4, 1, tzinfo=UTC)
        clauses = ContractGeneratorService._build_clauses(
            project_name="Seongsu Innovation Hub",
            contract_type="construction",
            language="zh-CN",
            counterparty_name="Hanbit Contractors",
            effective_date=effective_date,
            contract_amount_krw=4_500_000_000,
            special_clauses=["夜间施工需提前报备"],
        )
        assert len(clauses) == 5
        assert any("电子签署" in clause["body"] for clause in clauses)
        assert any("夜间施工需提前报备" in clause["body"] for clause in clauses)

    def test_markdown_rendering_contains_terms_and_sections(self) -> None:
        markdown = ContractGeneratorService._render_markdown(
            title="Mapo Prime Lease agreement",
            summary="Lease summary",
            key_terms=[{"label": "Counterparty", "value": "Tenant A"}],
            clauses=[{"title": "Purpose", "body": "Define the leased premises."}],
        )
        assert markdown.startswith("# Mapo Prime Lease agreement")
        assert "## Key Terms" in markdown
        assert "## Purpose" in markdown


class TestV53Phase3Rbac:
    def test_viewer_can_read_contracts(self) -> None:
        assert check_permission("viewer", "contracts", "read") is True

    def test_analyst_can_write_contracts(self) -> None:
        assert check_permission("analyst", "contracts", "write") is True
