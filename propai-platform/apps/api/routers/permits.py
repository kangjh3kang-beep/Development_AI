"""Permit submission and tracking router for v53."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from packages.schemas.models import PermitStatusResponse, PermitSubmissionRequest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.seumter_permit_service import SeumterPermitService

router = APIRouter()


@router.get("/{project_id}/status")
async def get_project_permit_status(project_id: str) -> dict:
    """프로젝트 인허가 상태 조회."""
    return {
        "project_id": project_id,
        "stages": [
            {"name": "사전검토", "status": "completed", "date": "2026-01-15"},
            {"name": "건축허가", "status": "in_progress", "date": None},
            {"name": "착공신고", "status": "pending", "date": None},
            {"name": "사용승인", "status": "pending", "date": None},
        ],
        "current_stage": "건축허가",
        "overall_progress_pct": 25,
        "documents_submitted": 3,
        "documents_required": 12,
    }


@router.post("/submit", response_model=PermitStatusResponse)
async def submit_permit(
    body: PermitSubmissionRequest,
    current_user: CurrentUser = Depends(RequirePermission("permits", "write")),
    db: AsyncSession = Depends(get_db),
) -> PermitStatusResponse:
    service = SeumterPermitService(db)
    result = await service.submit(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        permit_type=body.permit_type,
        region=body.region,
        building_area_sqm=body.building_area_sqm,
        is_public=body.is_public,
        is_agricultural=body.is_agricultural,
        applicant_name=body.applicant_name,
        submit_to_seumter=body.submit_to_seumter,
        submitted_document_ids=body.submitted_document_ids,
    )
    return PermitStatusResponse.model_validate(result)


@router.get("/{project_id}/latest", response_model=PermitStatusResponse)
async def get_latest_permit(
    project_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("permits", "read")),
    db: AsyncSession = Depends(get_db),
) -> PermitStatusResponse:
    service = SeumterPermitService(db)
    result = await service.get_latest(
        tenant_id=current_user.tenant_id,
        project_id=project_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Latest permit submission was not found",
        )
    return PermitStatusResponse.model_validate(result)


@router.get("/submissions/{submission_id}/status", response_model=PermitStatusResponse)
async def get_permit_status(
    submission_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("permits", "read")),
    db: AsyncSession = Depends(get_db),
) -> PermitStatusResponse:
    service = SeumterPermitService(db)
    result = await service.get_status(
        tenant_id=current_user.tenant_id,
        submission_id=submission_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permit submission was not found",
        )
    return PermitStatusResponse.model_validate(result)
