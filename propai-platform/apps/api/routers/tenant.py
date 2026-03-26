"""Tenant experience router for G89."""

from fastapi import APIRouter, Depends
from packages.schemas.models import (
    TenantFeedbackRequest,
    TenantFeedbackResponse,
    TenantSatisfactionRequest,
    TenantSatisfactionResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.tenant_experience_service import TenantExperienceService

router = APIRouter()


@router.post("/feedback/analyze", response_model=TenantFeedbackResponse)
async def analyze_tenant_feedback(
    body: TenantFeedbackRequest,
    current_user: CurrentUser = Depends(RequirePermission("tenant_experience", "write")),
    db: AsyncSession = Depends(get_db),
) -> TenantFeedbackResponse:
    """Analyze tenant feedback and generate an AI reply."""
    service = TenantExperienceService(db)
    ticket, sentiment = await service.analyze_feedback(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        unit_label=body.unit_label,
        category=body.category,
        feedback_text=body.feedback_text,
        satisfaction_rating=body.satisfaction_rating,
    )
    return TenantFeedbackResponse(
        ticket_id=ticket.id,
        project_id=ticket.project_id,
        sentiment_score=sentiment.sentiment_score,
        sentiment_label=sentiment.sentiment_label,
        ai_reply=sentiment.ai_reply or "",
        created_at=sentiment.created_at,
    )


@router.post("/satisfaction/nps", response_model=TenantSatisfactionResponse)
async def calculate_tenant_satisfaction(
    body: TenantSatisfactionRequest,
    current_user: CurrentUser = Depends(RequirePermission("tenant_experience", "write")),
    db: AsyncSession = Depends(get_db),
) -> TenantSatisfactionResponse:
    """Calculate NPS and tenant financial health."""
    service = TenantExperienceService(db)
    health, nps = await service.calculate_satisfaction(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        promoter_count=body.promoter_count,
        passive_count=body.passive_count,
        detractor_count=body.detractor_count,
        occupancy_rate=body.occupancy_rate,
        arrears_ratio=body.arrears_ratio,
    )
    return TenantSatisfactionResponse(
        financial_health_id=health.id,
        project_id=health.project_id,
        nps=nps,
        churn_risk_score=health.churn_risk_score,
        health_grade=health.health_grade,
        created_at=health.created_at,
    )
