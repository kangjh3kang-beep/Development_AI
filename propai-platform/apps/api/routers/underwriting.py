"""Underwriting router for G81."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from packages.schemas.models import UnderwritingRequest, UnderwritingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.underwriting_service import UnderwritingService

router = APIRouter()


@router.get("/history", response_model=list[UnderwritingResponse])
async def list_underwriting_history(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(RequirePermission("underwriting", "read")),
    db: AsyncSession = Depends(get_db),
) -> list[UnderwritingResponse]:
    """List tenant underwriting history."""
    service = UnderwritingService(db)
    records = await service.list_history(tenant_id=current_user.tenant_id, limit=limit)
    return [
        UnderwritingResponse(
            underwriting_id=record.id,
            project_id=record.project_id,
            project_name=record.project_name,
            risk_level=record.risk_level,
            risk_score=record.risk_score,
            recommendation=record.recommendation,
            projected_profit_krw=record.projected_profit_krw,
            profit_margin_ratio=record.profit_margin_ratio,
            debt_ratio=record.debt_ratio,
            equity_multiple=record.equity_multiple,
            jeonse_ratio=record.jeonse_ratio,
            key_risks=record.key_risks or [],
            narrative=record.narrative or "",
            created_at=record.created_at,
        )
        for record in records
    ]


@router.post("/{project_id}", response_model=UnderwritingResponse)
async def create_underwriting(
    project_id: UUID,
    body: UnderwritingRequest,
    current_user: CurrentUser = Depends(RequirePermission("underwriting", "write")),
    db: AsyncSession = Depends(get_db),
) -> UnderwritingResponse:
    """Create an underwriting assessment for a project."""
    if body.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path project_id does not match request body project_id",
        )

    service = UnderwritingService(db)
    record = await service.create_underwriting(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        project_name=body.project_name,
        total_cost_krw=body.total_cost_krw,
        projected_revenue_krw=body.projected_revenue_krw,
        acquisition_price_krw=body.acquisition_price_krw,
        equity_krw=body.equity_krw,
        debt_krw=body.debt_krw,
        jeonse_ratio=body.jeonse_ratio,
        assumptions_json=body.assumptions_json,
        data_room_documents=[document.model_dump() for document in body.data_room_documents],
    )
    return UnderwritingResponse(
        underwriting_id=record.id,
        project_id=record.project_id,
        project_name=record.project_name,
        risk_level=record.risk_level,
        risk_score=record.risk_score,
        recommendation=record.recommendation,
        projected_profit_krw=record.projected_profit_krw,
        profit_margin_ratio=record.profit_margin_ratio,
        debt_ratio=record.debt_ratio,
        equity_multiple=record.equity_multiple,
        jeonse_ratio=record.jeonse_ratio,
        key_risks=record.key_risks or [],
        narrative=record.narrative or "",
        created_at=record.created_at,
    )
