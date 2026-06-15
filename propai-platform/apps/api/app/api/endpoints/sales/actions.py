"""sales 도메인 전용 액션 — 조직/동호생성/분양가/계약/홀드/수수료검증."""

import uuid
from datetime import datetime, timezone, UTC

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.deps_sales import SalesCtx, require_role, sales_ctx
from apps.api.database.models.sales.units_pricing import SalesUnitGeneration, SalesUnitPriceTable
from app.services.sales.contract.service import cancel_contract, create_contract, sign_contract
from app.services.sales.org.service import create_node, move_subtree, seed_default_org
from app.services.sales.pricing.engine import (
    apply_group_pricing, generate_price_table, project_revenue, solve_base_for_target,
)
from app.services.sales.pricing.suggest import suggest_base_price
from app.services.sales.units.generation import generate_units

actions_router = APIRouter(tags=["sales-actions"])

# P2 직급별 등록권한: 각 node_type 을 등록할 수 있는 '최소 상위 역할' 집합.
# 시행사→대행사, 대행사→본부장, 본부장→팀장, 팀장→직원 (상위 역할·관리자는 항상 허용).
_REGISTER_MATRIX = {
    "AGENCY": {"DEVELOPER", "SUPERADMIN"},
    "SUBAGENCY": {"AGENCY", "DEVELOPER", "SUPERADMIN"},
    "GM_DIRECTOR": {"AGENCY", "SUBAGENCY", "DEVELOPER", "SUPERADMIN"},
    "TEAM_LEADER": {"GM_DIRECTOR", "AGENCY", "SUBAGENCY", "DEVELOPER", "SUPERADMIN"},
    "MEMBER": {"TEAM_LEADER", "GM_DIRECTOR", "AGENCY", "SUBAGENCY", "DEVELOPER", "SUPERADMIN"},
}


@actions_router.post("/org/nodes")
async def add_node(body: dict, db: AsyncSession = Depends(get_db),
                   ctx: SalesCtx = Depends(require_role("AGENCY", "SUBAGENCY", "DIRECTOR", "GM_DIRECTOR", "TEAM_LEADER", "DEVELOPER"))):
    ntype = body["node_type"]
    allowed = _REGISTER_MATRIX.get(ntype)
    if allowed is not None and ctx.role not in allowed:
        from fastapi import HTTPException
        raise HTTPException(403, f"{ntype} 등록 권한이 없습니다(상위 직급만 등록 가능).")
    node = await create_node(db, ctx.site_id, ntype, body.get("parent_id"),
                             user_id=body.get("user_id"), company_id=body.get("company_id"),
                             display_name=body.get("display_name"))
    await db.commit()
    return {"id": str(node.id), "path": str(node.path)}


@actions_router.get("/org/team-overview")
async def org_team_overview(db: AsyncSession = Depends(get_db),
                            ctx: SalesCtx = Depends(require_role(
                                "TEAM_LEADER", "DIRECTOR", "GM_DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER", "SUPERADMIN"))):
    """P2-3 내 하위 조직 인원의 계약·고객·업무일지 집계+로스터(직급별 관리)."""
    from app.services.sales.org.overview import team_overview
    return await team_overview(db, ctx.site_id, getattr(ctx, "org_path", None) or None)


@actions_router.post("/org/seed-default")
async def org_seed_default(body: dict | None = None, db: AsyncSession = Depends(get_db),
                           ctx: SalesCtx = Depends(require_role("DEVELOPER", "AGENCY", "SUPERADMIN"))):
    """P2 기본조직 생성(대행사→본부장→5팀×10명). 빈 조직에서만. 이후 추가·삭제·인원배정."""
    body = body or {}
    res = await seed_default_org(db, ctx.site_id,
                                 teams=int(body.get("teams", 5)),
                                 members_per_team=int(body.get("members_per_team", 10)))
    if res.get("ok"):
        await db.commit()
    return res


