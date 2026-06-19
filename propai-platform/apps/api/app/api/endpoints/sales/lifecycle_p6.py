"""Part6 라이프사이클 — 보증/신탁 점검 + 실거래/전매 + 수수료 분할·유보 + 세무."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_sales import SalesCtx, require_role, sales_ctx
from app.services.sales.commission.extension import (
    create_schedule,
    release_holdback,
    run_due_payouts,
    set_holdback,
)
from app.services.sales.guarantee.service import guarantee_check
from app.services.sales.resale.service import (
    create_realtx_report,
    decide_transfer,
    request_transfer,
    submit_realtx,
)
from app.services.sales.tax.service import (
    build_withholding_statements,
    issue_tax_invoice,
    read_withholding_statements,
)

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
        # ★[응답계약 SSOT(iter-2 MED)] decide_transfer 의 결과(allowed/reason/already_decided)를 버리지
        #   않고 그대로 응답한다 — resale_request 가 duplicate/transfer_type 을 돌려주는 것과 대칭.
        #   프론트가 already_decided 를 받아 '이미 결정된 요청' 안내를 띄울 수 있게 한다(silent 성공 위장 금지).
        res = await decide_transfer(db, transfer_id, bool(body.get("allowed")),
                                    body.get("reason", ""), site_id=ctx.site_id)
    except ValueError as e:
        await db.rollback()
        raise HTTPException(404, str(e)) from e
    await db.commit()
    return res


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
    # ★[GET 시맨틱 복원(iter-7 HIGH)] 과거엔 GET 이 build(db.add+commit)를 호출하는 비멱등 쓰기였고,
    #   (site,period,node) 유니크가 없어 재호출마다 명세가 중복누적됐다(법적 서류 중복). 이제 GET 은
    #   '적재된 명세 조회 전용'(쓰기 없음)이고, 빌드(쓰기)는 아래 POST /build 로 분리됐다.
    #   응답계약(period/gross/withholding 합계 + items)은 동일 유지(무회귀). 아직 빌드 전이면 빈 items.
    items = await read_withholding_statements(db, ctx.site_id, period)
    gross = sum(it["gross"] for it in items)
    withholding = sum(it["withholding"] for it in items)
    return {"period": period, "gross": gross, "withholding": withholding, "items": items}


@r6.post("/tax/withholding-statements/build")
async def tax_wh_build(body: dict, db: AsyncSession = Depends(get_db),
                       ctx: SalesCtx = Depends(require_role("AGENCY", "DEVELOPER"))):
    # ★[쓰기 분리·멱등(iter-7 HIGH)] 지급명세서 적재(쓰기)는 POST 로만 한다. build 는 동일 (site,period)
    #   명세를 delete-before-insert 로 재집계하므로 같은 기간을 몇 번 빌드해도 행수·합계가 불변이다
    #   (정본 멱등키는 Alembic 034 — 동시 빌드 race 까지 차단). 응답은 빌드된 노드별 내역 + 합계.
    from fastapi import HTTPException
    period = body.get("period")
    if not period:
        raise HTTPException(400, "period(YYYY-MM)가 필요합니다")
    sts = await build_withholding_statements(db, ctx.site_id, period)
    await db.commit()
    gross = sum(int(s.gross or 0) for s in sts)
    withholding = sum(int(s.withholding or 0) for s in sts)
    return {"period": period, "gross": gross, "withholding": withholding,
            "items": [{"payee_node_id": str(s.payee_node_id) if s.payee_node_id else None,
                       "gross": int(s.gross or 0), "withholding": int(s.withholding or 0)} for s in sts]}


@r6.post("/tax/invoices")
async def tax_inv(body: dict, db: AsyncSession = Depends(get_db),
                  ctx: SalesCtx = Depends(require_role("AGENCY", "DEVELOPER"))):
    inv = await issue_tax_invoice(db, ctx.site_id, body["direction"], body.get("counterparty_biz_no"),
                                  int(body.get("supply_amount", 0)), int(body.get("vat_amount", 0)), body.get("item"))
    await db.commit()
    return {"id": str(inv.id), "status": inv.status}
