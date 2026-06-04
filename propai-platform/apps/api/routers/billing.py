"""구독 과금 라우터 — 사용 현황·추가결제(시뮬레이션)·견적·등급변경(관리자)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db
from app.core.billing import (
    TIER_BILLING,
    get_usd_krw_rate,
    markup_quote,
    public_status,
    tier_included_budget_krw,
)
from app.services.billing import billing_service

router = APIRouter(prefix="/api/v1/billing", tags=["구독·과금"])


@router.get("/plans")
async def list_plans():
    """등급별 요금·포함 사용량 안내.

    ★할증배수(50/40/30%)는 내부 정책 → 외부 미노출. 사용자에겐 요금·포함 사용량(원)만.
    """
    return {
        "plans": [
            {
                "tier": t,
                "label": info["label"],
                "fee_krw": info["fee_krw"],
                "included_budget_krw": tier_included_budget_krw(t),
            }
            for t, info in TIER_BILLING.items()
        ],
    }


@router.get("/status")
async def billing_status(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """사용자 과금 현황 — 실지급액(원)만 노출(내부 배수·환율 제외)."""
    status = await billing_service.get_status(db, current.user_id)
    return public_status(status)


class TopupRequest(BaseModel):
    amount_krw: float


@router.post("/topup")
async def topup(
    req: TopupRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """추가결제(시뮬레이션) — 한도 충전 후 갱신된 현황 반환."""
    if req.amount_krw <= 0:
        raise HTTPException(status_code=400, detail="충전 금액이 올바르지 않습니다.")
    await billing_service.topup(db, current.user_id, req.amount_krw)
    return await billing_service.get_status(db, current.user_id)


class QuoteRequest(BaseModel):
    real_cost_usd: float


@router.post("/quote")
async def quote(
    req: QuoteRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """추가결제 견적 — 실지급액(원)만 반환. (할증·실원가·환율은 내부 비노출)"""
    st = await billing_service.get_status(db, current.user_id)
    rate = await get_usd_krw_rate()
    return markup_quote(req.real_cost_usd, st["tier"], rate, internal=False)


class ChargeRequest(BaseModel):
    action: str  # "project_create" | "land_analysis"


@router.post("/preview-charge")
async def preview_charge(
    req: ChargeRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """서비스 사용료 사전 견적(차감 전 표시용). LLM 과금과 별개."""
    if req.action not in ("project_create", "land_analysis", "sales_provision"):
        raise HTTPException(status_code=400, detail="알 수 없는 행위")
    return await billing_service.preview_service_fee(db, current.user_id, req.action)


@router.post("/charge")
async def charge(
    req: ChargeRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """행위 발생 시 서비스 사용료 차감(프로젝트 생성·토지분석). LLM 과금과 별개."""
    if req.action not in ("project_create", "land_analysis", "sales_provision"):
        raise HTTPException(status_code=400, detail="알 수 없는 행위")
    return await billing_service.charge_service(db, current.user_id, req.action)


class SetTierRequest(BaseModel):
    user_id: str
    tier: str


@router.get("/admin/config")
async def get_billing_config(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """관리자 전용: 현재 과금 설정(등급요금·할증·서비스료·단계별·무료횟수) 조회."""
    if current.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    from app.core.billing import get_config

    await billing_service.load_config(db, force=True)
    return get_config()


@router.put("/admin/config")
async def update_billing_config(
    override: dict,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """관리자 전용: 과금 금액 설정 수정/변경(DB 영속 + 즉시 반영)."""
    if current.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return await billing_service.save_config(db, override or {})


@router.post("/admin/set-tier")
async def admin_set_tier(
    req: SetTierRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """관리자 전용: 사용자 등급 변경."""
    if current.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    await billing_service.set_tier(db, req.user_id, req.tier)
    return {"ok": True, "user_id": req.user_id, "tier": req.tier}
