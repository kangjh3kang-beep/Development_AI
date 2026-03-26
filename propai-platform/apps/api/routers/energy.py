"""Energy estimation endpoints for v43 rollout."""

from fastapi import APIRouter, Depends
from packages.schemas.models import (
    EnergyCertificationRequest,
    EnergyCertificationResponse,
    KepcoCalculationRequest,
    KepcoCalculationResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.energy_service import EnergyService

router = APIRouter()


@router.post("/kepco/calculate", response_model=KepcoCalculationResponse)
async def calculate_kepco_bill(
    body: KepcoCalculationRequest,
    current_user: CurrentUser = Depends(RequirePermission("energy", "read")),
    db: AsyncSession = Depends(get_db),
) -> KepcoCalculationResponse:
    service = EnergyService(db)
    result = await service.calculate_kepco_bill(
        tenant_id=current_user.tenant_id,
        usage_kwh=body.usage_kwh,
        contract_type=body.contract_type,
        demand_kw=body.demand_kw,
    )
    return KepcoCalculationResponse(**result)


@router.post("/certification", response_model=EnergyCertificationResponse)
async def estimate_energy_certification(
    body: EnergyCertificationRequest,
    current_user: CurrentUser = Depends(RequirePermission("energy", "read")),
    db: AsyncSession = Depends(get_db),
) -> EnergyCertificationResponse:
    service = EnergyService(db)
    record = await service.certify_energy(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        total_area_sqm=body.total_area_sqm,
        floors=body.floors,
        window_wall_ratio=body.window_wall_ratio,
        insulation_grade=body.insulation_grade,
        bems_saving_rate=body.bems_saving_rate,
    )

    return EnergyCertificationResponse(
        energy_grade=record.energy_grade,
        zeb_grade=record.zeb_grade,
        annual_energy_demand_kwh=record.annual_energy_demand_kwh,
        annual_renewable_generation_kwh=record.annual_renewable_generation_kwh,
        energy_independence_rate=record.energy_independence_rate,
        bems_saving_rate=record.bems_saving_rate,
        bems_saving_kwh=record.bems_saving_kwh,
        recommendations=list(record.recommendations_json or []),
    )
