"""v53 smart contract generation and e-sign handoff router."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from packages.schemas.models import (
    ContractDraftResponse,
    ContractESignRequest,
    ContractGenerationRequest,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.contract_generator import ContractGeneratorService

router = APIRouter()


@router.post("/generate", response_model=ContractDraftResponse, status_code=status.HTTP_201_CREATED)
async def generate_contract_draft(
    body: ContractGenerationRequest,
    current_user: CurrentUser = Depends(RequirePermission("contracts", "write")),
    db: AsyncSession = Depends(get_db),
) -> ContractDraftResponse:
    service = ContractGeneratorService(db)
    try:
        result = await service.generate_draft(
            tenant_id=current_user.tenant_id,
            project_id=body.project_id,
            contract_type=body.contract_type,
            target_language=body.target_language,
            counterparty_name=body.counterparty_name,
            effective_date=body.effective_date,
            contract_amount_krw=body.contract_amount_krw,
            special_clauses=body.special_clauses,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ContractDraftResponse.model_validate(result)


@router.get("/{project_id}/latest", response_model=ContractDraftResponse)
async def get_latest_contract_draft(
    project_id: UUID,
    contract_type: str | None = Query(default=None, max_length=50),
    current_user: CurrentUser = Depends(RequirePermission("contracts", "read")),
    db: AsyncSession = Depends(get_db),
) -> ContractDraftResponse:
    service = ContractGeneratorService(db)
    try:
        result = await service.get_latest(
            tenant_id=current_user.tenant_id,
            project_id=project_id,
            contract_type=contract_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Latest contract draft was not found",
        )

    return ContractDraftResponse.model_validate(result)


@router.post("/{draft_id}/esign", response_model=ContractDraftResponse)
async def handoff_contract_to_esign(
    draft_id: UUID,
    body: ContractESignRequest,
    current_user: CurrentUser = Depends(RequirePermission("contracts", "write")),
    db: AsyncSession = Depends(get_db),
) -> ContractDraftResponse:
    service = ContractGeneratorService(db)
    try:
        result = await service.request_esign(
            tenant_id=current_user.tenant_id,
            draft_id=draft_id,
            signer_name=body.signer_name,
            signer_email=body.signer_email,
            signer_phone=body.signer_phone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ContractDraftResponse.model_validate(result)
