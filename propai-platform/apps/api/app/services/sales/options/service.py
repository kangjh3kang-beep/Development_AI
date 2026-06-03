"""유상옵션 — 카탈로그 선택 → 계약 옵션 기록(분양가와 분리 표기). VAT 항목별 계산."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.options import SalesContractOption, SalesOptionCatalog

VAT = Decimal("0.1")


async def add_option(db: AsyncSession, contract_id, option_id, qty=1):
    opt = (await db.execute(select(SalesOptionCatalog).where(SalesOptionCatalog.id == option_id))).scalar_one()
    amount = Decimal(opt.price or 0) * int(qty)
    vat = (amount * VAT).quantize(Decimal("1")) if opt.vat_applicable else Decimal(0)
    db.add(SalesContractOption(contract_ext_id=contract_id, option_id=option_id, qty=int(qty),
           unit_price=opt.price, amount=amount, vat_amount=vat))
    await db.flush()
    return {"amount": int(amount), "vat": int(vat)}


async def option_total(db: AsyncSession, contract_id) -> dict:
    rows = (await db.execute(select(SalesContractOption).where(
        SalesContractOption.contract_ext_id == contract_id,
        SalesContractOption.status == "SELECTED"))).scalars()
    amt = sum((r.amount or 0) for r in rows)
    return {"option_total": int(amt)}
