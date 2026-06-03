"""sales 도메인 전용 액션 — 조직/동호생성/분양가/계약/홀드/수수료검증."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.deps_sales import SalesCtx, require_role, sales_ctx
from apps.api.database.models.sales.units_pricing import SalesUnitGeneration, SalesUnitHold, SalesUnitPriceTable
from app.services.sales.contract.service import cancel_contract, sign_contract
from app.services.sales.org.service import create_node, move_subtree
from app.services.sales.pricing.engine import generate_price_table
from app.services.sales.units.generation import generate_units

actions_router = APIRouter(tags=["sales-actions"])


@actions_router.post("/org/nodes")
async def add_node(body: dict, db: AsyncSession = Depends(get_db),
                   ctx: SalesCtx = Depends(require_role("AGENCY", "SUBAGENCY", "DIRECTOR", "GM_DIRECTOR", "DEVELOPER"))):
    node = await create_node(db, ctx.site_id, body["node_type"], body.get("parent_id"),
                             user_id=body.get("user_id"), company_id=body.get("company_id"),
                             display_name=body.get("display_name"))
    await db.commit()
    return {"id": str(node.id), "path": str(node.path)}


@actions_router.patch("/org/nodes/{node_id}/move")
async def move_node(node_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                    ctx: SalesCtx = Depends(require_role("AGENCY", "DEVELOPER"))):
    await move_subtree(db, node_id, body["new_parent_id"], by=ctx.user.id)
    await db.commit()
    return {"ok": True}


@actions_router.post("/units/generate")
async def units_generate(body: dict, db: AsyncSession = Depends(get_db),
                         ctx: SalesCtx = Depends(require_role("AGENCY", "DEVELOPER"))):
    gen = SalesUnitGeneration(site_id=ctx.site_id, source_type=body["source_type"],
                              params=body.get("params"), source_ref=body.get("source_ref"), by=ctx.user.id)
    db.add(gen)
    await db.flush()
    n = await generate_units(db, ctx.site_id, gen)
    await db.commit()
    return {"generated": n}


@actions_router.post("/pricing/generate")
async def pricing_generate(body: dict, db: AsyncSession = Depends(get_db),
                           ctx: SalesCtx = Depends(require_role("DEVELOPER", "AGENCY"))):
    n = await generate_price_table(db, ctx.site_id, uuid.UUID(body["round_id"]), by=ctx.user.id)
    await db.commit()
    return {"priced": n}


@actions_router.patch("/units/{unit_id}/price")
async def set_unit_price_mode(unit_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                              ctx: SalesCtx = Depends(require_role("DEVELOPER", "AGENCY"))):
    rid = uuid.UUID(body["round_id"])
    pt = (await db.execute(select(SalesUnitPriceTable).where(
        SalesUnitPriceTable.unit_id == unit_id, SalesUnitPriceTable.round_id == rid))).scalar_one_or_none()
    if not pt:
        pt = SalesUnitPriceTable(site_id=ctx.site_id, unit_id=unit_id, round_id=rid)
        db.add(pt)
    pt.price_mode = body["mode"]
    if body["mode"] == "FIXED":
        pt.override_price = body["override_price"]
        pt.override_reason = body.get("reason")
        pt.override_by = ctx.user.id
        pt.override_at = datetime.now(timezone.utc)
        pt.total_price = body["override_price"]
    await db.commit()
    return {"ok": True}


@actions_router.post("/units/{unit_id}/hold")
async def hold_unit(unit_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                    ctx: SalesCtx = Depends(sales_ctx)):
    db.add(SalesUnitHold(site_id=ctx.site_id, unit_id=unit_id, staff_id=body.get("staff_id"),
           customer_id=body.get("customer_id"),
           expires_at=datetime.now(timezone.utc) + timedelta(minutes=int(body.get("minutes", 30)))))
    await db.commit()
    return {"ok": True}


@actions_router.post("/contracts/{contract_id}/sign")
async def contract_sign(contract_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                        ctx: SalesCtx = Depends(sales_ctx)):
    c = await sign_contract(db, ctx.site_id, contract_id, by=ctx.user.id)
    await db.commit()
    return {"id": str(c.id), "stage": c.stage}


@actions_router.post("/contracts/{contract_id}/cancel")
async def contract_cancel(contract_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                          ctx: SalesCtx = Depends(require_role("DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER"))):
    c = await cancel_contract(db, ctx.site_id, contract_id, body.get("reason", ""), by=ctx.user.id)
    await db.commit()
    return {"id": str(c.id), "status": c.status}


@actions_router.post("/provision")
async def provision(body: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """현장 ERP 프로비저닝(신규 site 생성). 신규 현장이라 sales_ctx 미사용 — 인증+역할로 게이트."""
    from fastapi import HTTPException

    from app.services.sales.provision import provision_site

    role = (getattr(user, "role", "") or "").lower()
    if role not in {"admin", "superadmin", "owner", "총괄관리자", "developer", "시행사", "dev"}:
        raise HTTPException(403, "프로비저닝 권한 없음")
    res = await provision_site(db, uuid.UUID(body["project_id"]), user.tenant_id,
                               body["site_name"], body.get("development_type", "APT"))
    await db.commit()
    return res


@actions_router.post("/commission/distribution/validate")
async def validate_distribution(body: dict, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    from app.services.sales.commission.engine import _active_master, _amount, _rules, resolve_total
    m = await _active_master(db, ctx.site_id)
    if not m:
        return {"total": 0, "allocated": 0, "valid": True, "note": "수수료 총액(master) 미설정"}
    total = await resolve_total(db, ctx.site_id, type("C", (), {"total_price": body.get("sample_price", 0)}))
    by_node, by_type = await _rules(db, ctx.site_id, m.id)
    s = sum(_amount(r, total) for r in list(by_node.values()) + list(by_type.values()))
    return {"total": int(total), "allocated": int(s), "valid": s <= total}
