"""계약 상태머신 — 서명(동호 CONTRACTED + 회차 자동생성 + 수수료 split + 투영),
취소(동호 CANCELLED + 변경 스냅샷 + 수수료 환수 + 투영). 1호 1계약은 동호 유니크로 보장.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.commission_mh_harness import SalesCommissionEvent
from apps.api.database.models.sales.contract_crm_ad import SalesContractChange, SalesContractExt, SalesContractInstallment
from apps.api.database.models.sales.site_org import SalesSiteConfig
from apps.api.database.models.sales.units_pricing import SalesUnitInventory, SalesUnitStatusLog
from app.services.sales.commission.engine import clawback, split_commission
from app.services.sales.harness.outbox import emit_outbox


async def _set_unit_status(db, unit_id, to_status, by=None):
    if not unit_id:
        return None
    u = (await db.execute(select(SalesUnitInventory).where(SalesUnitInventory.id == unit_id))).scalar_one()
    db.add(SalesUnitStatusLog(site_id=u.site_id, unit_id=unit_id, from_status=u.status, to_status=to_status, by=by))
    u.status = to_status
    await db.flush()
    return u


async def sign_contract(db: AsyncSession, site_id, contract_id, by=None):
    c = (await db.execute(select(SalesContractExt).where(SalesContractExt.id == contract_id))).scalar_one()
    c.stage = "SIGNED"
    c.signed_at = datetime.now(timezone.utc)
    await _set_unit_status(db, c.unit_id, "CONTRACTED", by)  # 동호 유니크로 1호 1계약 보장

    cfg = (await db.execute(select(SalesSiteConfig).where(SalesSiteConfig.site_id == site_id))).scalar_one_or_none()
    sched = ((cfg.installment_schedule if cfg else None) or {}).get("default", [])
    base = datetime.now(timezone.utc).date()
    for i, s in enumerate(sched, start=1):
        db.add(SalesContractInstallment(
            contract_ext_id=c.id, seq=i, kind=s["kind"],
            due_date=base + timedelta(days=int(s["after_days"])),
            amount=int(round((c.total_price or 0) * float(s["ratio"]))),
        ))
    await split_commission(db, site_id, c)
    await emit_outbox(db, site_id, "ContractSigned",
                      {"unit_id": str(c.unit_id), "amount": int(c.total_price or 0), "stage": "SIGNED"})
    await db.flush()
    return c


async def cancel_contract(db: AsyncSession, site_id, contract_id, reason: str, by=None):
    c = (await db.execute(select(SalesContractExt).where(SalesContractExt.id == contract_id))).scalar_one()
    db.add(SalesContractChange(
        contract_ext_id=c.id, change_type="CANCEL", effective_at=datetime.now(timezone.utc),
        reason=reason, prev_snapshot={"stage": c.stage, "total_price": int(c.total_price or 0)},
    ))
    c.status = "CANCELLED"
    await _set_unit_status(db, c.unit_id, "CANCELLED", by)
    ev = (await db.execute(select(SalesCommissionEvent).where(
        SalesCommissionEvent.contract_ext_id == c.id))).scalar_one_or_none()
    if ev:
        await clawback(db, ev.id, reason)
    await emit_outbox(db, site_id, "ContractCancelled",
                      {"unit_id": str(c.unit_id), "amount": int(c.total_price or 0)})
    await db.flush()
    return c
