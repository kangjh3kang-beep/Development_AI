"""Part6 라이프사이클 — 보증/신탁 점검 + 실거래/전매 + 수수료 분할·유보 + 세무."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_sales import SalesCtx, require_role, sales_ctx
from app.services.sales.commission.extension import (
    create_schedule, release_holdback, run_due_payouts, set_holdback,
)
from app.services.sales.guarantee.service import guarantee_check
from app.services.sales.resale.service import (
    create_realtx_report, decide_transfer, request_transfer, submit_realtx,
)
from app.services.sales.tax.service import build_withholding_statements, issue_tax_invoice

r6 = APIRouter(tags=["sales-p6"])


@r6.get("/guarantee/check")
async def g_check(db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    return await guarantee_check(db, ctx.site_id)


@r6.post("/realtx/report")
async def realtx_report(body: dict, db: AsyncSession = Depends(get_db),
                        ctx: SalesCtx = Depends(require_role("AGENCY", "DEVELOPER"))):
    await create_realtx_report(db, ctx.site_id, uuid.UUID(body["contract_id"]))
    await db.commit()
    return {"ok": True}


@r6.post("/realtx/{report_id}/submit")
async def realtx_submit(report_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                        ctx: SalesCtx = Depends(require_role("AGENCY", "DEVELOPER"))):
    await submit_realtx(db, ctx.site_id, report_id, body)
    await db.commit()
    return {"ok": True}


@r6.post("/resale/transfer/request")
async def resale_request(body: dict, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    res = await request_transfer(db, ctx.site_id, uuid.UUID(body["contract_id"]),
                                 body.get("to_customer"), body.get("transfer_type", "RESALE"), by=ctx.user.id)
    await db.commit()
    return res


@r6.post("/resale/transfer/{transfer_id}/decide")
async def resale_decide(transfer_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                        ctx: SalesCtx = Depends(require_role("AGENCY", "DEVELOPER"))):
    from fastapi import HTTPException
    try:
        await decide_transfer(db, transfer_id, bool(body.get("allowed")), body.get("reason", ""), site_id=ctx.site_id)
    except ValueError as e:
        await db.rollback()
        raise HTTPException(404, str(e))
    await db.commit()
    return {"ok": True}


@r6.post("/commission/splits/{split_id}/schedule")
async def comm_schedule(split_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                        ctx: SalesCtx = Depends(require_role("AGENCY", "DEVELOPER"))):
    await create_schedule(db, split_id, body["milestones"])
    await db.commit()
    return {"ok": True}


@r6.post("/commission/holdback")
async def comm_holdback(body: dict, db: AsyncSession = Depends(get_db),
                        ctx: SalesCtx = Depends(require_role("AGENCY", "DEVELOPER"))):
    await set_holdback(db, uuid.UUID(body["split_id"]), body["reason"], int(body["amount"]),
                       body.get("release_condition"))
    await db.commit()
    return {"ok": True}


@r6.post("/commission/holdback/{holdback_id}/release")
async def comm_release(holdback_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                       ctx: SalesCtx = Depends(require_role("AGENCY", "DEVELOPER"))):
    await release_holdback(db, holdback_id)
    await db.commit()
    return {"ok": True}


@r6.post("/commission/payouts/run")
async def comm_payouts_run(db: AsyncSession = Depends(get_db),
                           ctx: SalesCtx = Depends(require_role("AGENCY", "DEVELOPER"))):
    n = await run_due_payouts(db, ctx.site_id, date.today())
    await db.commit()
    return {"paid": n}


@r6.get("/tax/withholding-statements")
async def tax_wh(period: str, db: AsyncSession = Depends(get_db),
                 ctx: SalesCtx = Depends(require_role("AGENCY", "DEVELOPER"))):
    st = await build_withholding_statements(db, ctx.site_id, period)
    await db.commit()
    return {"period": st.period, "gross": int(st.gross or 0), "withholding": int(st.withholding or 0)}


@r6.post("/tax/invoices")
async def tax_inv(body: dict, db: AsyncSession = Depends(get_db),
                  ctx: SalesCtx = Depends(require_role("AGENCY", "DEVELOPER"))):
    inv = await issue_tax_invoice(db, ctx.site_id, body["direction"], body.get("counterparty_biz_no"),
                                  int(body.get("supply_amount", 0)), int(body.get("vat_amount", 0)), body.get("item"))
    await db.commit()
    return {"id": str(inv.id), "status": inv.status}
