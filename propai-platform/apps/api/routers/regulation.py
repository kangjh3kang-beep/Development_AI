"""법규 검토 라우터."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from packages.schemas.models import RegulationCheckResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.rate_limit import ai_limiter, limiter
from apps.api.services.regulation_service import RegulationService

router = APIRouter()


class RegulationCheckRequest(BaseModel):
    project_id: UUID
    regulation_type: str
    project_info: dict


@router.post("/check", response_model=RegulationCheckResponse)
@limiter.limit(ai_limiter)
async def check_regulation(
    request: Request,
    body: RegulationCheckRequest,
    current_user: CurrentUser = Depends(RequirePermission("regulation", "write")),
    db: AsyncSession = Depends(get_db),
) -> RegulationCheckResponse:
    """법규 적합성을 검토한다."""
    svc = RegulationService(db)
    return await svc.check_regulation(
        project_id=body.project_id,
        tenant_id=current_user.tenant_id,
        regulation_type=body.regulation_type,
        project_info=body.project_info,
    )
