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
@router.post("/estimate", response_model=AVMValuationResponse)  # 프론트 표준 경로(/avm/estimate)
@limiter.limit(ai_limiter)
async def estimate_value(
    request: Request,
    body: AVMRequest,
    # AVM 시세 추정은 조회(읽기) 성격 — viewer(구독자)도 다른 부지분석 패널처럼 사용 가능해야 함.
    # write 요구 시 viewer가 403→프론트 "로그인 필요" 오표기(부지분석 AVM·필지 카드 멈춤). read로 정정.
    current_user: CurrentUser = Depends(RequirePermission("avm", "read")),
    db: AsyncSession = Depends(get_db),
) -> AVMValuationResponse:
    """AVM 시세를 추정한다."""
    svc = AVMService(db)
    result = await svc.estimate(body, current_user.tenant_id)
    AVM_ESTIMATES.inc()
    return result
