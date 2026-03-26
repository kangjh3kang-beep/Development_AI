"""Contractor network router for G95."""

from fastapi import APIRouter, Depends, Query
from packages.schemas.models import (
    ContractorCreateRequest,
    ContractorRecommendationItem,
    ContractorRecommendationRequest,
    ContractorRecommendationResponse,
    ContractorResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.contractor_service import ContractorService

router = APIRouter()


def _serialize_contractor(contractor) -> ContractorResponse:
    return ContractorResponse(
        contractor_id=contractor.id,
        company_name=contractor.company_name,
        business_number=contractor.business_number,
        category=contractor.category,
        specialties=list(contractor.specialties_json or []),
        contact_name=contractor.contact_name,
        contact_phone=contractor.contact_phone,
        contact_email=contractor.contact_email,
        address=contractor.address,
        rating=contractor.rating,
        is_active=contractor.is_active,
        created_at=contractor.created_at,
    )


@router.post("/register", response_model=ContractorResponse)
async def register_contractor(
    body: ContractorCreateRequest,
    current_user: CurrentUser = Depends(RequirePermission("contractors", "write")),
    db: AsyncSession = Depends(get_db),
) -> ContractorResponse:
    service = ContractorService(db)
    contractor = await service.upsert_contractor(
        tenant_id=current_user.tenant_id,
        company_name=body.company_name,
        business_number=body.business_number,
        category=body.category,
        specialties=body.specialties,
        contact_name=body.contact_name,
        contact_phone=body.contact_phone,
        contact_email=body.contact_email,
        address=body.address,
        rating=body.rating,
        notes=body.notes,
    )
    return _serialize_contractor(contractor)


@router.get("/active", response_model=list[ContractorResponse])
async def list_active_contractors(
    category: str | None = None,
    limit: int = Query(default=10, ge=1, le=50),
    current_user: CurrentUser = Depends(RequirePermission("contractors", "read")),
    db: AsyncSession = Depends(get_db),
) -> list[ContractorResponse]:
    service = ContractorService(db)
    contractors = await service.list_active(
        tenant_id=current_user.tenant_id,
        category=category,
        limit=limit,
    )
    return [_serialize_contractor(contractor) for contractor in contractors]


@router.post("/recommend", response_model=ContractorRecommendationResponse)
async def recommend_contractors(
    body: ContractorRecommendationRequest,
    current_user: CurrentUser = Depends(RequirePermission("contractors", "read")),
    db: AsyncSession = Depends(get_db),
) -> ContractorRecommendationResponse:
    service = ContractorService(db)
    recommendations = await service.recommend(
        tenant_id=current_user.tenant_id,
        category=body.category,
        required_specialties=body.required_specialties,
        region_hint=body.region_hint,
        max_results=body.max_results,
    )
    return ContractorRecommendationResponse(
        category=body.category,
        recommendations=[
            ContractorRecommendationItem(
                contractor_id=item["contractor"].id,
                company_name=item["contractor"].company_name,
                category=item["contractor"].category,
                specialties=list(item["contractor"].specialties_json or []),
                rating=item["contractor"].rating,
                match_score=item["match_score"],
                reasons=item["reasons"],
            )
            for item in recommendations
        ],
    )
