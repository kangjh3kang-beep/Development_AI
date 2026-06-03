"""수납 — 가상계좌 발급/입금 대사(미납 회차 충당)/연체이자 산정. 자금이체 미수행(기록·대사·산출)."""

from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sales_crypto import encrypt
from apps.api.database.models.sales.contract_crm_ad import SalesContractExt, SalesContractInstallment
from apps.api.database.models.sales.payment import SalesOverdueInterest, SalesPayment, SalesVirtualAccount
from apps.api.database.models.sales.site_org import SalesSiteConfig


async def issue_va(db: AsyncSession, site_id, contract_id, bank, va_number, holder, pool_ref=None):
    db.add(SalesVirtualAccount(site_id=site_id, contract_ext_id=contract_id, bank=bank,
           va_number_enc=encrypt(va_number), holder=holder, pool_ref=pool_ref))
    await db.flush()


async def ingest_payment(db: AsyncSession, site_id, payload: dict) -> dict:
    """payload: {va_number, amount, depositor?, paid_at?, raw_ref?}. 미매칭 → 수동 대사 큐."""
    target = encrypt(payload["va_number"])
    amount = Decimal(str(payload["amount"]))
    paid_at = payload.get("paid_at")
    va = (await db.execute(select(SalesVirtualAccount).where(
        SalesVirtualAccount.site_id == site_id, SalesVirtualAccount.va_number_enc == target))).scalar_one_or_none()
    if not va:
        db.add(SalesPayment(site_id=site_id, method="VA", amount=amount, paid_at=paid_at,
               matched=False, raw_ref=payload.get("raw_ref")))
        await db.flush()
        return {"matched": False}
    insts = (await db.execute(select(SalesContractInstallment).where(
        SalesContractInstallment.contract_ext_id == va.contract_ext_id)
        .order_by(SalesContractInstallment.seq))).scalars()
    remaining = amount
    pay_inst_id = None
    for it in insts:
        due = (it.amount or 0) - (it.paid_amount or 0)
        if due <= 0:
            continue
        applied = min(Decimal(due), remaining)
        it.paid_amount = (it.paid_amount or 0) + int(applied)
        if applied >= due:
            it.paid_at = paid_at or datetime.now(timezone.utc)
        pay_inst_id = pay_inst_id or it.id
        remaining -= applied
        if remaining <= 0:
            break
    db.add(SalesPayment(site_id=site_id, contract_ext_id=va.contract_ext_id, installment_id=pay_inst_id,
           method="VA", amount=amount, paid_at=paid_at, matched=True, raw_ref=payload.get("raw_ref")))
    await db.flush()
    return {"matched": True, "contract": str(va.contract_ext_id)}


async def overdue_calc(db: AsyncSession, site_id, as_of: datetime) -> int:
    cfg = (await db.execute(select(SalesSiteConfig).where(SalesSiteConfig.site_id == site_id))).scalar_one_or_none()
    rate = Decimal(str(((cfg.stage_def if cfg else None) or {}).get("overdue_rate", 0)))  # 연체이율(파라미터, 약관 재확인)
    # 현장 스코프: contracts_ext 조인으로 site_id 필터
    insts = (await db.execute(
        select(SalesContractInstallment)
        .join(SalesContractExt, SalesContractExt.id == SalesContractInstallment.contract_ext_id)
        .where(SalesContractExt.site_id == site_id,
               SalesContractInstallment.due_date < as_of.date()))).scalars()
    n = 0
    for it in insts:
        unpaid = (it.amount or 0) - (it.paid_amount or 0)
        if unpaid <= 0:
            continue
        days = (as_of.date() - it.due_date).days
        interest = int((Decimal(unpaid) * days * (rate / Decimal(365))).quantize(Decimal("1")))
        db.add(SalesOverdueInterest(site_id=site_id, installment_id=it.id, overdue_days=days,
               rate=rate, amount=interest))
        n += 1
    await db.flush()
    return n
