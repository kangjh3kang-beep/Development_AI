"""분양가 엔진 — 차수별 기준가 × (1+Σ가중치RATE) + Σ가중치FIXED, 확정가 우선,
구성(토지비/건축비/업무대행비) 분해 + VAT. 상한제(CAP)는 업무대행비(CUSTOM) 제외.
"""

import uuid
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
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
        if d == "FLOOR" and str(unit.floor) == k or d == "LINE" and (unit.line or "") == k or d == "ASPECT" and (unit.aspect or "") == k or d == "CUSTOM":
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


async def resolve_unit_price(db: AsyncSession, site_id, unit, round_id=None):
    """per-unit 가격표(SalesUnitPriceTable)가 없을 때 기준단가(SalesPriceBase)에서 1세대 가격을 직접
    산정한다(계약 가격 자동해소 폴백). generate_price_table 미실행 상태에서도 계약 total_price 가
    NULL→0 cascade(수수료·할부·연체 전량 0) 되지 않도록 한다. 산식은 generate_price_table 과 동일.
    """
    if unit is None or not getattr(unit, "type_id", None):
        return None
    q = select(SalesPriceBase).where(
        SalesPriceBase.site_id == site_id, SalesPriceBase.type_id == unit.type_id)
    if round_id:
        q = q.where(SalesPriceBase.round_id == round_id)
    br = (await db.execute(q)).scalars().first()
    if not br:
        return None
    ttype = (await db.execute(select(SalesUnitType).where(SalesUnitType.id == unit.type_id))).scalar_one_or_none()
    if not ttype:
        return None
    rid = round_id or br.round_id
    weights = list((await db.execute(select(SalesPriceWeight).where(
        SalesPriceWeight.site_id == site_id, SalesPriceWeight.round_id == rid))).scalars())
    group_map: dict = {}
    for g in (await db.execute(select(SalesPriceGroup).where(SalesPriceGroup.site_id == site_id))).scalars():
        for m in (await db.execute(select(SalesPriceGroupMember).where(
                SalesPriceGroupMember.group_id == g.id))).scalars():
            group_map.setdefault(m.unit_id, []).append(g)
    price = compute_unit_price(unit, ttype, br, _match_weights(unit, weights, group_map))
    return int(price) if price else None


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


