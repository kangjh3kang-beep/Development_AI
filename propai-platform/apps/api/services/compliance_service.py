"""Compliance service for KYC and AML workflows."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.phase_e_compliance import AMLScreening, ComplianceCheck, KYCDocument

_HIGH_RISK_COUNTRIES = {"IR", "KP", "RU", "SY", "MM"}
_VERIFIED_DOCUMENT_KINDS = {"passport", "id-card", "business-license", "corporate-registry"}


class ComplianceService:
    """Create compliance screening records using deterministic heuristics."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _score_aml_risk(
        *,
        transaction_amount_krw: float,
        politically_exposed: bool,
        residency_countries: list[str],
        document_count: int,
    ) -> tuple[float, str, str, list[str], str]:
        score = 18.0
        matched_lists: list[str] = []

        if transaction_amount_krw >= 20_000_000_000:
            score += 34
            matched_lists.append("large-cashflow")
        elif transaction_amount_krw >= 5_000_000_000:
            score += 22
            matched_lists.append("enhanced-dd")
        elif transaction_amount_krw >= 1_000_000_000:
            score += 10

        if politically_exposed:
            score += 24
            matched_lists.append("pep-screening")

        high_risk_hits = sorted(
            {country.upper() for country in residency_countries if country.upper() in _HIGH_RISK_COUNTRIES}
        )
        if high_risk_hits:
            score += 20 + min(10, len(high_risk_hits) * 2)
            matched_lists.extend([f"country:{country}" for country in high_risk_hits])

        if document_count == 0:
            score += 18
            matched_lists.append("missing-docs")
        elif document_count == 1:
            score += 8

        bounded = max(0.0, min(100.0, score))
        if bounded >= 75:
            return (
                bounded, "high", "hit", matched_lists,
                "Escalate to compliance officer and require source-of-funds review.",
            )
        if bounded >= 50:
            return (
                bounded, "medium", "review", matched_lists,
                "Run enhanced due diligence and confirm beneficial ownership.",
            )
        return bounded, "low", "clear", matched_lists, "Standard monitoring is sufficient."

    async def screen(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        subject_name: str,
        check_type: str,
        transaction_amount_krw: float,
        politically_exposed: bool,
        residency_countries: list[str],
        documents: list[dict],
    ) -> tuple[ComplianceCheck, AMLScreening, list[KYCDocument]]:
        score, risk_level, match_status, matched_lists, remediation_plan = self._score_aml_risk(
            transaction_amount_krw=transaction_amount_krw,
            politically_exposed=politically_exposed,
            residency_countries=residency_countries,
            document_count=len(documents),
        )

        findings = [
            {"factor": "transaction-amount", "value": transaction_amount_krw},
            {"factor": "politically-exposed", "value": politically_exposed},
            {"factor": "residency-countries", "value": residency_countries},
        ]
        if not documents:
            findings.append({"factor": "documentation", "value": "missing"})

        check = ComplianceCheck(
            tenant_id=tenant_id,
            project_id=project_id,
            check_type=check_type,
            status="completed" if match_status == "clear" else "review",
            score=round(score, 2),
            findings_json=findings,
            remediation_plan=remediation_plan,
        )
        self.db.add(check)

        screening = AMLScreening(
            tenant_id=tenant_id,
            project_id=project_id,
            subject_name=subject_name,
            provider="internal",
            match_status=match_status,
            risk_level=risk_level,
            matched_lists_json=matched_lists,
            notes=remediation_plan,
        )
        self.db.add(screening)
        await self.db.flush()

        stored_documents: list[KYCDocument] = []
        for document in documents:
            document_kind = str(document["document_kind"]).lower()
            stored = KYCDocument(
                tenant_id=tenant_id,
                project_id=project_id,
                subject_name=subject_name,
                document_kind=document_kind,
                identifier_masked=document.get("identifier_masked"),
                storage_url=str(document["storage_url"]),
                verified=document_kind in _VERIFIED_DOCUMENT_KINDS,
                metadata_json={"file_name": document["file_name"]},
            )
            self.db.add(stored)
            stored_documents.append(stored)

        await self.db.commit()
        await self.db.refresh(check)
        await self.db.refresh(screening)
        return check, screening, stored_documents
