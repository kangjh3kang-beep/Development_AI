"""sales 읽기 뷰 — 프론트(현장목록/조직트리/Unit360/분양가표/시행사 투영) 지원 집계 엔드포인트."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.deps_sales import SalesCtx, sales_ctx
from apps.api.database.models.sales.contract_crm_ad import SalesContractExt, SalesContractInstallment
from apps.api.database.models.sales.site_org import SalesOrgNode, SalesSite, SalesSiteSummary
from apps.api.database.models.sales.units_pricing import (
    SalesUnitInventory, SalesUnitPriceBreakdown, SalesUnitPriceTable, SalesUnitStatusLog,
)

views_router = APIRouter(tags=["sales-views"])


@views_router.get("/sites")
async def list_sites(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """현재 테넌트(조직)의 분양 현장 목록 + 프로비저닝 진입점."""
    rows = (await db.execute(select(SalesSite).where(
        SalesSite.organization_id == user.tenant_id, SalesSite.deleted_at.is_(None))
        .order_by(SalesSite.created_at.desc()))).scalars().all()
    return [{"id": str(s.id), "site_code": s.site_code, "site_name": s.site_name,
             "development_type": s.development_type, "status": s.status} for s in rows]


@views_router.get("/org/tree")
async def org_tree(db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    rows = (await db.execute(select(SalesOrgNode).where(
        SalesOrgNode.site_id == ctx.site_id, SalesOrgNode.deleted_at.is_(None)))).scalars().all()
    return [{"id": str(n.id), "path": str(n.path), "node_type": n.node_type,
             "display_name": n.display_name} for n in rows]


@views_router.get("/pricing/table")
async def pricing_table(round_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                        ctx: SalesCtx = Depends(sales_ctx)):
    q = (select(SalesUnitInventory, SalesUnitPriceTable)
         .join(SalesUnitPriceTable, SalesUnitPriceTable.unit_id == SalesUnitInventory.id)
         .where(SalesUnitInventory.site_id == ctx.site_id, SalesUnitPriceTable.round_id == round_id,
                SalesUnitInventory.deleted_at.is_(None)))
    out = []
    for u, pt in (await db.execute(q)).all():
        out.append({"unit_id": str(u.id), "dong": u.dong, "ho": u.ho,
                    "total_price": int(pt.total_price or 0), "price_mode": pt.price_mode,
                    "override_price": int(pt.override_price) if pt.override_price is not None else None})
    return out


@views_router.get("/units/{unit_id}/detail")
async def unit_detail(unit_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                      ctx: SalesCtx = Depends(sales_ctx)):
    u = (await db.execute(select(SalesUnitInventory).where(SalesUnitInventory.id == unit_id))).scalar_one_or_none()
    if not u:
        return {"unit": None}
    pt = (await db.execute(select(SalesUnitPriceTable).where(
        SalesUnitPriceTable.unit_id == unit_id).order_by(SalesUnitPriceTable.updated_at.desc())
        .limit(1))).scalar_one_or_none()
    breakdown = []
    if pt:
        breakdown = [{"label": b.label, "amount": int(b.amount or 0), "vat_amount": int(b.vat_amount or 0)}
                     for b in (await db.execute(select(SalesUnitPriceBreakdown).where(
                         SalesUnitPriceBreakdown.unit_id == unit_id,
                         SalesUnitPriceBreakdown.round_id == pt.round_id))).scalars()]
    contract = (await db.execute(select(SalesContractExt).where(
        SalesContractExt.unit_id == unit_id, SalesContractExt.status == "ACTIVE"))).scalar_one_or_none()
    installments = []
    if contract:
        installments = [{"seq": it.seq, "kind": it.kind, "amount": int(it.amount or 0),
                         "due_date": it.due_date.isoformat() if it.due_date else None,
                         "paid_amount": int(it.paid_amount or 0)}
                        for it in (await db.execute(select(SalesContractInstallment).where(
                            SalesContractInstallment.contract_ext_id == contract.id)
                            .order_by(SalesContractInstallment.seq))).scalars()]
    history = [{"ts": h.ts.isoformat(), "from_status": h.from_status, "to_status": h.to_status}
               for h in (await db.execute(select(SalesUnitStatusLog).where(
                   SalesUnitStatusLog.unit_id == unit_id)
                   .order_by(SalesUnitStatusLog.ts.desc()).limit(20))).scalars()]
    return {
        "unit": {"id": str(u.id), "dong": u.dong, "ho": u.ho, "floor": u.floor,
                 "line": u.line, "aspect": u.aspect, "status": u.status},
        "price": ({"total_price": int(pt.total_price or 0), "breakdown": breakdown} if pt else None),
        "contract": ({"stage": contract.stage, "total_price": int(contract.total_price or 0)} if contract else None),
        "installments": installments,
        "history": history,
    }


@views_router.get("/projection/summary")
async def projection_summary(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """시행사 투영 — 현장별 누적 집계(개인정보 없음). sales_site_summary 증분행 합산."""
    site_rows = (await db.execute(select(SalesSite).where(
        SalesSite.organization_id == user.tenant_id, SalesSite.deleted_at.is_(None)))).scalars().all()
    out = []
    for s in site_rows:
        agg = (await db.execute(select(
            func.coalesce(func.sum(SalesSiteSummary.visitors), 0),
            func.coalesce(func.sum(SalesSiteSummary.contracts_cnt), 0),
            func.coalesce(func.sum(SalesSiteSummary.contract_amt), 0),
            func.coalesce(func.sum(SalesSiteSummary.commission_paid), 0),
        ).where(SalesSiteSummary.site_id == s.id))).first()
        total_units = (await db.execute(select(func.count()).select_from(SalesUnitInventory).where(
            SalesUnitInventory.site_id == s.id, SalesUnitInventory.deleted_at.is_(None)))).scalar() or 0
        contracts = int(agg[1] or 0)
        out.append({
            "site_id": str(s.id), "site_name": s.site_name, "status": s.status,
            "visitors": int(agg[0] or 0), "contracts_cnt": contracts,
            "contract_amt": int(agg[2] or 0),
            "sold_ratio": round(contracts / total_units, 4) if total_units else 0,
            "commission_paid": int(agg[3] or 0), "commission_due": 0,
        })
    return out
