"""데스크 운영 — 방문통계/물품수불/출퇴근."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.commission_mh_harness import MhInventoryItem, MhInventoryTxn, MhVisitor
from apps.api.database.models.sales.staff import SalesStaffAttendance


async def visit_stats(db: AsyncSession, site_id, since, until):
    rows = (await db.execute(
        select(func.date_trunc("hour", MhVisitor.checked_in_at).label("h"), func.count().label("c"))
        .where(MhVisitor.site_id == site_id, MhVisitor.checked_in_at.between(since, until))
        .group_by("h").order_by("h"))).all()
    return [{"hour": r.h.isoformat(), "visitors": r.c} for r in rows]


async def inventory_txn(db: AsyncSession, item_id, txn_type, qty, staff_id=None, memo=None):
    item = (await db.execute(select(MhInventoryItem).where(MhInventoryItem.id == item_id))).scalar_one()
    delta = qty if txn_type == "IN" else -qty
    if item.stock_qty is not None and item.stock_qty + delta < 0:
        raise ValueError("재고 부족")
    item.stock_qty = (item.stock_qty or 0) + delta
    db.add(MhInventoryTxn(item_id=item_id, txn_type=txn_type, qty=qty, staff_id=staff_id, memo=memo))
    await db.flush()
    return item.stock_qty


async def attendance_check(db: AsyncSession, site_id, staff_id, kind, lat=None, lng=None):
    if kind == "IN":
        a = SalesStaffAttendance(site_id=site_id, staff_id=staff_id, check_in=datetime.now(timezone.utc),
                                 method="QR", geo=(f"POINT({lng} {lat})" if lat and lng else None))
        db.add(a)
        await db.flush()
        return a
    a = (await db.execute(select(SalesStaffAttendance).where(
        SalesStaffAttendance.staff_id == staff_id, SalesStaffAttendance.check_out.is_(None))
        .order_by(SalesStaffAttendance.check_in.desc()).limit(1))).scalar_one_or_none()
    if a:
        a.check_out = datetime.now(timezone.utc)
        a.work_minutes = int((a.check_out - a.check_in).total_seconds() // 60)
    await db.flush()
    return a
