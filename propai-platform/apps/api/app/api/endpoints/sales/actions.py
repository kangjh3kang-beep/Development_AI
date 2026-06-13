"""sales 도메인 전용 액션 — 조직/동호생성/분양가/계약/홀드/수수료검증."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.deps_sales import SalesCtx, require_role, sales_ctx
from apps.api.database.models.sales.units_pricing import SalesUnitGeneration, SalesUnitPriceTable
from app.services.sales.contract.service import cancel_contract, create_contract, sign_contract
from app.services.sales.org.service import create_node, move_subtree
from app.services.sales.pricing.engine import generate_price_table
from app.services.sales.pricing.suggest import suggest_base_price
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


@actions_router.get("/contracts")
async def list_contracts(db: AsyncSession = Depends(get_db),
                         ctx: SalesCtx = Depends(sales_ctx)):
    """현장 계약 목록(선택기용). 세대(동·호)·고객명·금액 라벨로 반환 — 원시 UUID 수기입력 대체."""
    rows = (await db.execute(text(
        "SELECT c.id::text AS id, c.total_price, c.status, u.dong, u.ho, cu.name AS customer_name "
        "FROM sales_contracts_ext c "
        "LEFT JOIN sales_unit_inventory u ON c.unit_id = u.id "
        "LEFT JOIN sales_customers cu ON c.customer_id = cu.id "
        "WHERE c.site_id = :sid ORDER BY c.created_at DESC LIMIT 500"
    ), {"sid": str(ctx.site_id)})).mappings().all()
    out = []
    for r in rows:
        unit_label = f"{r['dong']}동 {r['ho']}호" if (r["dong"] or r["ho"]) else "세대미지정"
        price = f" · {float(r['total_price']) / 1e8:.2f}억" if r["total_price"] else ""
        nm = f" · {r['customer_name']}" if r["customer_name"] else ""
        out.append({"id": r["id"], "label": f"{unit_label}{nm}{price}", "status": r["status"]})
    return out


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


@actions_router.get("/pricing/suggest")
async def pricing_suggest(bcode: str | None = None, db: AsyncSession = Depends(get_db),
                          ctx: SalesCtx = Depends(require_role("DEVELOPER", "AGENCY"))):
    """P1-1 기준층 적정분양가 3안(공/기/보) — 주변시세(거래사례비교) 기반. bcode 선택(미전달 시 PNU 유도)."""
    return await suggest_base_price(db, ctx.site_id, bcode=bcode)


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


# ※ POST /units/{id}/hold 는 units_live.py 의 hold_unit_live 가 정식 핸들러다.
#   (예전엔 여기에도 같은 경로가 있어 둘 중 하나가 죽는 '중복 라우트' 결함이 있었음 → 일원화).
#   임시선점/해제/확정(hold/release/reserve)은 모두 units_live 라우터에서 일관 처리한다.


@actions_router.post("/contracts")
async def contract_create(body: dict, db: AsyncSession = Depends(get_db),
                          ctx: SalesCtx = Depends(require_role("MEMBER", "TEAM_LEADER", "DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER"))):
    """계약 체결(최초 생성) — 세대+고객으로 계약 1건 생성(전주기 연결의 시작점).

    body: { unit_id(필수), customer_id?, round_id?, total_price? }
    금액 미지정 시 세대 가격표에서 자동 산출. 생성 후 수납/대출/전매 화면에서 즉시 선택 가능.
    """
    from fastapi import HTTPException
    try:
        unit_id = uuid.UUID(str(body["unit_id"]))
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "세대(unit_id)를 선택하세요.")
    cust = body.get("customer_id")
    rnd = body.get("round_id")
    mnode = body.get("member_node_id")  # 담당 영업사원 노드(있으면 계약 체결 시 수수료가 배분됨)
    try:
        c = await create_contract(
            db, ctx.site_id, unit_id,
            customer_id=uuid.UUID(str(cust)) if cust else None,
            round_id=uuid.UUID(str(rnd)) if rnd else None,
            member_node_id=uuid.UUID(str(mnode)) if mnode else None,
            total_price=body.get("total_price"), by=ctx.user.id)
    except ValueError as e:
        await db.rollback()
        raise HTTPException(409, str(e))
    await db.commit()
    return {"id": str(c.id), "stage": c.stage, "total_price": int(c.total_price or 0)}


@actions_router.post("/contracts/{contract_id}/sign")
async def contract_sign(contract_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                        ctx: SalesCtx = Depends(sales_ctx)):
    from fastapi import HTTPException
    try:
        c = await sign_contract(db, ctx.site_id, contract_id, by=ctx.user.id)
    except ValueError as e:
        await db.rollback()
        raise HTTPException(409, str(e))  # 중복 서명·잘못된 상태는 409로 명확히
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
