"""모델하우스 데스크 라우터 (sales_router 하위 /mh)."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_sales import SalesCtx, sales_ctx
from apps.api.database.models.sales.site_org import SalesSiteConfig
from app.services.sales.mh.checkin import checkin
from app.services.sales.mh.consent import template as consent_template
from app.services.sales.mh.match import match_staff
from app.services.sales.mh.notify import notify_designated
from app.services.sales.mh.ops import attendance_check, inventory_txn, visit_stats

mh_router = APIRouter(prefix="/mh", tags=["model-house"])


def _client_ip(request: Request) -> str | None:
    """동의 IP(고지이력). 프록시 환경은 X-Forwarded-For 첫 IP 우선."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


@mh_router.get("/consent-template")
async def desk_consent_template(_ctx: SalesCtx = Depends(sales_ctx)):
    """방문객 동의 고지문(수집항목·이용목적·보유기간 + 필수/선택 분리). 동의팝업이 렌더."""
    return consent_template()


@mh_router.post("/visitors/checkin")
async def desk_checkin(body: dict, request: Request, db: AsyncSession = Depends(get_db),
                       ctx: SalesCtx = Depends(sales_ctx)):
    v = await checkin(db, ctx.site_id, body.get("desk_id"), body, consent_ip=_client_ip(request))
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
