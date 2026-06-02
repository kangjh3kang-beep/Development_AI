"""구독 과금 라우터 — 사용 현황·추가결제(시뮬레이션)·견적·등급변경(관리자)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db
from app.core.billing import TIER_BILLING, get_usd_krw_rate, markup_quote
from app.services.billing import billing_service

router = APIRouter(prefix="/api/v1/billing", tags=["구독·과금"])


@router.get("/plans")
async def list_plans():
    """등급별 요금·포함한도·할증 안내."""
    from app.core.billing import tier_included_budget_krw

    return {
        "plans": [
            {
                "tier": t,
                "label": info["label"],
                "fee_krw": info["fee_krw"],
                "included_budget_krw": tier_included_budget_krw(t),
                "surcharge_pct": round((info["multiplier"] - 1) * 100),
                "multiplier": info["multiplier"],
            }
            for t, info in TIER_BILLING.items()
        ],
    }


@router.get("/status")
async def billing_status(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await billing_service.get_status(db, current.user_id)


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
    """추가결제 견적(등급 할증 적용 청구액 표시)."""
    st = await billing_service.get_status(db, current.user_id)
    rate = await get_usd_krw_rate()
    return markup_quote(req.real_cost_usd, st["tier"], rate)


class SetTierRequest(BaseModel):
    user_id: str
    tier: str


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