async def solve_base_for_target(
    db: AsyncSession, site_id: uuid.UUID, round_id: uuid.UUID, target_total_10k: int, by=None,
) -> dict:
    """목표 총매출 → 균일 기준단가(㎡당, PER_AREA) 역산 후 전 타입 반영·재생성. reverse.

    총매출은 기준단가 base 에 선형: total = base·M + F.
      M = Σ_세대[ 공급면적 × round_factor × (1+가중치율) ]   (PER_AREA 균일 가정)
      F = Σ_세대[ 정액가중치 + 옵션 + 프리미엄 ]
    base = (target - F) / M. M<=0 이면 산출 불가(세대/면적 없음).
    """
    weights = list((await db.execute(select(SalesPriceWeight).where(
        SalesPriceWeight.site_id == site_id, SalesPriceWeight.round_id == round_id))).scalars())
    base_rows = {r.type_id: r for r in (await db.execute(select(SalesPriceBase).where(
        SalesPriceBase.site_id == site_id, SalesPriceBase.round_id == round_id))).scalars()}
    group_map: dict = {}
    for g in (await db.execute(select(SalesPriceGroup).where(SalesPriceGroup.site_id == site_id))).scalars():
        for m in (await db.execute(select(SalesPriceGroupMember).where(
                SalesPriceGroupMember.group_id == g.id))).scalars():
            group_map.setdefault(m.unit_id, []).append(g)
    types = {t.id: t for t in (await db.execute(select(SalesUnitType).where(
        SalesUnitType.site_id == site_id))).scalars()}
    units = list((await db.execute(select(SalesUnitInventory).where(
        SalesUnitInventory.site_id == site_id, SalesUnitInventory.deleted_at.is_(None)))).scalars())
    opt_prem = {pt.unit_id: (Decimal(pt.option_price or 0) + Decimal(pt.premium or 0))
                for pt in (await db.execute(select(SalesUnitPriceTable).where(
                    SalesUnitPriceTable.site_id == site_id, SalesUnitPriceTable.round_id == round_id))).scalars()}

    M = Decimal(0)
    F = Decimal(0)
    for u in units:
        t = types.get(u.type_id)
        if not t:
            continue
        br = base_rows.get(u.type_id)
        area = _area(t, (br.base_area_kind if br else None) or "supply")
        factor = Decimal(str((br.round_factor if br else None) or 1))
        rate = Decimal(0); fixed = Decimal(0)
        for w in _match_weights(u, weights, group_map):
            if w.basis == "RATE":
                rate += Decimal(str(w.value or 0))
            else:
                fixed += Decimal(str(w.value or 0))
        M += area * factor * (Decimal(1) + rate)
        F += fixed + opt_prem.get(u.id, Decimal(0))

    if M <= 0:
        return {"ok": False, "note": "세대/공급면적이 없어 역산 불가 — 동·호표·타입 면적을 먼저 확정하세요."}

    # 단가·금액은 원(KRW) 단위. 목표는 만원으로 받으므로 ×10000 환산(F·옵션·프리미엄도 원).
    target_won = Decimal(int(target_total_10k)) * 10000
    base = (target_won - F) / M
    if base <= 0:
        return {"ok": False, "note": "목표 매출이 정액·옵션 합보다 작아 기준단가가 음수입니다 — 목표를 확인하세요."}
    base = base.quantize(Decimal("1"), ROUND_HALF_UP)

    # 전 타입에 균일 기준단가(PER_AREA, 공급) 반영 후 재생성.
    for t in types.values():
        br = base_rows.get(t.id)
        if br:
            br.basis = "PER_AREA"; br.base_unit_price = int(base); br.base_area_kind = br.base_area_kind or "supply"
        else:
            db.add(SalesPriceBase(site_id=site_id, round_id=round_id, type_id=t.id,
                   basis="PER_AREA", base_unit_price=int(base), base_area_kind="supply", round_factor=1))
    await db.flush()
    await generate_price_table(db, site_id, round_id, by=by)
    rev = await project_revenue(db, site_id, round_id)
    return {"ok": True, "base_unit_price": int(base), "target_total_10k": int(target_total_10k),
            "achieved_total_10k": rev["total_revenue_10k"], "units_priced": rev["units_priced"]}


async def apply_group_pricing(
    db: AsyncSession, site_id: uuid.UUID, round_id: uuid.UUID,
    unit_ids: list[uuid.UUID], mode: str, value: float, group_name: str | None = None, by=None,
) -> dict:
    """P1-4 선택 세대 그룹 일괄단가 적용 후 재생성.

    mode:
      RATE          그룹 가중치 +value(예 0.05=+5%)  — SalesPriceGroup(basis=RATE)
      FIXED         그룹 가중치 +value 원             — SalesPriceGroup(basis=FIXED)
      OVERRIDE_PSQM 선택 세대에 절대 평당단가 value(원/㎡)×공급면적 = 확정금액(override)
    """
    uids = [u for u in unit_ids if u]
    if not uids:
        return {"ok": False, "note": "선택된 세대가 없습니다."}
    if mode in ("RATE", "FIXED"):
        g = SalesPriceGroup(site_id=site_id, group_name=group_name or "그룹",
                            basis=mode, value=value, priority=10)
        db.add(g)
        await db.flush()
        for uid in uids:
            db.add(SalesPriceGroupMember(group_id=g.id, unit_id=uid))
    elif mode == "OVERRIDE_PSQM":
        types = {t.id: t for t in (await db.execute(select(SalesUnitType).where(
            SalesUnitType.site_id == site_id))).scalars()}
        units = {u.id: u for u in (await db.execute(select(SalesUnitInventory).where(
            SalesUnitInventory.id.in_(uids)))).scalars()}
        for uid in uids:
            u = units.get(uid)
            t = types.get(u.type_id) if u else None
            if not t:
                continue
            area = Decimal(str(t.supply_area or t.contract_area or t.exclusive_area or 0))
            if area <= 0:
                continue
            amt = (Decimal(str(value)) * area).quantize(Decimal("1"), ROUND_HALF_UP)
            pt = (await db.execute(select(SalesUnitPriceTable).where(
                SalesUnitPriceTable.unit_id == uid, SalesUnitPriceTable.round_id == round_id))).scalar_one_or_none()
            if not pt:
                pt = SalesUnitPriceTable(site_id=site_id, unit_id=uid, round_id=round_id)
                db.add(pt)
            pt.price_mode = "FIXED"
            pt.override_price = int(amt)
    else:
        return {"ok": False, "note": f"알 수 없는 mode: {mode}"}
    await db.flush()
    n = await generate_price_table(db, site_id, round_id, by=by)
    rev = await project_revenue(db, site_id, round_id)
    return {"ok": True, "mode": mode, "applied_units": len(uids), "regenerated": n,
            "total_revenue_10k": rev["total_revenue_10k"]}


