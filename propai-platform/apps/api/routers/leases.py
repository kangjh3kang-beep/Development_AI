"""Lease router for G83."""

from fastapi import APIRouter, Depends
from packages.schemas.models import (
    LeaseAbstractionResponse,
    LeaseAnalysisRequest,
    LeaseAnalysisResponse,
    LeaseIFRS16ScheduleResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.lease_service import LeaseService

router = APIRouter()


@router.post("/analyze", response_model=LeaseAnalysisResponse)
async def analyze_lease_contract(
    body: LeaseAnalysisRequest,
    current_user: CurrentUser = Depends(RequirePermission("leases", "write")),
    db: AsyncSession = Depends(get_db),
) -> LeaseAnalysisResponse:
    """Create lease abstraction and IFRS16 schedule."""
    service = LeaseService(db)
    abstraction, schedule = await service.analyze(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        source_document_name=body.source_document_name,
        tenant_name=body.tenant_name,
        lease_type=body.lease_type,
        area_sqm=body.area_sqm,
        deposit_krw=body.deposit_krw,
        monthly_rent_krw=body.monthly_rent_krw,
        start_date=body.start_date,
        end_date=body.end_date,
        discount_rate=body.discount_rate,
        critical_terms=body.critical_terms,
        abstraction_text=body.abstraction_text,
    )
    return LeaseAnalysisResponse(
        abstraction=LeaseAbstractionResponse(
            abstraction_id=abstraction.id,
            project_id=abstraction.project_id,
            tenant_name=abstraction.tenant_name,
            lease_type=abstraction.lease_type,
            area_sqm=abstraction.area_sqm,
            deposit_krw=abstraction.deposit_krw,
            monthly_rent_krw=abstraction.monthly_rent_krw,
            critical_terms=abstraction.critical_terms_json or [],
        ),
        ifrs16_schedule=LeaseIFRS16ScheduleResponse(
            schedule_id=schedule.id,
            project_id=schedule.project_id,
            lease_term_months=schedule.lease_term_months,
            discount_rate=schedule.discount_rate,
            rou_asset_krw=schedule.rou_asset_krw,
            lease_liability_krw=schedule.lease_liability_krw,
            payment_schedule=schedule.payment_schedule_json,
        ),
    )
