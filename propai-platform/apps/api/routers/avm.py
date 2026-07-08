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
    # ★성장루프 조인키: AVM 결과 요약을 분석원장에 best-effort 적재(멱등)하고
    #   응답 스키마의 `ledger_hash` 필드로 노출 — 프론트 피드백(👍/👎)이 원장과 조인된다.
    try:
        from app.services.ledger.analysis_ledger_service import extract_ledger_hash
        from app.services.ledger.ledger_adapters import record_user_analysis
        wb = await record_user_analysis(
            analysis_type="avm",
            summary={
                "estimated_price": result.estimated_price,
                "price_per_sqm": result.price_per_sqm,
                "confidence_score": result.confidence_score,
                "comparable_count": result.comparable_count,
                "model_version": result.model_version,
                "address": body.address, "area_sqm": body.area_sqm,
            },
            tenant_id=str(current_user.tenant_id) if current_user.tenant_id else None,
            project_id=str(body.project_id), pnu=body.pnu, address=body.address,
            source="avm",
        )
        h = extract_ledger_hash(wb)
        if h:
            result.ledger_hash = h
    except Exception:  # noqa: BLE001 — 원장 적재 실패해도 AVM 결과는 무손상 반환
        pass
    return result