async def project_revenue(db: AsyncSession, site_id: uuid.UUID, round_id: uuid.UUID) -> dict:
    """현재 분양가표 기준 총매출(분양액) 산출 — forward. 타입별 분해 포함(만원 단위)."""
    rows = list((await db.execute(select(SalesUnitPriceTable).where(
        SalesUnitPriceTable.site_id == site_id, SalesUnitPriceTable.round_id == round_id))).scalars())
    types = {t.id: t for t in (await db.execute(select(SalesUnitType).where(
        SalesUnitType.site_id == site_id))).scalars()}
    units = {u.id: u for u in (await db.execute(select(SalesUnitInventory).where(
        SalesUnitInventory.site_id == site_id, SalesUnitInventory.deleted_at.is_(None)))).scalars()}
    # 분양가표 base_price/total_price 는 원(KRW) 단위. 만원(_10k) 표기는 ÷10000.
    total = Decimal(0)
    by_type: dict[str, dict] = {}
    for pt in rows:
        amt = Decimal(pt.total_price or pt.base_price or 0)
        total += amt
        u = units.get(pt.unit_id)
        _t = types.get(u.type_id) if u else None
        tname = _t.type_name if _t else "기타"
        e = by_type.setdefault(tname, {"count": 0, "total_10k": 0})
        e["count"] += 1
        e["total_10k"] += int(amt / 10000)
    # 원가구성 집계(토지비/건축비/업무대행비 + VAT) — decompose 결과(SalesUnitPriceBreakdown).
    _LBL = {"LAND": "토지비", "BUILD": "건축비", "CUSTOM": "업무대행비"}
    bd_rows = (await db.execute(
        select(SalesUnitPriceBreakdown.component_type,
               func.sum(SalesUnitPriceBreakdown.amount),
               func.sum(SalesUnitPriceBreakdown.vat_amount))
        .where(SalesUnitPriceBreakdown.site_id == site_id,
               SalesUnitPriceBreakdown.round_id == round_id)
        .group_by(SalesUnitPriceBreakdown.component_type))).all()
    breakdown = [{
        "component_type": ct, "label": _LBL.get(ct or "", ct or "기타"),
        "amount_10k": int((a or 0) / 10000), "vat_10k": int((v or 0) / 10000),
    } for ct, a, v in bd_rows]

    return {
        "round_id": str(round_id),
        "units_priced": len(rows),
        "total_revenue_won": int(total),            # 총분양액(원)
        "total_revenue_10k": int(total / 10000),    # 총분양액(만원)
        "avg_unit_10k": int(total / len(rows) / 10000) if rows else 0,
        "by_type": by_type,
        "breakdown": breakdown,                     # 원가구성(토지비/건축비/대행비·VAT, 만원)
    }
