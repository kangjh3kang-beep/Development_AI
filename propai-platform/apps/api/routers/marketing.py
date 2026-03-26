"""Marketing router for G86."""

from fastapi import APIRouter, Depends
from packages.schemas.models import (
    MarketingContentRequest,
    MarketingContentResponse,
    OMReportRequest,
    OMReportResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.marketing_service import MarketingService

router = APIRouter()


@router.post("/generate", response_model=MarketingContentResponse)
async def generate_marketing_content(
    body: MarketingContentRequest,
    current_user: CurrentUser = Depends(RequirePermission("marketing", "write")),
    db: AsyncSession = Depends(get_db),
) -> MarketingContentResponse:
    """Generate channel-specific marketing content."""
    service = MarketingService(db)
    content = await service.generate_content(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        project_name=body.project_name,
        channel=body.channel,
        asset_type=body.asset_type,
        target_audience=body.target_audience,
        tone=body.tone,
        highlights=body.highlights,
    )
    return MarketingContentResponse(
        content_id=content.id,
        project_id=content.project_id,
        channel=content.channel,
        headline=content.headline,
        body=content.body,
        call_to_action=content.call_to_action,
        created_at=content.created_at,
    )


@router.post("/om-report", response_model=OMReportResponse)
async def generate_offering_memorandum(
    body: OMReportRequest,
    current_user: CurrentUser = Depends(RequirePermission("marketing", "write")),
    db: AsyncSession = Depends(get_db),
) -> OMReportResponse:
    """Generate an offering memorandum."""
    service = MarketingService(db)
    memorandum = await service.generate_om_report(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        project_name=body.project_name,
        asset_type=body.asset_type,
        investment_highlights=body.investment_highlights,
        target_audience=body.target_audience,
        risk_factors=body.risk_factors,
        output_format=body.output_format,
    )
    return OMReportResponse(
        memorandum_id=memorandum.id,
        project_id=memorandum.project_id,
        title=memorandum.title,
        executive_summary=memorandum.executive_summary,
        sections=memorandum.sections_json,
        risk_factors=list(memorandum.risk_factors_json or []),
        output_format=memorandum.output_format,
        created_at=memorandum.created_at,
    )