# ── 분양관리요약(관리자) 현장별 통합 관리 콘솔 ────────────────────────────────
@actions_router.get("/admin/site-detail")
async def admin_site_detail(db: AsyncSession = Depends(get_db),
                            ctx: SalesCtx = Depends(require_role(
                                "GM_DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER", "SUPERADMIN"))):
    """현장 1곳 통합 관리 지표 — 담당자·근태·계약·매출·수수료·방문·광고·회계·손익."""
    from app.services.sales.admin.console import site_management_detail
    return await site_management_detail(db, ctx.site_id)


@actions_router.post("/accounting/entry")
async def accounting_entry(body: dict, db: AsyncSession = Depends(get_db),
                           ctx: SalesCtx = Depends(require_role(
                               "GM_DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER", "SUPERADMIN"))):
    """현장 회계 항목 등록(인건비/경비/공과금/광고비/기타)."""
    from fastapi import HTTPException
    from app.services.sales.admin.console import add_accounting_entry
    try:
        return await add_accounting_entry(
            db, ctx.site_id, body.get("entry_type", ""), int(body.get("amount", 0)),
            body.get("memo"), body.get("entry_date"), getattr(ctx.user, "id", None))
    except ValueError as e:
        raise HTTPException(400, str(e))


@actions_router.get("/accounting/summary")
async def accounting_summary(db: AsyncSession = Depends(get_db),
                             ctx: SalesCtx = Depends(require_role(
                                 "GM_DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER", "SUPERADMIN"))):
    """현장 회계 비용 집계(항목별)+매출·수수료·손익 — site-detail 와 동일 원장 기준."""
    from app.services.sales.admin.console import site_management_detail
    d = await site_management_detail(db, ctx.site_id)
    return {"accounting": d["accounting"], "revenue": d["revenue"],
            "commission": d["commission"], "profit_estimate": d["profit_estimate"], "note": d["note"]}


# ── 급여관리(근태×단가 자동산정) + 광고 ROI ──────────────────────────────────
@actions_router.post("/staff/wage")
async def staff_wage_set(body: dict, db: AsyncSession = Depends(get_db),
                         ctx: SalesCtx = Depends(require_role(
                             "TEAM_LEADER", "GM_DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER", "SUPERADMIN"))):
    """직원 단가 설정(일급/시급/월급) — 급여 자동산정 기준."""
    from fastapi import HTTPException
    from app.services.sales.admin.console import set_staff_wage
    try:
        return await set_staff_wage(db, ctx.site_id, body["staff_id"],
                                    body.get("wage_type", "DAILY"), int(body.get("base_wage", 0)),
                                    tax_mode=body.get("tax_mode", "FREELANCE"))
    except (ValueError, KeyError) as e:
        raise HTTPException(400, f"입력 오류: {e}")


@actions_router.get("/payroll")
async def payroll_compute(ym: str, db: AsyncSession = Depends(get_db),
                          ctx: SalesCtx = Depends(require_role(
                              "TEAM_LEADER", "GM_DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER", "SUPERADMIN"))):
    """직원별 급여 자동산정(근태×단가). ym=YYYY-MM."""
    from app.services.sales.admin.console import compute_payroll
    return await compute_payroll(db, ctx.site_id, ym)


@actions_router.post("/payroll/post")
async def payroll_post(body: dict, db: AsyncSession = Depends(get_db),
                       ctx: SalesCtx = Depends(require_role(
                           "GM_DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER", "SUPERADMIN"))):
    """산정 급여 총액을 회계 인건비(LABOR)로 자동전기(월 중복 방지). body.ym=YYYY-MM."""
    from fastapi import HTTPException
    from app.services.sales.admin.console import post_payroll_to_accounting
    ym = body.get("ym")
    if not ym:
        raise HTTPException(400, "ym(YYYY-MM) 필요")
    return await post_payroll_to_accounting(db, ctx.site_id, ym, getattr(ctx.user, "id", None))


@actions_router.get("/ad/roi")
async def ad_roi_view(db: AsyncSession = Depends(get_db),
                      ctx: SalesCtx = Depends(require_role(
                          "TEAM_LEADER", "GM_DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER", "SUPERADMIN"))):
    """광고 집행비 대비 집객·계약 효율(단가)."""
    from app.services.sales.admin.console import ad_roi
    return await ad_roi(db, ctx.site_id)


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


