"""sales 도메인 전용 액션 — 조직/동호생성/분양가/계약/홀드/수수료검증."""

import uuid
from datetime import datetime, timezone

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
async def hold_unit(unit_id: uuid.UUID, body: dict | None = None, db: AsyncSession = Depends(get_db),
                    ctx: SalesCtx = Depends(sales_ctx)):
    """동호 임시선점 — Phase1-C 원자 선점(DB-SSOT)으로 위임(동시성 0충돌 보장).

    이전 구현은 무조건 INSERT라 race를 막지 못했다. 이제 atomic_hold 의 단일행 조건부
    UPDATE 로 정확히 1명만 선점, 부가로 SalesUnitHold 감사행을 남긴다.
    """
    from fastapi import HTTPException

    from app.services.sales.units.concurrency import (
        HOLD_TTL_MINUTES, atomic_hold, current_status, ensure_unit_concurrency_columns,
    )
    from app.api.endpoints.sales.units_live import _broadcast

    await ensure_unit_concurrency_columns(db)
    body = body or {}
    ttl = int(body.get("minutes") or HOLD_TTL_MINUTES)
    me = ctx.user.id
    row = await atomic_hold(db, ctx.site_id, unit_id, me, ttl_minutes=ttl)
    if row is None:
        cur = await current_status(db, ctx.site_id, unit_id)
        await db.rollback()
        if cur is None:
            raise HTTPException(404, "세대를 찾을 수 없습니다")
        held_by_me = str(cur["held_by"]) == str(me) if cur["held_by"] else False
        raise HTTPException(409, detail={"message": "이미 다른 직원이 선점했거나 계약된 세대입니다",
                                         "current_status": cur["status"], "held_by_me": held_by_me})
    db.add(SalesUnitHold(site_id=ctx.site_id, unit_id=unit_id, staff_id=body.get("staff_id"),
           customer_id=body.get("customer_id"), expires_at=row["hold_expires_at"]))
    await db.commit()
    await _broadcast(ctx.site_id, "HOLD", unit_id, "HOLD", held_by=me, expires_at=row["hold_expires_at"])
    return {"ok": True, "hold_token": row["hold_token"],
            "expires_at": row["hold_expires_at"].isoformat() if row["hold_expires_at"] else None}


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
    """현장 ERP 프로비저닝(신규 site 생성).

    구독자 포함 인증 사용자 누구나 본인 테넌트에 현장을 만들 수 있고, 생성 시
    관리자 책정 '분양현장 생성 사용료'(billing service_fees.sales_provision)가 부과된다.
    생성한 현장은 본인 테넌트 소유 → sales_ctx가 DEVELOPER로 인정(운영까지 일관 동작)."""
    from fastapi import HTTPException

    from app.services.billing import billing_service
    from app.services.sales.provision import provision_site

    # 프로젝트 번호 검증 — 로컬(비-UUID) id면 500 대신 명확한 안내
    pid_raw = str(body.get("project_id") or "").strip()
    try:
        pid = uuid.UUID(pid_raw)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(400, "유효한 프로젝트 번호가 아닙니다. 프로젝트 관리에서 저장(동기화)된 프로젝트를 선택하세요.")
    if not str(body.get("site_name") or "").strip():
        raise HTTPException(400, "현장 이름을 입력하세요.")
    if not getattr(user, "tenant_id", None):
        raise HTTPException(403, "테넌트 정보가 없어 현장을 만들 수 없습니다. 다시 로그인해 주세요.")

    res = await provision_site(db, pid, user.tenant_id,
                               body["site_name"], body.get("development_type", "APT"))
    await db.commit()

    # 분양현장 생성 사용료(관리자 책정) 부과 — best-effort(실패해도 현장 생성 유지, 후불 누적)
    fee_krw = None
    try:
        await billing_service.load_config(db)
        charged = await billing_service.charge_service(db, user.id, "sales_provision")
        fee_krw = charged.get("charged_krw")
    except Exception:  # noqa: BLE001
        pass
    if isinstance(res, dict):
        res = {**res, "service_fee_krw": fee_krw}
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
