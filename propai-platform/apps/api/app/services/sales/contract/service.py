"""계약 상태머신 — 서명(동호 CONTRACTED + 회차 자동생성 + 수수료 split + 투영),
취소(동호 CANCELLED + 변경 스냅샷 + 수수료 환수 + 투영). 1호 1계약은 동호 유니크로 보장.
"""

import uuid
from datetime import datetime, timedelta, timezone, UTC

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


async def create_contract(db: AsyncSession, site_id, unit_id, customer_id=None, round_id=None,
                          total_price=None, member_node_id=None, by=None):
    """계약 체결(최초 생성) — 세대 1호에 계약 1건을 만든다.

    이 함수가 없으면 '청약/세대 → 계약 → 수납/대출/전매'로 이어지는 전주기 흐름이 끊겨
    수납·대출·전매 화면의 계약 선택 목록이 항상 비게 된다(연결성 핵심).

    - total_price 미지정 시 해당 세대의 가격표(sales_unit_price_table)에서 자동으로 끌어온다.
    - 세대 상태를 RESERVED(예약)로 바꾸고, 다른 화면들이 곧바로 이 계약을 선택할 수 있게 한다.
    - member_node_id: 이 계약을 담당한 영업사원(조직도 노드). 이게 있어야 계약 체결 시
      수수료가 그 사원→상위 조직으로 배분된다(없으면 split이 빈 체인이라 아무도 수수료를 못 받음).
    """
    from sqlalchemy import desc

    from apps.api.database.models.sales.units_pricing import SalesUnitPriceTable

    unit = (await db.execute(select(SalesUnitInventory).where(SalesUnitInventory.id == unit_id))).scalar_one_or_none()
    if unit is None:
        raise ValueError("세대를 찾을 수 없습니다")
    if unit.status == "CONTRACTED":
        raise ValueError("이미 계약된 세대입니다")  # 1호 1계약(동호 유니크)

    # 금액이 안 넘어오면 세대 가격표에서 최신 round의 총액을 가져온다.
    price = total_price
    if price is None:
        q = select(SalesUnitPriceTable).where(SalesUnitPriceTable.unit_id == unit_id)
        if round_id:
            q = q.where(SalesUnitPriceTable.round_id == round_id)
        pt = (await db.execute(q.order_by(desc(SalesUnitPriceTable.id)))).scalars().first()
        if pt is not None:
            price = int(pt.override_price or pt.total_price or pt.base_price or 0)
        # 폴백: per-unit 가격표가 없으면(가격표 미생성) 기준단가(SalesPriceBase)에서 직접 산정.
        # 없을 경우 total_price=NULL→수수료·할부·연체 전량 0 cascade 가 발생하므로 자동해소한다.
        if not price:
            from app.services.sales.pricing.engine import resolve_unit_price
            price = await resolve_unit_price(db, site_id, unit, round_id)

    c = SalesContractExt(site_id=site_id, unit_id=unit_id, customer_id=customer_id,
                         round_id=round_id, member_node_id=member_node_id, stage="RESERVED", status="ACTIVE",
                         total_price=int(price) if price else None)
    db.add(c)
    await _set_unit_status(db, unit_id, "RESERVED", by)  # 예약 상태로 전환(청약·배치도와 동기화)
    await db.flush()
    return c


async def sign_contract(db: AsyncSession, site_id, contract_id, by=None):
    c = (await db.execute(select(SalesContractExt).where(SalesContractExt.id == contract_id))).scalar_one()
    # 이미 서명됐거나 취소된 계약을 또 서명하면 회차표·수수료가 중복 생성된다 → 막는다(멱등 가드).
    if c.stage != "RESERVED" or c.status != "ACTIVE":
        raise ValueError(f"서명할 수 없는 계약 상태입니다(현재 단계={c.stage}, 상태={c.status}). 예약(RESERVED) 상태에서만 서명 가능합니다.")
    c.stage = "SIGNED"
    c.signed_at = datetime.now(UTC)
    await _set_unit_status(db, c.unit_id, "CONTRACTED", by)  # 동호 유니크로 1호 1계약 보장

    cfg = (await db.execute(select(SalesSiteConfig).where(SalesSiteConfig.site_id == site_id))).scalar_one_or_none()
    sched = ((cfg.installment_schedule if cfg else None) or {}).get("default", [])
    base = datetime.now(UTC).date()
    for i, s in enumerate(sched, start=1):
        db.add(SalesContractInstallment(
            contract_ext_id=c.id, seq=i, kind=s["kind"],
            due_date=base + timedelta(days=int(s["after_days"])),
            amount=int(round(float(c.total_price or 0) * float(s["ratio"]))),
        ))
    await split_commission(db, site_id, c)
    await emit_outbox(db, site_id, "ContractSigned",
                      {"unit_id": str(c.unit_id), "amount": int(c.total_price or 0), "stage": "SIGNED"})
    await db.flush()
    return c


async def cancel_contract(db: AsyncSession, site_id, contract_id, reason: str, by=None):
    c = (await db.execute(select(SalesContractExt).where(SalesContractExt.id == contract_id))).scalar_one()
    db.add(SalesContractChange(
        contract_ext_id=c.id, change_type="CANCEL", effective_at=datetime.now(UTC),
        reason=reason, prev_snapshot={"stage": c.stage, "total_price": int(c.total_price or 0)},
    ))
    c.status = "CANCELLED"
    c.stage = "CANCELLED"
    # 계약은 취소(CANCELLED)로 남기되, 세대(호실)는 다시 'AVAILABLE'로 되돌려 재분양이 가능하게 한다.
    # (이전엔 세대를 CANCELLED로 막아버려 해지 후 같은 호실을 영영 다시 팔 수 없는 결함이 있었음.)
    await _set_unit_status(db, c.unit_id, "AVAILABLE", by)
    ev = (await db.execute(select(SalesCommissionEvent).where(
        SalesCommissionEvent.contract_ext_id == c.id))).scalar_one_or_none()
    if ev:
        await clawback(db, ev.id, reason)
    await emit_outbox(db, site_id, "ContractCancelled",
                      {"unit_id": str(c.unit_id), "amount": int(c.total_price or 0)})
    await db.flush()
    return c