@actions_router.get("/pricing/revenue")
async def pricing_revenue(round_id: str, db: AsyncSession = Depends(get_db),
                          ctx: SalesCtx = Depends(require_role("DEVELOPER", "AGENCY", "GM_DIRECTOR", "DIRECTOR"))):
    """P1-3 현재 분양가표 기준 총매출(분양액) 산출 — forward."""
    return await project_revenue(db, ctx.site_id, uuid.UUID(round_id))


@actions_router.post("/pricing/solve-base")
async def pricing_solve_base(body: dict, db: AsyncSession = Depends(get_db),
                             ctx: SalesCtx = Depends(require_role("DEVELOPER", "AGENCY"))):
    """P1-3 목표 총매출 → 균일 기준단가 역산·전 타입 반영·재생성 — reverse."""
    res = await solve_base_for_target(db, ctx.site_id, uuid.UUID(body["round_id"]),
                                      int(body["target_total_10k"]), by=ctx.user.id)
    if res.get("ok"):
        await db.commit()
        # Phase 1: 분양매출 SSOT 합류(best-effort) — solve_base는 achieved_total_10k를 total로 정규화
        from app.services.ledger.ledger_adapters import record_pricing_revenue
        await record_pricing_revenue(
            rev={**res, "total_revenue_10k": res.get("achieved_total_10k")},
            round_id=str(body["round_id"]),
            tenant_id=str(getattr(ctx.user, "tenant_id", "") or "") or None,
            project_id=str(ctx.site_id), created_by=str(ctx.user.id))
    return res


@actions_router.post("/pricing/group-apply")
async def pricing_group_apply(body: dict, db: AsyncSession = Depends(get_db),
                              ctx: SalesCtx = Depends(require_role("DEVELOPER", "AGENCY"))):
    """P1-4 선택 세대 그룹 일괄단가 — mode=RATE(+%)·FIXED(+원)·OVERRIDE_PSQM(절대 평당단가)."""
    res = await apply_group_pricing(
        db, ctx.site_id, uuid.UUID(body["round_id"]),
        [uuid.UUID(str(u)) for u in (body.get("unit_ids") or [])],
        mode=body.get("mode", "RATE"), value=float(body.get("value", 0)),
        group_name=body.get("group_name"), by=ctx.user.id)
    if res.get("ok"):
        await db.commit()
        # Phase 1: 분양매출 SSOT 합류(best-effort 무중단 — append_analysis가 예외 흡수)
        from app.services.ledger.ledger_adapters import record_pricing_revenue
        await record_pricing_revenue(
            rev=res, round_id=str(body["round_id"]),
            tenant_id=str(getattr(ctx.user, "tenant_id", "") or "") or None,
            project_id=str(ctx.site_id), created_by=str(ctx.user.id))
    return res


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
        pt.override_at = datetime.now(UTC)
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


@actions_router.get("/commission/tax-pref")
async def get_tax_pref(node_id: str, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    """수령자(노드) 수수료 세금유형 조회 — WITHHOLDING(3.3% 원천) | VAT(부가세 10%)."""
    from app.services.sales.commission.engine import get_node_tax_type
    return {"node_id": node_id, "tax_type": await get_node_tax_type(db, uuid.UUID(node_id))}


@actions_router.post("/commission/tax-pref")
async def set_tax_pref(body: dict, db: AsyncSession = Depends(get_db),
                       ctx: SalesCtx = Depends(require_role("DEVELOPER", "AGENCY", "GM_DIRECTOR", "TEAM_LEADER", "MEMBER"))):
    """수령자 세금유형 설정 — 3.3% 원천징수(WITHHOLDING) 또는 부가세 10%(VAT) 중 선택."""
    from fastapi import HTTPException
    from app.services.sales.commission.engine import set_node_tax_type
    try:
        tt = await set_node_tax_type(db, ctx.site_id, uuid.UUID(body["node_id"]), body.get("tax_type", ""))
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e) or "node_id·tax_type(WITHHOLDING/VAT) 필요")
    await db.commit()
    return {"ok": True, "node_id": body["node_id"], "tax_type": tt}


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
