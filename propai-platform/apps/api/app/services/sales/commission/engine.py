"""수수료 2단 엔진 — 시행사 총액 → 대행사 배분(조직 path cascade) → 잔여 대행사 귀속,
SUM(배분) ≤ 총액 보장. 지급 원천징수(3.3%). 계약취소 시 역추적 환수(clawback).
"""

import uuid
from decimal import Decimal

from sqlalchemy import select, text
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


def payout_net(gross: Decimal, tax_type: str = "WITHHOLDING",
               wh_rate: Decimal = Decimal("0.033"), vat_rate: Decimal = Decimal("0.10")) -> dict:
    """수령자 세금유형별 지급 분개.

    - WITHHOLDING(개인 사업소득, 3.3% 원천징수): 지급액에서 원천징수 후 실수령 = gross - 원천.
      세금계산서 없음. (프리랜서/팀원 기본)
    - VAT(사업자 세금계산서, 부가세 10%): 공급가액=gross 에 부가세 10% 가산해 지급(total_paid),
      사업자 실수령 공급가액 = gross(부가세는 별도 신고). 원천징수 없음.
    반환 키는 하위호환(gross/withholding/net) 유지 + tax_type/vat/total_paid 추가.
    """
    if (tax_type or "").upper() == "VAT":
        vat = (gross * vat_rate).quantize(Q)
        return {"tax_type": "VAT", "gross": gross, "withholding": Decimal(0), "vat": vat,
                "total_paid": gross + vat, "net": gross}
    wh = (gross * wh_rate).quantize(Q)   # 사업소득 원천징수 3.3%
    return {"tax_type": "WITHHOLDING", "gross": gross, "withholding": wh, "vat": Decimal(0),
            "total_paid": gross, "net": gross - wh}


# 수령자(조직노드)별 세금유형 선호 — 멱등 테이블(WITHHOLDING 기본).
_TAXPREF_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_commission_tax_pref ("
    "  site_id uuid NOT NULL,"
    "  node_id uuid NOT NULL,"
    "  tax_type varchar(16) NOT NULL DEFAULT 'WITHHOLDING',"
    "  updated_at timestamptz NOT NULL DEFAULT now(),"
    "  PRIMARY KEY (node_id)"
    ")"
)
_TAXPREF_READY = False


async def ensure_tax_pref(db) -> None:
    global _TAXPREF_READY
    if _TAXPREF_READY:
        return
    await db.execute(text(_TAXPREF_DDL))
    await db.commit()
    _TAXPREF_READY = True


async def get_node_tax_type(db, node_id) -> str:
    """노드(수령자) 세금유형. 미설정 시 WITHHOLDING(3.3%)."""
    if node_id is None:
        return "WITHHOLDING"
    await ensure_tax_pref(db)
    r = (await db.execute(text("SELECT tax_type FROM sales_commission_tax_pref WHERE node_id=:n"),
                          {"n": str(node_id)})).first()
    return (r[0] if r else "WITHHOLDING") or "WITHHOLDING"


async def set_node_tax_type(db, site_id, node_id, tax_type: str) -> str:
    tt = (tax_type or "").upper()
    if tt not in ("WITHHOLDING", "VAT"):
        raise ValueError("tax_type은 WITHHOLDING 또는 VAT")
    await ensure_tax_pref(db)
    await db.execute(text(
        "INSERT INTO sales_commission_tax_pref (site_id, node_id, tax_type, updated_at) "
        "VALUES (:s,:n,:t, now()) ON CONFLICT (node_id) DO UPDATE SET tax_type=:t, updated_at=now()"),
        {"s": str(site_id), "n": str(node_id), "t": tt})
    return tt


async def clawback(db: AsyncSession, event_id, reason: str):
    splits = list((await db.execute(select(SalesCommissionSplit).where(
        SalesCommissionSplit.event_id == event_id))).scalars())
    total_rev = sum((s.amount or 0) for s in splits)
    db.add(SalesCommissionClawback(event_id=event_id, reason=reason, reversed_amount=total_rev))
    ev = (await db.execute(select(SalesCommissionEvent).where(
        SalesCommissionEvent.id == event_id))).scalar_one()
    ev.status = "REVERSED"
    await db.flush()
