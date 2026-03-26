"""Compliance router for G82."""

from fastapi import APIRouter, Depends
from packages.schemas.models import (
    AMLScreeningResponse,
    ComplianceCheckResponse,
    ComplianceScreeningRequest,
    ComplianceScreeningResponse,
    KYCDocumentResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.compliance_service import ComplianceService

router = APIRouter()


@router.post("/screening", response_model=ComplianceScreeningResponse)
async def run_compliance_screening(
    body: ComplianceScreeningRequest,
    current_user: CurrentUser = Depends(RequirePermission("compliance", "write")),
    db: AsyncSession = Depends(get_db),
) -> ComplianceScreeningResponse:
    """Run KYC and AML screening for a project subject."""
    service = ComplianceService(db)
    check, screening, documents = await service.screen(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        subject_name=body.subject_name,
        check_type=body.check_type,
        transaction_amount_krw=body.transaction_amount_krw,
        politically_exposed=body.politically_exposed,
        residency_countries=body.residency_countries,
        documents=[document.model_dump() for document in body.documents],
    )
    return ComplianceScreeningResponse(
        compliance_check=ComplianceCheckResponse(
            check_id=check.id,
            project_id=check.project_id,
            check_type=check.check_type,
            status=check.status,
            score=check.score,
            findings=check.findings_json or [],
            remediation_plan=check.remediation_plan,
        ),
        aml_screening=AMLScreeningResponse(
            screening_id=screening.id,
            subject_name=screening.subject_name,
            match_status=screening.match_status,
            risk_level=screening.risk_level,
            matched_lists=list(screening.matched_lists_json or []),
            notes=screening.notes,
        ),
        kyc_documents=[
            KYCDocumentResponse(
                document_id=document.id,
                subject_name=document.subject_name,
                document_kind=document.document_kind,
                verified=document.verified,
                storage_url=document.storage_url,
            )
            for document in documents
        ],
    )
