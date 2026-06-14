"""Part5 라이프사이클 액션 — 청약 배정/예비/선착순 + 옵션 + 대출실행 + 수납(VA/대사/수동매칭)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
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
async def va_issue(body: dict, db: AsyncSession = Depends(get_db),
                   ctx: SalesCtx = Depends(require_role("AGENCY", "DIRECTOR", "GM_DIRECTOR", "DEVELOPER"))):
    # 가상계좌 발급은 자금 흐름과 직결되는 민감 작업 → 일반 팀원(MEMBER)이 아닌 관리 권한만 허용.
    from fastapi import HTTPException
    try:
        cid = uuid.UUID(str(body["contract_id"]))
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "contract_id가 올바르지 않습니다.") from None
    if not body.get("bank") or not body.get("va_number"):
        raise HTTPException(400, "은행·가상계좌번호는 필수입니다.")
    await issue_va(db, ctx.site_id, cid, body["bank"],
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
    from fastapi import HTTPException

    from apps.api.database.models.sales.contract_crm_ad import SalesContractExt, SalesContractInstallment
    from apps.api.database.models.sales.payment import SalesPayment
    try:
        inst_id = uuid.UUID(str(body["installment_id"]))
        contract_id = uuid.UUID(str(body["contract_id"]))
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "installment_id·contract_id가 올바르지 않습니다.") from None
    # 같은 현장(site_id)의 결제만 수동매칭 허용 — 타 현장 결제 위조 차단.
    p = (await db.execute(select(SalesPayment).where(
        SalesPayment.id == payment_id, SalesPayment.site_id == ctx.site_id))).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "결제 내역을 찾을 수 없습니다.")
    # 이미 매칭된 결제를 또 매칭하면 회차 납입액이 이중 가산된다 → 막는다(멱등 가드).
    if p.matched:
        raise HTTPException(409, "이미 대사 완료된 입금입니다.")
    # 대상 회차도 같은 현장 계약 소속인지 확인(교차 테넌트 충당 방지).
    it = (await db.execute(select(SalesContractInstallment)
        .join(SalesContractExt, SalesContractExt.id == SalesContractInstallment.contract_ext_id)
        .where(SalesContractInstallment.id == inst_id,
               SalesContractExt.site_id == ctx.site_id))).scalar_one_or_none()
    if it is None:
        raise HTTPException(404, "해당 현장의 회차를 찾을 수 없습니다.")
    p.installment_id = inst_id
    p.contract_ext_id = contract_id
    p.matched = True
    it.paid_amount = (it.paid_amount or 0) + (p.amount or 0)
    it.paid_at = datetime.now(UTC)
    await db.commit()
    return {"matched": True}


# ── #4 할인/환급 + 계약자별 통합 수납현황 ──────────────────────────────────────
# 회차(installment 납부)·연체(SalesOverdueInterest)는 기존 존재. 할인/환급은 별도 조정 레코드로
# 멱등 테이블에 적립하고, 계약자 기준으로 납부/연체/할인/환급을 한 번에 집계한다(가짜값 없음).
_ADJ_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_payment_adjustments ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  site_id uuid NOT NULL,"
    "  contract_ext_id uuid NOT NULL,"
    "  adj_type varchar(12) NOT NULL,"          # DISCOUNT(할인) | REFUND(환급)
    "  amount numeric(16,0) NOT NULL,"
    "  reason text,"
    "  created_by uuid,"
    "  created_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_ADJ_READY = False


async def _ensure_adj(db: AsyncSession) -> None:
    global _ADJ_READY
    if _ADJ_READY:
        return
    await db.execute(text(_ADJ_DDL))
    await db.commit()
    _ADJ_READY = True


@r5.post("/payments/adjustment")
async def payment_adjustment(body: dict, db: AsyncSession = Depends(get_db),
                             ctx: SalesCtx = Depends(require_role("AGENCY", "GM_DIRECTOR", "DIRECTOR", "DEVELOPER"))):
    """할인(DISCOUNT)·환급(REFUND) 조정 등록. amount는 원(KRW) 양수."""
    from fastapi import HTTPException
    await _ensure_adj(db)
    try:
        cid = uuid.UUID(str(body["contract_ext_id"]))
        atype = str(body["adj_type"]).upper()
        amount = int(body["amount"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "contract_ext_id·adj_type(DISCOUNT/REFUND)·amount 필요") from None
    if atype not in ("DISCOUNT", "REFUND") or amount <= 0:
        raise HTTPException(400, "adj_type은 DISCOUNT/REFUND, amount는 양수여야 합니다.")
    await db.execute(text(
        "INSERT INTO sales_payment_adjustments (site_id, contract_ext_id, adj_type, amount, reason, created_by) "
        "VALUES (:s,:c,:t,:a,:r,:u)"),
        {"s": str(ctx.site_id), "c": str(cid), "t": atype, "a": amount,
         "r": body.get("reason"), "u": str(getattr(ctx.user, "id", "")) or None})
    await db.commit()
    return {"ok": True, "adj_type": atype, "amount": amount}


@r5.get("/payments/contract-summary")
async def payment_contract_summary(contract_id: str, db: AsyncSession = Depends(get_db),
                                   ctx: SalesCtx = Depends(sales_ctx)):
    """계약자(계약) 기준 통합 수납현황 — 납부/연체/할인/환급(원 단위)."""
    from apps.api.database.models.sales.contract_crm_ad import SalesContractExt, SalesContractInstallment
    await _ensure_adj(db)
    cid = uuid.UUID(contract_id)
    c = (await db.execute(select(SalesContractExt).where(
        SalesContractExt.id == cid, SalesContractExt.site_id == ctx.site_id))).scalar_one_or_none()
    if not c:
        from fastapi import HTTPException
        raise HTTPException(404, "해당 현장의 계약을 찾을 수 없습니다.")
    insts = list((await db.execute(select(SalesContractInstallment).where(
        SalesContractInstallment.contract_ext_id == cid)
        .order_by(SalesContractInstallment.seq))).scalars())
    billed = sum(int(i.amount or 0) for i in insts)
    paid = sum(int(i.paid_amount or 0) for i in insts)
    today = datetime.now(UTC).date()
    overdue = [{"seq": i.seq, "due_date": str(i.due_date), "unpaid": int((i.amount or 0) - (i.paid_amount or 0))}
               for i in insts if i.due_date and i.due_date < today and (i.paid_amount or 0) < (i.amount or 0)]
    adj = (await db.execute(text(
        "SELECT adj_type, count(*), coalesce(sum(amount),0) FROM sales_payment_adjustments "
        "WHERE site_id=:s AND contract_ext_id=:c GROUP BY adj_type"),
        {"s": str(ctx.site_id), "c": str(cid)})).all()
    adj_map = {t: {"count": int(n), "amount": int(a)} for t, n, a in adj}
    return {
        "contract_id": str(cid),
        "total_price": int(c.total_price or 0),
        "installments": {"count": len(insts), "billed": billed, "paid": paid, "unpaid": billed - paid},
        "overdue": {"count": len(overdue), "items": overdue,
                    "unpaid_amount": sum(o["unpaid"] for o in overdue)},
        "discount": adj_map.get("DISCOUNT", {"count": 0, "amount": 0}),
        "refund": adj_map.get("REFUND", {"count": 0, "amount": 0}),
    }


@r5.get("/payments/installments")
async def payment_installments(contract_id: str, db: AsyncSession = Depends(get_db),
                               ctx: SalesCtx = Depends(sales_ctx)):
    """계약 회차별 납부 스케줄 — 계약금·중도금·잔금 회차의 약정일·금액·납부·미납·상태(PAID/PARTIAL/UNPAID/OVERDUE)
    + 연체(일수·이자)를 오늘 기준으로 실시간 산출. 자금이동 미수행(현황·산출만)."""
    from decimal import Decimal

    from fastapi import HTTPException

    from apps.api.database.models.sales.contract_crm_ad import SalesContractExt, SalesContractInstallment
    from apps.api.database.models.sales.site_org import SalesSiteConfig
    cid = uuid.UUID(contract_id)
    c = (await db.execute(select(SalesContractExt).where(
        SalesContractExt.id == cid, SalesContractExt.site_id == ctx.site_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "해당 현장의 계약을 찾을 수 없습니다.")
    cfg = (await db.execute(select(SalesSiteConfig).where(
        SalesSiteConfig.site_id == ctx.site_id))).scalar_one_or_none()
    # 연체이율(약관 파라미터, 0이면 미설정 → 이자 0).
    rate = float(((cfg.stage_def if cfg else None) or {}).get("overdue_rate", 0))
    insts = list((await db.execute(select(SalesContractInstallment).where(
        SalesContractInstallment.contract_ext_id == cid).order_by(SalesContractInstallment.seq))).scalars())
    today = datetime.now(UTC).date()
    kind_label = {"DOWN": "계약금", "MIDDLE": "중도금", "BALANCE": "잔금", "OPTION": "옵션"}
    rows = []
    t_billed = t_paid = t_unpaid = t_interest = 0
    for it in insts:
        amt = int(it.amount or 0)
        paid = int(it.paid_amount or 0)
        unpaid = amt - paid
        overdue_days = 0
        interest = 0
        if unpaid <= 0:
            status = "PAID"
        elif paid > 0:
            status = "PARTIAL"
        else:
            status = "UNPAID"
        if unpaid > 0 and it.due_date and it.due_date < today:
            status = "OVERDUE"
            overdue_days = (today - it.due_date).days
            interest = int(Decimal(unpaid) * overdue_days * (Decimal(str(rate)) / Decimal(365)))
        rows.append({
            "seq": it.seq, "kind": it.kind,
            "kind_label": kind_label.get((it.kind or "").upper(), it.kind),
            "amount": amt, "paid_amount": paid, "unpaid": unpaid,
            "due_date": str(it.due_date) if it.due_date else None,
            "paid_at": str(it.paid_at) if it.paid_at else None,
            "status": status, "overdue_days": overdue_days, "overdue_interest": interest,
        })
        t_billed += amt
        t_paid += paid
        t_unpaid += unpaid
        t_interest += interest
    return {
        "contract_id": str(cid), "total_price": int(c.total_price or 0),
        "overdue_rate": rate, "as_of": str(today), "count": len(rows), "installments": rows,
        "totals": {"billed": t_billed, "paid": t_paid, "unpaid": t_unpaid, "overdue_interest": t_interest},
    }
