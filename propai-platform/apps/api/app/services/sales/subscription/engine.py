"""청약 배정 엔진 — 가점/추첨/특공 + 예비순번 + 선착순/무순위. 추첨은 시드 고정(감사 가능)."""

import hashlib
from datetime import datetime, timedelta, timezone
from itertools import groupby

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.subscription import (
    SalesSubscriptionAnnouncement, SalesSubscriptionApplication, SalesSubscriptionReserveQueue,
    SalesSubscriptionWinner, SalesUnrankedOffer,
)
from apps.api.database.models.sales.units_pricing import SalesUnitInventory
from app.services.sales.harness.outbox import emit_outbox


def _tiebreak(seed, app_id) -> str:
    return hashlib.sha256(f"{seed}:{app_id}".encode()).hexdigest()


def _rank_pick(apps, n, seed):
    ordered = sorted(apps, key=lambda a: ((a.rank or 9), -(float(a.gajeom_score or 0)), _tiebreak(seed, a.id)))
    n = max(int(n), 0)
    return ordered[:n], ordered[n:]


async def _available_units(db, site_id, type_id):
    return list((await db.execute(select(SalesUnitInventory).where(
        SalesUnitInventory.site_id == site_id, SalesUnitInventory.type_id == type_id,
        SalesUnitInventory.status == "AVAILABLE", SalesUnitInventory.deleted_at.is_(None)))).scalars())


async def run_draw(db: AsyncSession, site_id, announcement_id, seed: str | None = None) -> int:
    ann = (await db.execute(select(SalesSubscriptionAnnouncement).where(
        SalesSubscriptionAnnouncement.id == announcement_id))).scalar_one()
    seed = seed or ann.announce_no or str(announcement_id)
    rules = ann.rules or {}
    special_ratio = rules.get("special_ratio", {})  # {type_id: 0~1} 파라미터
    apps = list((await db.execute(select(SalesSubscriptionApplication).where(
        SalesSubscriptionApplication.announcement_id == announcement_id,
        SalesSubscriptionApplication.eligibility == "OK"))).scalars())
    apps.sort(key=lambda a: str(a.unit_type_id))
    total_win = 0
    for type_id, grp in groupby(apps, key=lambda a: a.unit_type_id):
        group = list(grp)
        units = await _available_units(db, site_id, type_id)
        quota = len(units)
        sp_quota = int(quota * float(special_ratio.get(str(type_id), 0)))
        specials = [a for a in group if a.supply_class == "SPECIAL"]
        generals = [a for a in group if a.supply_class == "GENERAL"]
        win_sp, rest_sp = _rank_pick(specials, sp_quota, seed)
        win_gen, _rest_gen = _rank_pick(generals + rest_sp, quota - len(win_sp), seed)
        winners = [(a, "SPECIAL") for a in win_sp] + [(a, "GENERAL") for a in win_gen]
        for (a, wtype), unit in zip(winners, units):
            a.result = "WIN"
            db.add(SalesSubscriptionWinner(
                site_id=site_id, application_id=a.id, unit_id=unit.id, win_type=wtype, status="NOTIFIED",
                contract_due=(ann.contract_end or (datetime.now(timezone.utc).date() + timedelta(days=7)))))
            unit.status = "APPLIED"
            total_win += 1
        for i, a in enumerate(_rest_gen, start=1):
            a.result = "RESERVE"
            db.add(SalesSubscriptionReserveQueue(site_id=site_id, announcement_id=announcement_id,
                   application_id=a.id, unit_type_id=type_id, reserve_no=i))
    ann.status = "DRAWN"
    await emit_outbox(db, site_id, "ApplicationReceived", {"round_id": str(ann.round_id or ""), "unit_id": ""})
    await db.flush()
    return total_win


async def promote_reserve(db: AsyncSession, site_id, unit_id, by=None):
    unit = (await db.execute(select(SalesUnitInventory).where(SalesUnitInventory.id == unit_id))).scalar_one()
    nxt = (await db.execute(select(SalesSubscriptionReserveQueue).where(
        SalesSubscriptionReserveQueue.site_id == site_id,
        SalesSubscriptionReserveQueue.unit_type_id == unit.type_id,
        SalesSubscriptionReserveQueue.promoted.is_(False))
        .order_by(SalesSubscriptionReserveQueue.reserve_no).limit(1))).scalar_one_or_none()
    if not nxt:
        return None
    nxt.promoted = True
    db.add(SalesSubscriptionWinner(site_id=site_id, application_id=nxt.application_id, unit_id=unit_id,
           win_type="RESERVE", status="NOTIFIED"))
    unit.status = "APPLIED"
    await db.flush()
    return nxt.application_id


async def claim_offer(db: AsyncSession, site_id, unit_id, customer_id, kind="FCFS"):
    unit = (await db.execute(select(SalesUnitInventory).where(SalesUnitInventory.id == unit_id))).scalar_one()
    if unit.status != "AVAILABLE":
        raise ValueError("이미 점유된 세대")
    if kind == "UNRANKED":
        db.add(SalesUnrankedOffer(site_id=site_id, unit_id=unit_id, claimed_by=customer_id,
               claimed_at=datetime.now(timezone.utc)))
    unit.status = "APPLIED"
    await db.flush()
    return unit_id
