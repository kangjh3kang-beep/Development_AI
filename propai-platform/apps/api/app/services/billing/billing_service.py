"""구독 과금 서비스 — 사용자별 LLM 청구사용량 누적·한도·충전·등급.

public.users의 tier/llm_billed_krw/billing_budget_krw/billing_cycle_start를
raw SQL로 직접 다룬다(ORM 컬럼 불일치 회피). 월 단위 사이클 자동 리셋.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import json

from app.core.billing import (
    TIER_BILLING,
    apply_config,
    billed_krw,
    get_config,
    free_tier_analysis_fee,
    free_tier_analysis_quota,
    get_usd_krw_rate,
    is_metered_tier,
    service_fee_land_analysis,
    service_fee_project_create,
    service_fee_sales_provision,
    service_fee_stage,
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
    await load_config(db)
    await ensure_cycle(db, user_id)
    row = await _row(db, user_id)
    if not row:
        return {"tier": "guest", "metered": False, "blocked": False}
    tier, billed, budget = row[0], float(row[1]), float(row[2])
    rate = await get_usd_krw_rate()
    metered = is_metered_tier(tier)
    remaining = max(0.0, budget - billed)
    meta = await _meta(db, user_id)
    acount = int(meta[1]) if meta else 0
    sfee = float(meta[2]) if meta else 0.0
    free_quota = free_tier_analysis_quota(tier) if not metered else 0
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
        # 서비스 사용료(LLM 별개)
        "service_fee_krw": round(sfee),
        "free_analysis_quota": free_quota,
        "free_analysis_used": acount if not metered else 0,
        "free_analysis_remaining": max(0, free_quota - acount) if not metered else 0,
        # 내부전용(노출 X)
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


_CONFIG_DDL = "CREATE TABLE IF NOT EXISTS billing_config (id int PRIMARY KEY, config jsonb, updated_at timestamptz)"
_config_loaded = False


async def load_config(db: AsyncSession, force: bool = False) -> None:
    """billing_config(DB)에서 관리자 설정을 읽어 런타임 설정에 반영(최초 1회/강제)."""
    global _config_loaded
    if _config_loaded and not force:
        return
    try:
        await db.execute(text(_CONFIG_DDL))
        await db.commit()
        row = (await db.execute(text("SELECT config FROM billing_config WHERE id=1"))).first()
        if row and row[0]:
            cfg = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            apply_config(cfg)
        _config_loaded = True
    except Exception:  # noqa: BLE001
        pass


async def save_config(db: AsyncSession, override: dict[str, Any]) -> dict[str, Any]:
    """관리자 설정 저장(DB 영속 + 런타임 반영)."""
    await db.execute(text(_CONFIG_DDL))
    apply_config(override)
    cfg = json.dumps(get_config(), ensure_ascii=False)
    await db.execute(
        text("INSERT INTO billing_config(id, config, updated_at) VALUES (1, CAST(:c AS jsonb), now()) "
             "ON CONFLICT (id) DO UPDATE SET config=CAST(:c AS jsonb), updated_at=now()"),
        {"c": cfg},
    )
    await db.commit()
    return get_config()


async def _meta(db: AsyncSession, user_id: Any):
    """tier, analysis_count, service_fee_krw 조회."""
    r = (await db.execute(
        text("SELECT tier, COALESCE(analysis_count,0), COALESCE(service_fee_krw,0) "
             "FROM public.users WHERE id=:id"),
        {"id": str(user_id)},
    )).first()
    return r


def compute_service_fee(tier: str, action: str, analysis_count: int) -> dict[str, Any]:
    """행위별 서비스 사용료(원) 산정. LLM 과금과 별개.

    - 프로젝트 생성: 2,000원(구독자)
    - 토지분석: 구독자 2,000원 / 일반회원 무료 N회후 5,000원 / 비회원 무료 N회후 10,000원
    """
    if action == "project_create":
        return {"fee_krw": service_fee_project_create(), "free": False, "free_remaining": 0}
    if action == "sales_provision":
        return {"fee_krw": service_fee_sales_provision(), "free": False, "free_remaining": 0}
    # 파이프라인 단계별 과금 (stage:<name>)
    if action.startswith("stage:"):
        return {"fee_krw": service_fee_stage(action.split(":", 1)[1]), "free": False, "free_remaining": 0}
    # land_analysis
    if is_metered_tier(tier):  # 구독자
        return {"fee_krw": service_fee_land_analysis(), "free": False, "free_remaining": 0}
    quota = free_tier_analysis_quota(tier)
    if analysis_count < quota:
        return {"fee_krw": 0, "free": True, "free_remaining": quota - analysis_count - 1}
    return {"fee_krw": free_tier_analysis_fee(tier), "free": False, "free_remaining": 0}


async def preview_service_fee(db: AsyncSession, user_id: Any, action: str) -> dict[str, Any]:
    m = await _meta(db, user_id)
    if not m:
        return {"fee_krw": 0, "free": True, "free_remaining": 0}
    return compute_service_fee(m[0], action, int(m[1]))


async def charge_service(db: AsyncSession, user_id: Any, action: str) -> dict[str, Any]:
    """행위 발생 시 서비스 사용료 누적(+무료 토지분석이면 analysis_count 증가)."""
    m = await _meta(db, user_id)
    if not m:
        return {"charged_krw": 0, "free": True}
    tier, acount, sfee = m[0], int(m[1]), float(m[2])
    calc = compute_service_fee(tier, action, acount)
    fee = calc["fee_krw"]
    if action == "land_analysis" and calc.get("free"):
        await db.execute(
            text("UPDATE public.users SET analysis_count = COALESCE(analysis_count,0)+1 WHERE id=:id"),
            {"id": str(user_id)},
        )
    if fee > 0:
        await db.execute(
            text("UPDATE public.users SET service_fee_krw = COALESCE(service_fee_krw,0)+:f WHERE id=:id"),
            {"f": float(fee), "id": str(user_id)},
        )
    await db.commit()
    return {
        "action": action,
        "charged_krw": fee,
        "free": calc.get("free", False),
        "free_remaining": calc.get("free_remaining", 0),
        "service_fee_total_krw": round(sfee + fee),
    }


async def set_tier(db: AsyncSession, user_id: Any, tier: str) -> None:
    """등급 변경 + 한도 재설정(관리자)."""
    budget = tier_included_budget_krw(tier)
    await db.execute(
        text("UPDATE public.users SET tier=:t, llm_billed_krw=0, billing_budget_krw=:b, billing_cycle_start=:c WHERE id=:id"),
        {"t": tier, "b": budget, "c": datetime.now(timezone.utc), "id": str(user_id)},
    )
    await db.commit()
