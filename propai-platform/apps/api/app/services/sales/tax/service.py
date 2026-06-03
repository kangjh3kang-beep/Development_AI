"""세무 — 지급명세서(수수료 원천징수 집계)/세금계산서(건물 과세·토지 면세). 산출/기록만, 제출은 어댑터+승인."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.commission_mh_harness import SalesCommissionClaim, SalesCommissionPayout
from apps.api.database.models.sales.tax import SalesTaxInvoice, SalesWithholdingStatement
from apps.api.database.models.sales.units_pricing import SalesUnitPriceBreakdown


async def build_withholding_statements(db: AsyncSession, site_id, period: str):
    """기간(YYYY-MM) 내 현장 수수료 지급(원천징수) 집계 → 지급명세서. claim 경유 site 스코프."""
    row = (await db.execute(
        select(func.coalesce(func.sum(SalesCommissionPayout.gross), 0),
               func.coalesce(func.sum(SalesCommissionPayout.withholding), 0))
        .join(SalesCommissionClaim, SalesCommissionClaim.id == SalesCommissionPayout.claim_id)
        .where(SalesCommissionClaim.site_id == site_id,
               func.to_char(SalesCommissionPayout.paid_at, "YYYY-MM") == period))).one()
    gross, wh = int(row[0] or 0), int(row[1] or 0)
    st = SalesWithholdingStatement(site_id=site_id, period=period, income_type="BIZ_3_3",
                                   gross=gross, withholding=wh)
    db.add(st)
    await db.flush()
    return st


async def issue_tax_invoice(db: AsyncSession, site_id, direction, counterparty_biz_no,
                            supply_amount, vat_amount, item):
    inv = SalesTaxInvoice(site_id=site_id, direction=direction, counterparty_biz_no=counterparty_biz_no,
                          supply_amount=supply_amount, vat_amount=vat_amount, item=item,
                          issued_at=datetime.now(timezone.utc), status="DRAFT")
    db.add(inv)
    await db.flush()
    return inv


async def vat_summary_from_breakdown(db: AsyncSession, site_id, round_id) -> dict:
    """분양가 구성의 공급가/VAT(건물 과세) 합계 → 세금계산서 기초자료."""
    row = (await db.execute(
        select(func.coalesce(func.sum(SalesUnitPriceBreakdown.amount), 0),
               func.coalesce(func.sum(SalesUnitPriceBreakdown.vat_amount), 0))
        .where(SalesUnitPriceBreakdown.site_id == site_id,
               SalesUnitPriceBreakdown.round_id == round_id))).one()
    return {"supply": int(row[0] or 0), "vat": int(row[1] or 0)}
