"""Cost intelligence router for v53 material prices and escalation."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from packages.schemas.models import (
    CostEscalationRequest,
    CostEscalationResponse,
    MaterialPriceRefreshRequest,
    MaterialPriceSnapshotResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.cost_escalation_engine import CostEscalationEngine
from apps.api.services.kcci_material_price_service import KCCIMaterialPriceService

router = APIRouter()


def _split_material_codes(material_codes: str | None) -> list[str] | None:
    if material_codes is None:
        return None
    codes = [code.strip() for code in material_codes.split(",") if code.strip()]
    return codes or None


@router.post("/material-prices/refresh", response_model=MaterialPriceSnapshotResponse)
async def refresh_material_prices(
    body: MaterialPriceRefreshRequest,
    current_user: CurrentUser = Depends(RequirePermission("cost_intelligence", "write")),
    db: AsyncSession = Depends(get_db),
) -> MaterialPriceSnapshotResponse:
    service = KCCIMaterialPriceService(db)
    result = await service.refresh_snapshot(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        material_codes=body.material_codes,
        region_code=body.region_code,
    )
    return MaterialPriceSnapshotResponse.model_validate(result)


@router.get("/material-prices/latest", response_model=MaterialPriceSnapshotResponse)
async def get_latest_material_prices(
    project_id: UUID | None = None,
    region_code: str = Query(default="KR", min_length=2, max_length=20),
    material_codes: str | None = None,
    current_user: CurrentUser = Depends(RequirePermission("cost_intelligence", "read")),
    db: AsyncSession = Depends(get_db),
) -> MaterialPriceSnapshotResponse:
    service = KCCIMaterialPriceService(db)
    result = await service.get_latest_snapshot(
        tenant_id=current_user.tenant_id,
        project_id=project_id,
        material_codes=_split_material_codes(material_codes),
        region_code=region_code,
    )
    return MaterialPriceSnapshotResponse.model_validate(result)


@router.post("/escalation/analyze", response_model=CostEscalationResponse)
async def analyze_cost_escalation(
    body: CostEscalationRequest,
    current_user: CurrentUser = Depends(RequirePermission("cost_intelligence", "write")),
    db: AsyncSession = Depends(get_db),
) -> CostEscalationResponse:
    engine = CostEscalationEngine(db)
    try:
        result = await engine.analyze(
            tenant_id=current_user.tenant_id,
            project_id=body.project_id,
            base_construction_cost_krw=body.base_construction_cost_krw,
            baseline_year=body.baseline_year,
            target_year=body.target_year,
            construction_duration_months=body.construction_duration_months,
            material_share_ratio=body.material_share_ratio,
            labor_share_ratio=body.labor_share_ratio,
            overhead_share_ratio=body.overhead_share_ratio,
            contingency_ratio=body.contingency_ratio,
            material_codes=body.material_codes,
            region_code=body.region_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return CostEscalationResponse.model_validate(result)


@router.get("/escalation/{project_id}/latest", response_model=CostEscalationResponse)
async def get_latest_cost_escalation(
    project_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("cost_intelligence", "read")),
    db: AsyncSession = Depends(get_db),
) -> CostEscalationResponse:
    engine = CostEscalationEngine(db)
    result = await engine.get_latest(
        tenant_id=current_user.tenant_id,
        project_id=project_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Latest cost escalation scenario was not found",
        )
    return CostEscalationResponse.model_validate(result)
