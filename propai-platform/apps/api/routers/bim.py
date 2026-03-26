"""BIM/IFC 라우터.

IFC 파일 업로드/분석, 물량산출, Three.js geometry 변환, 탄소 배출량 산출.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from packages.schemas.models import (
    BIMQuantityResponse,
    CarbonCalculationRequest,
    CarbonCalculationResponse,
)
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.bim_ifc_service import BIMIFCService
from apps.api.services.carbon_calculation_service import CarbonCalculationService

router = APIRouter()


class IFCGenerateRequest(BaseModel):
    """IFC 자동 생성 요청."""

    project_id: UUID
    total_area_sqm: float = 1000.0
    floors: int = 10
    structure_type: str = "RC"


@router.post("/analyze", response_model=BIMQuantityResponse)
async def analyze_ifc(
    project_id: UUID,
    file_url: str,
    current_user: CurrentUser = Depends(RequirePermission("design", "write")),
    db: AsyncSession = Depends(get_db),
) -> BIMQuantityResponse:
    """IFC 파일을 분석하여 물량산출 결과를 반환한다.

    목표: 물량산출 오차 ≤ 2% (CoVe O1).
    """
    service = BIMIFCService(db)
    return await service.analyze_ifc(
        project_id=project_id,
        tenant_id=current_user.tenant_id,
        file_url=file_url,
    )


@router.post("/carbon", response_model=CarbonCalculationResponse)
async def calculate_carbon(
    body: CarbonCalculationRequest,
    current_user: CurrentUser = Depends(RequirePermission("design", "read")),
    db: AsyncSession = Depends(get_db),
) -> CarbonCalculationResponse:
    """건축자재별 탄소 배출량을 산출한다."""
    service = CarbonCalculationService(db)
    result = await service.calculate(
        project_id=body.project_id,
        tenant_id=current_user.tenant_id,
        material_breakdown=body.material_breakdown,
        total_area_sqm=body.total_area_sqm,
    )
    return CarbonCalculationResponse(
        total_embodied_carbon=result.total_embodied_carbon,
        total_operational_carbon=result.total_operational_carbon,
        total_carbon=result.total_carbon,
        breakdown=result.breakdown,
        reduction_tips=result.reduction_tips,
    )


@router.get("/threejs/{project_id}")
async def get_threejs_geometry(
    project_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("design", "read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Three.js BufferGeometry JSON을 반환한다.

    프로젝트에 연결된 IFC 파일을 파싱하여
    Three.js 뷰어용 geometry 데이터를 생성한다.
    목표: 1,000요소 ≤ 5초 로딩 (CoVe O5).
    """
    # DB에서 프로젝트의 최신 BIM 설계 조회
    row = await db.execute(
        text(
            "SELECT file_url FROM designs "
            "WHERE project_id = :pid AND design_type = 'bim_ifc' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"pid": str(project_id)},
    )
    record = row.fetchone()
    if not record or not record.file_url:
        raise HTTPException(status_code=404, detail="해당 프로젝트의 IFC 파일이 없습니다")

    service = BIMIFCService(db)
    filepath = await service._download_ifc(record.file_url)

    try:
        geometry = service._generate_threejs_geometry(filepath)
    finally:
        import os
        os.unlink(filepath)

    return {
        "project_id": str(project_id),
        "format": "threejs_buffergeometry",
        "total_elements": geometry["count"],
        "geometries": geometry["geometries"],
    }


@router.post("/generate-ifc", response_model=BIMQuantityResponse)
async def generate_ifc(
    body: IFCGenerateRequest,
    current_user: CurrentUser = Depends(RequirePermission("design", "write")),
    db: AsyncSession = Depends(get_db),
) -> BIMQuantityResponse:
    """설계 파라미터로 IFC 파일을 자동 생성한다."""
    service = BIMIFCService(db)
    return await service.generate_ifc_from_design(
        project_id=body.project_id,
        tenant_id=current_user.tenant_id,
        total_area_sqm=body.total_area_sqm,
        floors=body.floors,
        structure_type=body.structure_type,
    )
