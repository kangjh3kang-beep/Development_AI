"""현장 ERP 프로비저닝(템플릿 생성) + 배치 함수.

Celery 미배포(결정) → async 함수로 제공. API 액션/기존 스케줄러에서 호출.
동호 시드는 운영자가 소스(OUTLINE/도면/설계AI) 선택해 별도 /units/generate 로 실행.
기본형건축비 단가는 regulation_change_log 최신 고시값 주입(하드코딩 금지).
"""

import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.commission_mh_harness import (
    MhDesk, SalesCommissionMaster, SalesHarnessSubscription,
)
from apps.api.database.models.sales.site_org import SalesSite, SalesSiteConfig, SalesSiteProvisioning
from apps.api.database.models.sales.units_pricing import (
    SalesDevTypeProfile, SalesPriceComposition, SalesRound, SalesUnitHold, SalesUnitInventory,
)
from app.seeds.sales_dev_profiles import COMPOSITION_DEFAULTS, DEV_TYPE_DEFAULTS

DEFAULT_INSTALLMENTS = {"default": [
    {"kind": "DOWN", "ratio": 0.10, "after_days": 0},
    {"kind": "MIDDLE", "ratio": 0.10, "after_days": 90},
    {"kind": "MIDDLE", "ratio": 0.10, "after_days": 180},
    {"kind": "MIDDLE", "ratio": 0.10, "after_days": 270},
    {"kind": "MIDDLE", "ratio": 0.10, "after_days": 360},
    {"kind": "MIDDLE", "ratio": 0.10, "after_days": 450},
    {"kind": "BALANCE", "ratio": 0.40, "after_days": 720},
]}  # 현장 협의값으로 갱신(예시)


def _log(db, site_id, step, status, log=None):
    db.add(SalesSiteProvisioning(site_id=site_id, step=step, status=status, log=log))


async def provision_site(db: AsyncSession, project_id, organization_id, site_name, development_type) -> dict:
    code = f"s{secrets.token_hex(4)}"
    site = SalesSite(organization_id=organization_id, project_id=project_id, site_code=code,
                     site_name=site_name, development_type=development_type, status="PREP")
    db.add(site)
    await db.flush()
    _log(db, site.id, "site", "DONE")

    db.add(SalesSiteConfig(site_id=site.id, installment_schedule=DEFAULT_INSTALLMENTS,
                           pricing_mode="GENERAL", masking_policy={"mask_visitor_name": True}))

    prof = DEV_TYPE_DEFAULTS.get(development_type, DEV_TYPE_DEFAULTS["APT"])
    db.add(SalesDevTypeProfile(site_id=site.id, development_type=development_type,
           sale_method=prof["sale_method"], unit_price_basis=prof["unit_price_basis"],
           area_basis=prof.get("area_basis"), vat_policy=prof.get("vat_policy"),
           naming_rule=prof.get("naming_rule"), attributes=prof.get("attributes")))

    rnd = SalesRound(site_id=site.id, round_no=1, round_type="GENERAL", sale_type="GENERAL",
                     name="일반분양", sort_order=1)
    db.add(rnd)
    await db.flush()
    for c in COMPOSITION_DEFAULTS:
        db.add(SalesPriceComposition(site_id=site.id, round_id=rnd.id, **c))

    db.add(SalesCommissionMaster(site_id=site.id, basis="PER_CONTRACT_FIXED", fixed_amount=0, locked=False))
    db.add(MhDesk(site_id=site.id, desk_name="메인데스크", channel_id=f"site:{site.id}"))
    for e in ["ContractSigned", "ContractCancelled", "VisitorCheckedIn", "CommissionSettled", "StaffOnboarded"]:
        db.add(SalesHarnessSubscription(site_id=site.id, event_type=e, projection_target="site_summary"))
    _log(db, site.id, "config_seed", "DONE")
    await db.flush()
    return {"site_id": str(site.id), "site_code": code}


# ── 배치 함수(스케줄러/수동 호출) ──
async def expire_holds(db: AsyncSession, site_id, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    holds = list((await db.execute(select(SalesUnitHold).where(
        SalesUnitHold.site_id == site_id, SalesUnitHold.expires_at < now))).scalars())
    n = 0
    for h in holds:
        u = (await db.execute(select(SalesUnitInventory).where(SalesUnitInventory.id == h.unit_id))).scalar_one_or_none()
        if u and u.status == "HOLD":
            u.status = "AVAILABLE"
            n += 1
        await db.delete(h)
    await db.flush()
    return n
