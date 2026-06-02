"""구독 과금 서비스 — 사용자별 LLM 청구사용량 누적·한도·충전·등급.

public.users의 tier/llm_billed_krw/billing_budget_krw/billing_cycle_start를
raw SQL로 직접 다룬다(ORM 컬럼 불일치 회피). 월 단위 사이클 자동 리셋.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.billing import (
    TIER_BILLING,
    billed_krw,
    get_usd_krw_rate,
    is_metered_tier,
    tier_fee_krw,
    tier_included_budget_krw,
    tier_multiplier,
)

_SEL = text(
    "SELECT tier, COALESCE(llm_billed_krw,0), COALESCE(billing_budget_krw,0), billing_cycle_start "
    "FROM public.users WHERE id = :id"
)


async def _row(db: AsyncSession, user_id: Any):
    return (await db.execute(_SEL, {"id": str(user_id)})).first()


async def ensure_cycle(db: AsyncSession, user_id: Any):
    """월이 바뀌면 청구사용량 리셋 + 한도를 등급 기본한도로 재설정."""
    row = await _row(db, user_id)
    if not row:
        return None
    tier, billed, budget, cycle = row[0], float(row[1]), float(row[2]), row[3]
    now = datetime.now(timezone.utc)
    rollover = cycle is None or (cycle.year, cycle.month) != (now.year, now.month)
    if rollover and is_metered_tier(tier):
        budget = tier_included_budget_krw(tier)
        await db.execute(
            text("UPDATE public.users SET llm_billed_krw=0, billing_budget_krw=:b, billing_cycle_start=:c WHERE id=:id"),
            {"b": budget, "c": now, "id": str(user_id)},
        )
        await db.commit()
        billed = 0.0
    return tier, billed, budget


async def get_status(db: AsyncSession, user_id: Any) -> dict[str, Any]:
    await ensure_cycle(db, user_id)
    row = await _row(db, user_id)
    if not row:
        return {"tier": "guest", "metered": False, "blocked": False}
    tier, billed, budget = row[0], float(row[1]), float(row[2])
    rate = await get_usd_krw_rate()
    metered = is_metered_tier(tier)
    remaining = max(0.0, budget - billed)
    return {
        "tier": tier,
        "tier_label": TIER_BILLING.get(tier, {}).get("label", tier),
        "metered": metered,
        "fee_krw": tier_fee_krw(tier),
        "included_budget_krw": tier_included_budget_krw(tier),
        "budget_krw": round(budget),
        "billed_krw": round(billed),
        "remaining_krw": round(remaining),
        "usage_pct": round(billed / budget * 100, 1) if budget > 0 else 0,
        "blocked": metered and billed >= budget,
        "multiplier": tier_multiplier(tier),
        "exchange_rate": round(rate, 2),
    }


async def is_blocked(db: AsyncSession, user_id: Any) -> bool:
    row = await ensure_cycle(db, user_id)
    if not row:
        return False
    tier, billed, budget = row
    return is_metered_tier(tier) and billed >= budget


async def record_usage_usd(db: AsyncSession, user_id: Any, real_cost_usd: float) -> float | None:
    """실 LLM 원가($)를 등급 할증 적용 청구액(원)으로 누적. 반환=가산액(원)."""
    row = await ensure_cycle(db, user_id)
    if not row:
        return None
    tier = row[0]
    if not is_metered_tier(tier):
        return None
    rate = await get_usd_krw_rate()
    add = billed_krw(real_cost_usd, tier, rate)
    await db.execute(
        text("UPDATE public.users SET llm_billed_krw = COALESCE(llm_billed_krw,0) + :a WHERE id=:id"),
        {"a": add, "id": str(user_id)},
    )
    await db.commit()
    return round(add, 2)


async def topup(db: AsyncSession, user_id: Any, amount_krw: float) -> None:
    """추가결제(시뮬레이션): 한도 충전."""
    await db.execute(
        text("UPDATE public.users SET billing_budget_krw = COALESCE(billing_budget_krw,0) + :a WHERE id=:id"),
        {"a": float(amount_krw), "id": str(user_id)},
    )
    await db.commit()


async def set_tier(db: AsyncSession, user_id: Any, tier: str) -> None:
    """등급 변경 + 한도 재설정(관리자)."""
    budget = tier_included_budget_krw(tier)
    await db.execute(
        text("UPDATE public.users SET tier=:t, llm_billed_krw=0, billing_budget_krw=:b, billing_cycle_start=:c WHERE id=:id"),
        {"t": tier, "b": budget, "c": datetime.now(timezone.utc), "id": str(user_id)},
    )
    await db.commit()
