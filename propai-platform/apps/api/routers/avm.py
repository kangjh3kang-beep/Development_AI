"""AVM 시세 추정 라우터."""

from fastapi import APIRouter, Depends, Request
from packages.schemas.models import AVMRequest, AVMValuationResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.metrics import AVM_ESTIMATES
from apps.api.rate_limit import ai_limiter, limiter
from apps.api.services.avm_service import AVMService

router = APIRouter()


@router.post("", response_model=AVMValuationResponse)
@limiter.limit(ai_limiter)
async def estimate_value(
    request: Request,
    body: AVMRequest,
    current_user: CurrentUser = Depends(RequirePermission("avm", "write")),
    db: AsyncSession = Depends(get_db),
) -> AVMValuationResponse:
    """AVM 시세를 추정한다."""
    svc = AVMService(db)
    result = await svc.estimate(body, current_user.tenant_id)
    AVM_ESTIMATES.inc()
    return result
