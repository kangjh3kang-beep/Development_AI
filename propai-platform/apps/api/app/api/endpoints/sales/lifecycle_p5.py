"""Part5 라이프사이클 액션 — 청약 배정/예비/선착순 + 옵션 + 대출실행 + 수납(VA/대사/수동매칭)."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_sales import SalesCtx, require_role, sales_ctx
from app.services.sales.loan.service import execute_disbursement
from app.services.sales.options.service import add_option
from app.services.sales.payment.service import ingest_payment, issue_va
from app.services.sales.subscription.engine import claim_offer, promote_reserve, run_draw

r5 = APIRouter(tags=["sales-p5"])


@r5.post("/subscription/{ann_id}/draw")
async def draw(ann_id: uuid.UUID, body: dict | None = None, db: AsyncSession = Depends(get_db),
               ctx: SalesCtx = Depends(require_role("DEVELOPER", "AGENCY"))):
    n = await run_draw(db, ctx.site_id, ann_id, (body or {}).get("seed"))
    await db.commit()
    return {"winners": n}


@r5.post("/subscription/reserve/promote")
async def reserve_promote(body: dict, db: AsyncSession = Depends(get_db),
                          ctx: SalesCtx = Depends(require_role("DEVELOPER", "AGENCY", "DIRECTOR"))):
    aid = await promote_reserve(db, ctx.site_id, uuid.UUID(body["unit_id"]), by=ctx.user.id)
    await db.commit()
    return {"promoted_application": str(aid) if aid else None}


@r5.post("/subscription/claim")
async def subscription_claim(body: dict, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    uid = await claim_offer(db, ctx.site_id, uuid.UUID(body["unit_id"]),
                            body.get("customer_id"), body.get("kind", "FCFS"))
    await db.commit()
    return {"unit_id": str(uid)}


@r5.post("/contracts/{contract_id}/options")
async def contract_add_option(contract_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                              ctx: SalesCtx = Depends(sales_ctx)):
    res = await add_option(db, contract_id, uuid.UUID(body["option_id"]), int(body.get("qty", 1)))
    await db.commit()
    return res


@r5.post("/loan/disburse")
async def loan_disburse(body: dict, db: AsyncSession = Depends(get_db),
                        ctx: SalesCtx = Depends(require_role("DEVELOPER", "AGENCY"))):
    await execute_disbursement(db, ctx.site_id, uuid.UUID(body["agreement_id"]),
                               int(body["installment_seq"]), int(body["amount"]), body.get("disbursed_at"))
    await db.commit()
    return {"ok": True}


@r5.post("/payments/va/issue")
async def va_issue(body: dict, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    await issue_va(db, ctx.site_id, uuid.UUID(body["contract_id"]), body["bank"],
                   body["va_number"], body.get("holder"), body.get("pool_ref"))
    await db.commit()
    return {"ok": True}


@r5.post("/payments/webhook")
async def payments_webhook(body: dict, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    res = await ingest_payment(db, ctx.site_id, body)
    await db.commit()
    return res


@r5.post("/payments/{payment_id}/manual-match")
async def manual_match(payment_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                       ctx: SalesCtx = Depends(require_role("AGENCY", "DIRECTOR", "DEVELOPER"))):
    from apps.api.database.models.sales.contract_crm_ad import SalesContractInstallment
    from apps.api.database.models.sales.payment import SalesPayment
    p = (await db.execute(select(SalesPayment).where(SalesPayment.id == payment_id))).scalar_one()
    p.installment_id = uuid.UUID(body["installment_id"])
    p.contract_ext_id = uuid.UUID(body["contract_id"])
    p.matched = True
    it = (await db.execute(select(SalesContractInstallment).where(
        SalesContractInstallment.id == p.installment_id))).scalar_one()
    it.paid_amount = (it.paid_amount or 0) + (p.amount or 0)
    it.paid_at = datetime.now(timezone.utc)
    await db.commit()
    return {"matched": True}
