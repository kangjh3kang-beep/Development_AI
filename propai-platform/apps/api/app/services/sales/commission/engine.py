"""수수료 2단 엔진 — 시행사 총액 → 대행사 배분(조직 path cascade) → 잔여 대행사 귀속,
SUM(배분) ≤ 총액 보장. 지급 원천징수(3.3%). 계약취소 시 역추적 환수(clawback).
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.commission_mh_harness import (
    SalesCommissionDistribution, SalesCommissionClawback, SalesCommissionEvent,
    SalesCommissionMaster, SalesCommissionSplit,
)
from app.services.sales.org.service import ancestors_path

Q = Decimal("1")


async def _active_master(db, site_id) -> SalesCommissionMaster | None:
    return (await db.execute(select(SalesCommissionMaster).where(
        SalesCommissionMaster.site_id == site_id)
        .order_by(SalesCommissionMaster.effective_at.desc()).limit(1))).scalar_one_or_none()


async def resolve_total(db, site_id, contract) -> Decimal:
    m = await _active_master(db, site_id)
    if not m:
        return Decimal(0)
    if m.basis == "PER_CONTRACT_FIXED":
        return Decimal(m.fixed_amount or 0)
    if m.basis == "RATE_OF_PRICE":
        return (Decimal(getattr(contract, "total_price", 0) or 0) * Decimal(str(m.rate or 0))).quantize(Q)
    return Decimal(0)  # TOTAL_POOL: 정산 배치


async def _rules(db, site_id, master_id):
    rows = list((await db.execute(select(SalesCommissionDistribution).where(
        SalesCommissionDistribution.site_id == site_id,
        SalesCommissionDistribution.master_id == master_id))).scalars())
    by_node = {r.target_node_id: r for r in rows if r.target_node_id}
    by_type = {r.target_node_type: r for r in rows if r.target_node_type and not r.target_node_id}
    return by_node, by_type


def _amount(rule, total: Decimal) -> Decimal:
    if not rule:
        return Decimal(0)
    return Decimal(str(rule.value or 0)) if rule.basis == "FIXED" else (total * Decimal(str(rule.value or 0))).quantize(Q)


async def split_commission(db: AsyncSession, site_id, contract):
    total = await resolve_total(db, site_id, contract)
    if total <= 0:
        return None
    m = await _active_master(db, site_id)
    ev = SalesCommissionEvent(site_id=site_id, contract_ext_id=contract.id, base_amount=total, status="PENDING")
    db.add(ev)
    await db.flush()
    chain = await ancestors_path(db, contract.member_node_id)  # [대행사 … 팀원]
    if not chain:
        ev.status = "SPLIT"
        await db.flush()
        return ev
    agency = chain[0]
    by_node, by_type = await _rules(db, site_id, m.id)
    allocated = Decimal(0)
    for node in chain[1:]:
        rule = by_node.get(node.id) or by_type.get(node.node_type)
        amt = _amount(rule, total)
        if amt > 0:
            db.add(SalesCommissionSplit(event_id=ev.id, node_id=node.id, node_type=node.node_type,
                   basis=rule.basis, rate=(rule.value if rule.basis == "RATE" else None), amount=amt))
            allocated += amt
    residual = total - allocated
    if residual < 0:
        raise ValueError("배분 합계가 시행사 총액을 초과")  # 무결성: SUM(배분) ≤ 총액
    db.add(SalesCommissionSplit(event_id=ev.id, node_id=agency.id, node_type=agency.node_type,
           basis="RESIDUAL", amount=residual))  # 대행사 귀속(잔여)
    ev.status = "SPLIT"
    await db.flush()
    return ev


def payout_net(gross: Decimal, wh_rate: Decimal = Decimal("0.033")) -> dict:
    wh = (gross * wh_rate).quantize(Q)
    return {"gross": gross, "withholding": wh, "net": gross - wh}  # 사업소득 원천징수 3.3%


async def clawback(db: AsyncSession, event_id, reason: str):
    splits = list((await db.execute(select(SalesCommissionSplit).where(
        SalesCommissionSplit.event_id == event_id))).scalars())
    total_rev = sum((s.amount or 0) for s in splits)
    db.add(SalesCommissionClawback(event_id=event_id, reason=reason, reversed_amount=total_rev))
    ev = (await db.execute(select(SalesCommissionEvent).where(
        SalesCommissionEvent.id == event_id))).scalar_one()
    ev.status = "REVERSED"
    await db.flush()
