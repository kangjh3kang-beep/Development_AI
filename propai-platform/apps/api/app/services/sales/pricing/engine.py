"""분양가 엔진 — 차수별 기준가 × (1+Σ가중치RATE) + Σ가중치FIXED, 확정가 우선,
구성(토지비/건축비/업무대행비) 분해 + VAT. 상한제(CAP)는 업무대행비(CUSTOM) 제외.
"""

import uuid
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.site_org import SalesSiteConfig
from apps.api.database.models.sales.units_pricing import (
    SalesPriceBase, SalesPriceComposition, SalesPriceGenerationLog, SalesPriceGroup,
    SalesPriceGroupMember, SalesPriceWeight, SalesUnitInventory, SalesUnitPriceBreakdown,
    SalesUnitPriceTable, SalesUnitType,
)

Q = Decimal("1")
VAT = Decimal("0.1")


def _area(ttype, kind) -> Decimal:
    return Decimal(str(getattr(ttype, f"{kind}_area", None) or ttype.supply_area or 0))


def compute_unit_price(unit, ttype, base_row, weights_for_unit) -> Decimal:
    if base_row.basis == "PER_AREA":
        amt = Decimal(base_row.base_unit_price or 0) * _area(ttype, base_row.base_area_kind or "supply")
    else:
        amt = Decimal(base_row.base_unit_price or 0)
    amt *= Decimal(str(base_row.round_factor or 1))
    rate_sum = Decimal(0)
    fixed_sum = Decimal(0)
    for w in weights_for_unit:
        if w.basis == "RATE":
            rate_sum += Decimal(str(w.value or 0))
        else:
            fixed_sum += Decimal(str(w.value or 0))
    return (amt * (Decimal(1) + rate_sum) + fixed_sum).quantize(Q, ROUND_HALF_UP)


def _match_weights(unit, weights, group_map):
    out = []
    for w in weights:
        d, k = w.dimension, (w.match_key or "")
        if d == "FLOOR" and str(unit.floor) == k:
            out.append(w)
        elif d == "LINE" and (unit.line or "") == k:
            out.append(w)
        elif d == "ASPECT" and (unit.aspect or "") == k:
            out.append(w)
        elif d == "CUSTOM":
            out.append(w)
    out += group_map.get(unit.id, [])
    out.sort(key=lambda x: -(x.priority or 0))
    return out


def decompose(price: Decimal, comps, mode: str) -> list[dict]:
    rows = []
    for c in comps:
        if mode == "CAP" and c.component_type == "CUSTOM":
            continue  # 상한제: 업무대행비 등 산정 외
        amt = Decimal(str(c.value or 0)) if c.basis == "FIXED" else (price * Decimal(str(c.value or 0))).quantize(Q)
        vat = (amt * VAT).quantize(Q) if c.vat_applicable else Decimal(0)
        rows.append({"type": c.component_type, "label": c.label, "amount": amt, "vat": vat})
    return rows


async def generate_price_table(db: AsyncSession, site_id: uuid.UUID, round_id: uuid.UUID, by=None) -> int:
    cfg = (await db.execute(select(SalesSiteConfig).where(SalesSiteConfig.site_id == site_id))).scalar_one()
    mode = cfg.pricing_mode or "GENERAL"
    base_rows = {r.type_id: r for r in (await db.execute(select(SalesPriceBase).where(
        SalesPriceBase.site_id == site_id, SalesPriceBase.round_id == round_id))).scalars()}
    weights = list((await db.execute(select(SalesPriceWeight).where(
        SalesPriceWeight.site_id == site_id, SalesPriceWeight.round_id == round_id))).scalars())
    comps = list((await db.execute(select(SalesPriceComposition).where(
        SalesPriceComposition.site_id == site_id, SalesPriceComposition.round_id == round_id)
        .order_by(SalesPriceComposition.sort_order))).scalars())

    group_map: dict = {}
    for g in (await db.execute(select(SalesPriceGroup).where(SalesPriceGroup.site_id == site_id))).scalars():
        members = (await db.execute(select(SalesPriceGroupMember).where(
            SalesPriceGroupMember.group_id == g.id))).scalars()
        for m in members:
            group_map.setdefault(m.unit_id, []).append(g)

    types = {t.id: t for t in (await db.execute(select(SalesUnitType).where(
        SalesUnitType.site_id == site_id))).scalars()}
    units = list((await db.execute(select(SalesUnitInventory).where(
        SalesUnitInventory.site_id == site_id, SalesUnitInventory.deleted_at.is_(None)))).scalars())

    count = 0
    for u in units:
        pt = (await db.execute(select(SalesUnitPriceTable).where(
            SalesUnitPriceTable.unit_id == u.id, SalesUnitPriceTable.round_id == round_id))).scalar_one_or_none()
        if pt and pt.price_mode == "FIXED" and pt.override_price is not None:
            price = Decimal(pt.override_price)  # 확정금액 우선
        else:
            br = base_rows.get(u.type_id)
            if not br:
                continue
            price = compute_unit_price(u, types[u.type_id], br, _match_weights(u, weights, group_map))
        bd = decompose(price, comps, mode)
        if not pt:
            pt = SalesUnitPriceTable(site_id=site_id, unit_id=u.id, round_id=round_id)
            db.add(pt)
        pt.base_price = price
        pt.total_price = price + (pt.option_price or 0) + (pt.premium or 0)
        await db.execute(SalesUnitPriceBreakdown.__table__.delete().where(
            (SalesUnitPriceBreakdown.unit_id == u.id) & (SalesUnitPriceBreakdown.round_id == round_id)))
        for r in bd:
            db.add(SalesUnitPriceBreakdown(site_id=site_id, unit_id=u.id, round_id=round_id,
                   component_type=r["type"], label=r["label"], amount=r["amount"], vat_amount=r["vat"]))
        count += 1

    db.add(SalesPriceGenerationLog(site_id=site_id, round_id=round_id, generated_count=count,
           params_snapshot={"mode": mode}, by=by))
    await db.flush()
    return count
