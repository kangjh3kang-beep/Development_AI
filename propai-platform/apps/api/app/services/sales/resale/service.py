"""실거래신고/전매제한 — 신고기한(파라미터) 산정, 전매제한 검사로 명의변경 차단/허용. 기록만."""

from datetime import date, datetime, timedelta, timezone, UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.contract_crm_ad import SalesContractExt
from apps.api.database.models.sales.resale import (
    SalesRealtxReport, SalesResaleRestriction, SalesResaleTransfer,
)
from apps.api.database.models.sales.site_org import SalesSiteConfig


async def create_realtx_report(db: AsyncSession, site_id, contract_id):
    cfg = (await db.execute(select(SalesSiteConfig).where(SalesSiteConfig.site_id == site_id))).scalar_one_or_none()
    report_days = int(((cfg.stage_def if cfg else None) or {}).get("realtx_report_days", 30))  # 신고기한(파라미터)
    c = (await db.execute(select(SalesContractExt).where(SalesContractExt.id == contract_id))).scalar_one()
    base = (c.signed_at or datetime.now(UTC)).date()
    db.add(SalesRealtxReport(site_id=site_id, contract_ext_id=contract_id, status="PENDING",
           due_date=base + timedelta(days=report_days),
           payload={"unit_id": str(c.unit_id), "amount": int(c.total_price or 0)}))
    await db.flush()


async def submit_realtx(db: AsyncSession, site_id, report_id, irts_result: dict):
    rpt = (await db.execute(select(SalesRealtxReport).where(SalesRealtxReport.id == report_id))).scalar_one()
    rpt.status = irts_result.get("status", "SUBMITTED")
    rpt.report_no = irts_result.get("report_no")
    rpt.reported_at = datetime.now(UTC)
    await db.flush()


async def request_transfer(db: AsyncSession, site_id, contract_id, to_customer, transfer_type, by=None):
    c = (await db.execute(select(SalesContractExt).where(SalesContractExt.id == contract_id))).scalar_one()
    restr = list((await db.execute(select(SalesResaleRestriction).where(
        SalesResaleRestriction.site_id == site_id,
        ((SalesResaleRestriction.unit_id == c.unit_id) |
         (SalesResaleRestriction.round_id == c.round_id))))).scalars())
    today = date.today()
    blocked = False
    note = ""
    for rs in restr:
        if rs.start_at and rs.months:
            end = rs.start_at + timedelta(days=rs.months * 30)
            if rs.start_at <= today <= end:
                blocked = True
                note = f"{rs.restriction_type} 제한기간 내(~{end})"
    t = SalesResaleTransfer(site_id=site_id, contract_ext_id=contract_id, from_customer=c.customer_id,
                            to_customer=to_customer, transfer_type=transfer_type,
                            allowed=(not blocked), reason=note or None)
    db.add(t)
    await db.flush()
    return {"transfer_id": str(t.id), "allowed": not blocked, "reason": note}


async def decide_transfer(db: AsyncSession, transfer_id, allowed: bool, reason: str = "", site_id=None):
    # site_id를 받으면 같은 현장의 전매요청만 처리 — 타 현장 명의변경 승인 차단(테넌트 격리).
    q = select(SalesResaleTransfer).where(SalesResaleTransfer.id == transfer_id)
    if site_id is not None:
        q = q.where(SalesResaleTransfer.site_id == site_id)
    t = (await db.execute(q)).scalar_one_or_none()
    if t is None:
        raise ValueError("전매 요청을 찾을 수 없습니다")
    t.allowed = allowed
    t.reason = reason
    t.decided_at = datetime.now(UTC)
    if allowed:  # 명의변경 반영
        c = (await db.execute(select(SalesContractExt).where(SalesContractExt.id == t.contract_ext_id))).scalar_one()
        c.customer_id = t.to_customer
    await db.flush()
