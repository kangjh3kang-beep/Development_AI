"""Mock e-sign endpoints."""

import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from packages.schemas.models import ESignCreateRequest, ESignResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.models.esign_request import ESignRequest
from apps.api.database.session import get_db

router = APIRouter()


def _to_response(request: ESignRequest) -> ESignResponse:
    return ESignResponse(
        id=request.id,
        project_id=request.project_id,
        document_name=request.document_name,
        document_url=request.document_url,
        signer_name=request.signer_name,
        signer_email=request.signer_email,
        signer_phone=request.signer_phone,
        provider=request.provider,
        status=request.status,
        external_request_id=request.external_request_id,
        requested_at=request.requested_at,
        completed_at=request.completed_at,
        created_at=request.created_at,
    )


async def _get_request_or_404(
    request_id: UUID,
    tenant_id: UUID,
    db: AsyncSession,
) -> ESignRequest:
    result = await db.execute(
        select(ESignRequest).where(
            ESignRequest.id == request_id,
            ESignRequest.tenant_id == tenant_id,
        )
    )
    request = result.scalar_one_or_none()
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="E-sign request not found",
        )
    return request


@router.post("/request", response_model=ESignResponse, status_code=status.HTTP_201_CREATED)
async def create_esign_request(
    body: ESignCreateRequest,
    current_user: CurrentUser = Depends(RequirePermission("esign", "write")),
    db: AsyncSession = Depends(get_db),
) -> ESignResponse:
    request = ESignRequest(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        document_name=body.document_name,
        document_url=body.document_url,
        signer_name=body.signer_name,
        signer_email=body.signer_email,
        signer_phone=body.signer_phone,
        provider="mock",
        status="requested",
        external_request_id=f"esign_{secrets.token_hex(8)}",
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)
    return _to_response(request)


@router.get("/{request_id}/status", response_model=ESignResponse)
async def get_esign_status(
    request_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("esign", "read")),
    db: AsyncSession = Depends(get_db),
) -> ESignResponse:
    request = await _get_request_or_404(request_id, current_user.tenant_id, db)
    return _to_response(request)
