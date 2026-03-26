"""설계/BIM 라우터.

평면도 생성, IFC 분석, 설계 보고서 SSE 스트리밍.
"""

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends
from packages.schemas.models import BIMQuantityResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.bim_ifc_service import BIMIFCService
from apps.api.services.design_ai_service import DesignAIService
from apps.api.services.floor_plan_image_service import FloorPlanImageService

router = APIRouter()


class FloorPlanRequest(BaseModel):
    project_id: UUID
    area_sqm: float
    room_count: int
    style: str = "modern"


class IFCAnalyzeRequest(BaseModel):
    project_id: UUID
    file_url: str


class DesignReportRequest(BaseModel):
    project_id: UUID
    design_data: dict


@router.post("/floor-plan")
async def generate_floor_plan(
    body: FloorPlanRequest,
    current_user: CurrentUser = Depends(RequirePermission("design", "write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """AI 평면도를 생성한다."""
    svc = FloorPlanImageService(db)
    return await svc.generate(
        project_id=body.project_id,
        tenant_id=current_user.tenant_id,
        area_sqm=body.area_sqm,
        room_count=body.room_count,
        style=body.style,
    )


@router.post("/bim/analyze", response_model=BIMQuantityResponse)
async def analyze_ifc(
    body: IFCAnalyzeRequest,
    current_user: CurrentUser = Depends(RequirePermission("design", "write")),
    db: AsyncSession = Depends(get_db),
) -> BIMQuantityResponse:
    """IFC 파일을 분석하여 물량을 산출한다."""
    svc = BIMIFCService(db)
    return await svc.analyze_ifc(
        project_id=body.project_id,
        tenant_id=current_user.tenant_id,
        file_url=body.file_url,
    )


@router.post("/report/stream")
async def stream_design_report(
    body: DesignReportRequest,
    current_user: CurrentUser = Depends(RequirePermission("design", "read")),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """설계 보고서를 SSE 스트리밍으로 생성한다."""
    svc = DesignAIService(db)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        async for event in svc.stream_design_report(
            project_id=body.project_id,
            tenant_id=current_user.tenant_id,
            design_data=body.design_data,
        ):
            yield {"event": event.event_type, "data": event.model_dump_json()}

    return EventSourceResponse(event_generator())
