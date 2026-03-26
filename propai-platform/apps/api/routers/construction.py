"""시공/ESG AI 라우터.

BIM4D 시공 일정 생성, ZEB 에너지 시뮬레이션, 기후 리스크 분석, 하자 분류.
"""

from fastapi import APIRouter, Depends
from packages.schemas.models import (
    ClimateRiskRequest,
    ClimateRiskResponse,
    ConstructionScheduleRequest,
    ConstructionScheduleResponse,
    DefectClassificationRequest,
    DefectClassificationResponse,
    ZEBEnergyRequest,
    ZEBEnergyResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.construction_ai_service import ConstructionAIService

router = APIRouter()


@router.post("/schedule", response_model=ConstructionScheduleResponse)
async def generate_schedule(
    body: ConstructionScheduleRequest,
    current_user: CurrentUser = Depends(RequirePermission("design", "read")),
    db: AsyncSession = Depends(get_db),
) -> ConstructionScheduleResponse:
    """표준품셈 기반 13공정 시공 일정을 생성한다."""
    service = ConstructionAIService(db)
    result = service.generate_construction_schedule(
        total_area_sqm=body.total_area_sqm,
        floors_above=body.floors_above,
        floors_below=body.floors_below,
        structure_type=body.structure_type,
    )
    return ConstructionScheduleResponse(**result)


@router.post("/zeb-energy", response_model=ZEBEnergyResponse)
async def estimate_zeb_energy(
    body: ZEBEnergyRequest,
    current_user: CurrentUser = Depends(RequirePermission("design", "read")),
    db: AsyncSession = Depends(get_db),
) -> ZEBEnergyResponse:
    """ZEB 에너지 시뮬레이션을 수행한다."""
    service = ConstructionAIService(db)
    result = service.estimate_zeb_energy(
        total_area_sqm=body.total_area_sqm,
        floors=body.floors,
        window_wall_ratio=body.window_wall_ratio,
        insulation_grade=body.insulation_grade,
    )
    return ZEBEnergyResponse(**result)


@router.post("/climate-risk", response_model=ClimateRiskResponse)
async def analyze_climate_risk(
    body: ClimateRiskRequest,
    current_user: CurrentUser = Depends(RequirePermission("design", "read")),
    db: AsyncSession = Depends(get_db),
) -> ClimateRiskResponse:
    """기후 리스크를 분석한다."""
    service = ConstructionAIService(db)
    result = await service.analyze_climate_risk(
        project_id=body.project_id,
        lat=body.lat,
        lon=body.lon,
        construction_period_months=body.construction_period_months,
    )
    return ClimateRiskResponse(**result)


@router.post("/defect-classify", response_model=DefectClassificationResponse)
async def classify_defect(
    body: DefectClassificationRequest,
    current_user: CurrentUser = Depends(RequirePermission("design", "write")),
    db: AsyncSession = Depends(get_db),
) -> DefectClassificationResponse:
    """하자 사진을 AI로 분류한다."""
    service = ConstructionAIService(db)
    result = await service.classify_defect_image(
        project_id=body.project_id,
        image_url=body.image_url,
        location=body.location,
    )
    return DefectClassificationResponse(**result)
