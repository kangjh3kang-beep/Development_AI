"""수수료 분할지급/유보 — 마일스톤 스케줄(합계≤1) + 유보 차감 + 도래분 지급(원천징수). 취소시 환수 연계."""

from decimal import Decimal
from datetime import date, datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.commission_ext import SalesCommissionHoldback, SalesCommissionPayoutSchedule
from apps.api.database.models.sales.commission_mh_harness import SalesCommissionPayout, SalesCommissionSplit
from app.services.sales.commission.engine import payout_net


async def create_schedule(db: AsyncSession, split_id, milestones: list[dict]):
    total = sum(Decimal(str(m["ratio"])) for m in milestones)
    if total > Decimal("1"):
        raise ValueError("마일스톤 비율 합계가 1을 초과")
    for m in milestones:
        db.add(SalesCommissionPayoutSchedule(split_id=split_id, milestone=m["milestone"],
               ratio=Decimal(str(m["ratio"])), planned_at=m.get("planned_at")))
    await db.flush()


async def set_holdback(db: AsyncSession, split_id, reason, amount, release_condition=None):
    db.add(SalesCommissionHoldback(split_id=split_id, reason=reason, amount=amount,
           release_condition=release_condition))
    await db.flush()


async def release_holdback(db: AsyncSession, holdback_id):
    h = (await db.execute(select(SalesCommissionHoldback).where(
        SalesCommissionHoldback.id == holdback_id))).scalar_one()
    h.released_at = datetime.now(timezone.utc)
    await db.flush()
    return h


async def run_due_payouts(db: AsyncSession, site_id, as_of: date, wh_rate=Decimal("0.033")) -> int:
    rows = list((await db.execute(select(SalesCommissionPayoutSchedule).where(
        SalesCommissionPayoutSchedule.status == "PLANNED",
        SalesCommissionPayoutSchedule.planned_at <= as_of))).scalars())
    paid = 0
    for sch in rows:
        split = (await db.execute(select(SalesCommissionSplit).where(
            SalesCommissionSplit.id == sch.split_id))).scalar_one()
        gross = (Decimal(split.amount or 0) * Decimal(str(sch.ratio or 0))).quantize(Decimal("1"))
        hb = (await db.execute(select(SalesCommissionHoldback).where(
            SalesCommissionHoldback.split_id == sch.split_id,
            SalesCommissionHoldback.released_at.is_(None)))).scalars()
        gross -= sum(Decimal(h.amount or 0) for h in hb)
        if gross <= 0:
            sch.status = "PAID"
            continue
        # 수령자(노드) 세금유형 선택: WITHHOLDING(3.3% 원천) 또는 VAT(부가세 10% 가산).
        from app.services.sales.commission.engine import get_node_tax_type
        tt = await get_node_tax_type(db, split.node_id)
        net = payout_net(gross, tt)
        po = SalesCommissionPayout(claim_id=None, gross=int(net["gross"]),
             withholding=int(net["withholding"]), net=int(net["net"]),
             paid_at=datetime.now(timezone.utc), method="SCHEDULE")
        db.add(po)
        await db.flush()
        # tax_type/vat 는 모델 외 컬럼 — 멱등 ALTER 후 raw 갱신(부가세 가산 지급액 추적).
        await db.execute(text(
            "ALTER TABLE sales_commission_payouts ADD COLUMN IF NOT EXISTS tax_type varchar(16) DEFAULT 'WITHHOLDING'"))
        await db.execute(text(
            "ALTER TABLE sales_commission_payouts ADD COLUMN IF NOT EXISTS vat numeric(16,0) DEFAULT 0"))
        await db.execute(text(
            "UPDATE sales_commission_payouts SET tax_type=:t, vat=:v WHERE id=:i"),
            {"t": net["tax_type"], "v": int(net["vat"]), "i": str(po.id)})
        sch.status = "PAID"
        sch.paid_payout_id = po.id
        paid += 1
    await db.flush()
    return paid
