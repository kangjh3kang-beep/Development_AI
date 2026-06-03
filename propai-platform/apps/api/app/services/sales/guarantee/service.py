"""보증/신탁 — 선분양 요건 점검(HUG 분양보증 OR 신탁 분양관리+대리사무). 파라미터 규칙."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.guarantee import SalesGuaranteePolicy


async def guarantee_check(db: AsyncSession, site_id) -> dict:
    pols = list((await db.execute(select(SalesGuaranteePolicy).where(
        SalesGuaranteePolicy.site_id == site_id, SalesGuaranteePolicy.status == "ACTIVE"))).scalars())
    today = date.today()
    active = [p for p in pols if (not p.period_end or p.period_end >= today)]
    has_hug = any(p.guarantor == "HUG" and p.type == "SALE_GUARANTEE" for p in active)
    has_trust = (any(p.type == "TRUST_MGMT" for p in active) and any(p.type == "AGENCY_AFFAIR" for p in active))
    return {"satisfied": has_hug or has_trust, "hug": has_hug,
            "trust_mgmt_agency": has_trust, "active_policies": len(active)}
