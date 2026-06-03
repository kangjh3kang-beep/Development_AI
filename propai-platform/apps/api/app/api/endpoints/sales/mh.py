"""모델하우스 데스크 라우터 (sales_router 하위 /mh)."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_sales import SalesCtx, sales_ctx
from apps.api.database.models.sales.site_org import SalesSiteConfig
from app.services.sales.mh.checkin import checkin
from app.services.sales.mh.match import match_staff
from app.services.sales.mh.notify import notify_designated
from app.services.sales.mh.ops import attendance_check, inventory_txn, visit_stats

mh_router = APIRouter(prefix="/mh", tags=["model-house"])


@mh_router.post("/visitors/checkin")
async def desk_checkin(body: dict, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    v = await checkin(db, ctx.site_id, body.get("desk_id"), body)
    await db.commit()
    return {"visitor_id": str(v.id)}


@mh_router.post("/match")
async def desk_match(body: dict, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    res = await match_staff(db, ctx.site_id, uuid.UUID(body["visitor_id"]), body["input_type"], body["raw"])
    await db.commit()
    return res


@mh_router.post("/notify")
async def desk_notify(body: dict, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    cfg = (await db.execute(select(SalesSiteConfig).where(SalesSiteConfig.site_id == ctx.site_id))).scalar_one_or_none()
    await notify_designated(db, ctx.site_id, uuid.UUID(body["visitor_id"]), uuid.UUID(body["staff_id"]),
                            masking_policy=(cfg.masking_policy if cfg else None))
    await db.commit()
    return {"ok": True}


@mh_router.get("/stats")
async def desk_stats(hours: int = 24, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    until = datetime.now(timezone.utc)
    since = until - timedelta(hours=hours)
    return await visit_stats(db, ctx.site_id, since, until)


@mh_router.post("/inventory/txn")
async def desk_inv(body: dict, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    qty = await inventory_txn(db, uuid.UUID(body["item_id"]), body["txn_type"], int(body["qty"]),
                              body.get("staff_id"), body.get("memo"))
    await db.commit()
    return {"stock_qty": qty}


@mh_router.post("/attendance/check")
async def desk_att(body: dict, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    a = await attendance_check(db, ctx.site_id, uuid.UUID(body["staff_id"]), body["kind"],
                               body.get("lat"), body.get("lng"))
    await db.commit()
    return {"id": str(a.id) if a else None}
