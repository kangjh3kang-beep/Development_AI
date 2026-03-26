"""드론 점검 라우터."""

from uuid import UUID

from fastapi import APIRouter, Depends
from packages.schemas.models import DroneInspectionResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.drone_iot_service import DroneIoTService

router = APIRouter()


class DroneInspectRequest(BaseModel):
    project_id: UUID
    image_urls: list[str]
    flight_id: str | None = None


@router.post("/inspect", response_model=DroneInspectionResponse)
async def inspect(
    body: DroneInspectRequest,
    current_user: CurrentUser = Depends(RequirePermission("drone", "write")),
    db: AsyncSession = Depends(get_db),
) -> DroneInspectionResponse:
    """드론 점검을 수행한다."""
    svc = DroneIoTService(db)
    return await svc.inspect(
        project_id=body.project_id,
        tenant_id=current_user.tenant_id,
        image_urls=body.image_urls,
        flight_id=body.flight_id,
    )
