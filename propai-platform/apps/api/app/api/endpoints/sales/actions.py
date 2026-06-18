"""sales 도메인 전용 액션 — 조직/동호생성/분양가/계약/홀드/수수료검증."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.deps_sales import SalesCtx, require_role, sales_ctx
from app.services.sales.contract.service import cancel_contract, create_contract, sign_contract
from app.services.sales.org.service import create_node, move_subtree, seed_default_org
from app.services.sales.pricing.engine import (
    apply_group_pricing,
    generate_price_table,
    project_revenue,
    solve_base_for_target,
)
from app.services.sales.pricing.suggest import suggest_base_price
from app.services.sales.units.generation import generate_units
from apps.api.database.models.sales.units_pricing import SalesUnitGeneration, SalesUnitPriceTable

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

# 자주 쓰는 역할 집합(시그니처 길이·중복 축소). require_role(*상수) 로 전개.
_R_ORG_ADD = ("AGENCY", "SUBAGENCY", "DIRECTOR", "GM_DIRECTOR", "TEAM_LEADER", "DEVELOPER")
_R_TEAM = ("TEAM_LEADER", "DIRECTOR", "GM_DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER", "SUPERADMIN")
_R_SALES_ALL = ("MEMBER", "TEAM_LEADER", "GM_DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER", "SUPERADMIN")
_R_CONTRACT = ("MEMBER", "TEAM_LEADER", "DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER")
# ★세금유형 변경/조회는 머니패스(원천/부가세 분개) write·열람이라 최하위 영업사원(MEMBER)을
#   제거하고 최소 TEAM_LEADER 이상으로 제한한다(조회도 동일 게이트 — 타인 세금유형 무단 열람 차단).
# ★[권한사다리 역전 해소(iter-5)] DIRECTOR 는 _R_ORG_ADD/_R_TEAM/_R_CONTRACT 에 모두 포함된
#   상위 관리직인데 _R_TAXPREF 에서만 누락돼, 하급 TEAM_LEADER 는 통과하고 상급 DIRECTOR 는 403
#   인 사다리 역전이 있었다. DIRECTOR 를 추가해 '상위 직급은 하위가 가능한 머니패스 열람/설정을
#   항상 할 수 있다'는 권한 단조성을 복원한다(역전 제거).
_R_TAXPREF = ("DEVELOPER", "AGENCY", "SUBAGENCY", "GM_DIRECTOR", "DIRECTOR", "TEAM_LEADER")


@actions_router.post("/org/nodes")
async def add_node(body: dict, db: AsyncSession = Depends(get_db),
                   ctx: SalesCtx = Depends(require_role(*_R_ORG_ADD))):
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
                            ctx: SalesCtx = Depends(require_role(*_R_TEAM))):
    """P2-3 내 하위 조직 인원의 계약·고객·업무일지 집계+로스터(직급별 관리)."""
    from app.services.sales.org.overview import team_overview
    return await team_overview(db, ctx.site_id, getattr(ctx, "org_path", None) or None)


@actions_router.post("/org/nodes/{node_id}/assign")
async def org_assign_user(node_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                          ctx: SalesCtx = Depends(require_role(*_R_ORG_ADD))):
    """P2-3 노드 인원배정 — 같은 조직 사용자를 이메일로 노드에 배정(미배정 해소). body.email"""
    from fastapi import HTTPException

    from app.services.sales.org.service import assign_user_to_node
    try:
        res = await assign_user_to_node(db, ctx.site_id, node_id, body.get("email", ""))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await db.commit()
    return res


@actions_router.post("/org/nodes/{node_id}/unassign")
async def org_unassign_user(node_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                            ctx: SalesCtx = Depends(require_role(*_R_ORG_ADD))):
    """P2-3 노드 인원배정 해제 — 노드를 미배정으로 되돌림(노드·실적 유지)."""
    from fastapi import HTTPException

    from app.services.sales.org.service import unassign_user
    try:
        res = await unassign_user(db, ctx.site_id, node_id, by=getattr(ctx.user, "id", None))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await db.commit()
    return res


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
        raise HTTPException(400, str(e)) from e


@actions_router.get("/accounting/summary")
async def accounting_summary(db: AsyncSession = Depends(get_db),
                             ctx: SalesCtx = Depends(require_role(
                                 "GM_DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER", "SUPERADMIN"))):
    """현장 회계 비용 집계(항목별)+매출·수수료·손익 — site-detail 와 동일 원장 기준."""
    from app.services.sales.admin.console import site_management_detail
    d = await site_management_detail(db, ctx.site_id)
    # 손익 2-뷰(현금흐름·발생주의)+선수금·미수금 함께 반환. profit_estimate(=발생주의)는 하위호환 유지.
    return {"accounting": d["accounting"], "revenue": d["revenue"],
            "commission": d["commission"], "profit_estimate": d["profit_estimate"],
            "cash_flow": d.get("cash_flow"), "accrual": d.get("accrual"),
            "deferred_revenue": d.get("deferred_revenue"), "note": d["note"]}


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
        raise HTTPException(400, f"입력 오류: {e}") from e


@actions_router.get("/payroll")
async def payroll_compute(ym: str, db: AsyncSession = Depends(get_db),
                          ctx: SalesCtx = Depends(require_role(
                              "TEAM_LEADER", "GM_DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER", "SUPERADMIN"))):
    """직원별 급여 자동산정(근태×단가). ym=YYYY-MM."""
    from fastapi import HTTPException

    from app.services.sales.admin.console import _validate_ym, compute_payroll
    # ym 형식 검증(YYYY-MM·월01~12). 가드가 없으면 compute_payroll→_month_bounds→_validate_ym
    # 에서 비정규 ym(2026-13·2026/06·2026-6·공백)이 ValueError→HTTP500 으로 누출된다.
    # POST(/payroll/post·/accounting/entry)와 동일하게 진입 전 400 으로 차단(은폐 금지=명시 오류).
    try:
        _validate_ym(ym)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return await compute_payroll(db, ctx.site_id, ym)


@actions_router.post("/payroll/post")
async def payroll_post(body: dict, db: AsyncSession = Depends(get_db),
                       ctx: SalesCtx = Depends(require_role(
                           "GM_DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER", "SUPERADMIN"))):
    """산정 급여 총액을 회계 인건비(LABOR)로 자동전기(월 중복 방지). body.ym=YYYY-MM."""
    from fastapi import HTTPException

    from app.services.sales.admin.console import _validate_ym, post_payroll_to_accounting
    ym = body.get("ym")
    if not ym:
        raise HTTPException(400, "ym(YYYY-MM) 필요")
    # ym 형식 검증(YYYY-MM·월01~12). 비정규 ym(2026-13·2026/06·2026-6)은 멱등 귀속키를
    # 우회하므로 서비스 진입 전 400 으로 차단(은폐 금지=명시적 오류 반환).
    try:
        _validate_ym(ym)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
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
                          ctx: SalesCtx = Depends(require_role(*_R_CONTRACT))):
    """계약 체결(최초 생성) — 세대+고객으로 계약 1건 생성(전주기 연결의 시작점).

    body: { unit_id(필수), customer_id?, round_id?, total_price? }
    금액 미지정 시 세대 가격표에서 자동 산출. 생성 후 수납/대출/전매 화면에서 즉시 선택 가능.
    """
    from fastapi import HTTPException
    try:
        unit_id = uuid.UUID(str(body["unit_id"]))
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "세대(unit_id)를 선택하세요.") from None
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
        raise HTTPException(409, str(e)) from e
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
        raise HTTPException(409, str(e)) from e # 중복 서명·잘못된 상태는 409로 명확히
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
        raise HTTPException(400, "유효한 프로젝트 번호가 아닙니다. 저장(동기화)된 프로젝트를 선택하세요.") from None
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
async def get_tax_pref(node_id: str, db: AsyncSession = Depends(get_db),
                       ctx: SalesCtx = Depends(require_role(*_R_TAXPREF))):
    """수령자(노드) 수수료 세금유형 조회 — WITHHOLDING(3.3% 원천) | VAT(부가세 10%).

    ★머니패스 열람 게이트: 과거엔 sales_ctx(현장 멤버십)만 의존해 역할 게이트가 전무했다
      (최하위 MEMBER 도 타인 세금유형 열람 가능). 설정(POST)과 동일하게 _R_TAXPREF(TEAM_LEADER+)
      게이트를 걸어 조회/설정 권한을 대칭으로 맞춘다(타인 분개정보 무단 열람 차단)."""
    from fastapi import HTTPException

    from app.services.sales.commission.engine import get_node_tax_type
    # ★[UUID 가드 대칭(iter-6)] set_tax_pref 와 동일하게 node_id 파싱 실패를 전용 400 으로 돌린다.
    #   과거엔 uuid.UUID(node_id) 무가드 호출이 잘못된 쿼리파라미터(비-UUID)에서 ValueError 를 던져
    #   전역 핸들러 500 으로 빠졌다(클라이언트 입력오류를 서버오류로 오표시). KeyError 는 FastAPI 가
    #   필수 쿼리파라미터로 이미 422 처리하므로 여기선 형식오류(ValueError·TypeError)만 400 으로 잡는다.
    try:
        nid = uuid.UUID(node_id)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, "node_id 형식이 올바르지 않습니다(UUID 필요)") from e
    # 현장 격리: ctx.site_id 로 본 현장 행만 조회(타 현장 노드 세금유형 열람 차단).
    return {"node_id": node_id,
            "tax_type": await get_node_tax_type(db, nid, site_id=ctx.site_id)}


@actions_router.get("/commission/settle-summary")
async def commission_settle_summary(node_id: str, db: AsyncSession = Depends(get_db),
                                    ctx: SalesCtx = Depends(require_role(*_R_TEAM))):
    """#5 해촉/정산 — 노드(영업사원) 수수료 정산 명세(기발생−기지급=미지급, 원천/부가세 분개)."""
    from fastapi import HTTPException

    from app.services.sales.commission.engine import settle_summary
    # ★[UUID 가드 대칭(iter-6)] get_tax_pref/set_tax_pref 와 동일하게 node_id 형식오류를 전용 400 으로.
    #   무가드 uuid.UUID(node_id)는 비-UUID 쿼리파라미터에서 전역핸들러 500(클라이언트 입력오류 오표시).
    try:
        nid = uuid.UUID(node_id)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, "node_id 형식이 올바르지 않습니다(UUID 필요)") from e
    return await settle_summary(db, ctx.site_id, nid)


@actions_router.post("/commission/tax-pref")
async def set_tax_pref(body: dict, db: AsyncSession = Depends(get_db),
                       ctx: SalesCtx = Depends(require_role(*_R_TAXPREF))):
    """수령자 세금유형 설정 — 3.3% 원천징수(WITHHOLDING) 또는 부가세 10%(VAT) 중 선택."""
    from fastapi import HTTPException

    from app.services.sales.commission.engine import CrossSiteOwnershipError, set_node_tax_type
    # ★[오안내 해소(iter-5)] node_id 의 UUID 파싱을 try 진입 전에 분리한다. 과거엔 try 안에서
    #   uuid.UUID(body["node_id"]) 가 던지는 ValueError 가 아래 'except ValueError → tax_type 이
    #   올바르지 않습니다' 핸들러로 빨려 들어가, 실제로는 node_id 형식이 잘못된 건데 'tax_type 오류'
    #   로 잘못 안내됐다. 파싱을 분리하고 전용 메시지로 400 을 돌려준다(KeyError=누락, ValueError·
    #   TypeError=형식오류 — 둘 다 node_id 전용 안내).
    try:
        node_id = uuid.UUID(str(body["node_id"]))
    except KeyError as e:
        raise HTTPException(400, "node_id(노드 식별자) 필요") from e
    except (ValueError, TypeError) as e:
        raise HTTPException(400, "node_id 형식이 올바르지 않습니다(UUID 필요)") from e
    try:
        tt = await set_node_tax_type(db, ctx.site_id, node_id, body.get("tax_type", ""))
    except CrossSiteOwnershipError as e:
        # ★예외 분기(응답계약 SSOT): 교차현장 소유 충돌은 전용 예외클래스로 식별해 409(Conflict)
        #   로 매핑한다. (과거엔 한국어 메시지 '다른 현장' 부분문자열 매칭이라 문구 변경 시
        #   상태코드가 흔들렸다 — 전용 예외 isinstance 분기로 문구와 무관하게 409 불변.)
        #   CrossSiteOwnershipError 가 ValueError 하위라 반드시 아래 ValueError 핸들러보다 앞에 둔다.
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        # 그 외 입력검증 실패(잘못된 tax_type 등)는 400 Bad Request 로 매핑한다.
        raise HTTPException(400, str(e) or "tax_type(WITHHOLDING/VAT)이 올바르지 않습니다") from e
    # (node_id 의 KeyError/형식오류는 위 별도 try 에서 이미 전용 400 으로 처리됐으므로
    #  여기서는 set_node_tax_type 가 던질 일이 없는 KeyError 핸들러를 두지 않는다 — dead 분기 제거.)
    await db.commit()
    return {"ok": True, "node_id": str(node_id), "tax_type": tt}


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


# ── 세대 상태전이 액션 + 이벤트 원장(동호지정·계약 컨텍스트 메뉴) ───────────────
@actions_router.post("/units/{unit_id}/action")
async def unit_lifecycle_action(unit_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                                ctx: SalesCtx = Depends(require_role(*_R_SALES_ALL))):
    """세대 클릭 메뉴 액션 — HOLD_REQUEST(지정대기)/HOLD_CANCEL/CONTRACT_WAIT(계약대기)/
    CONTRACT_CANCEL/CONTRACT_SIGN(계약체결)/CONTRACT_TERMINATE/NOTE(특이사항). 상태전이+해시체인 원장."""
    from fastapi import HTTPException

    from app.services.sales.units.lifecycle_actions import unit_action
    try:
        return await unit_action(db, ctx.site_id, unit_id, body.get("action", ""),
                                  message=body.get("message"), by=getattr(ctx.user, "id", None))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@actions_router.get("/units/{unit_id}/events")
async def unit_events(unit_id: uuid.UUID, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    """세대 이벤트 타임라인(년월일·시분 + 해시체인) — 특이사항·상태이력."""
    from app.services.sales.units.event_ledger import unit_timeline
    return await unit_timeline(db, unit_id)


@actions_router.get("/units/{unit_id}/verify-chain")
async def unit_verify_chain(unit_id: uuid.UUID, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    """세대 이벤트 해시체인 무결성 검증(변조탐지) — 감사/공정성."""
    from app.services.sales.units.event_ledger import verify_chain
    return await verify_chain(db, unit_id)


# ── 동·호 추첨(즉석추첨 + seed 해시체인 감사) ────────────────────────────────
_DRAW_MGR = ("TEAM_LEADER", "GM_DIRECTOR", "SUBAGENCY", "AGENCY", "DEVELOPER", "SUPERADMIN")


@actions_router.get("/draw/groups")
async def draw_groups_list(db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    """현장 추첨그룹 목록."""
    from app.services.sales.draw.draw_engine import list_groups
    return await list_groups(db, ctx.site_id)


@actions_router.post("/draw/groups")
async def draw_group_create(body: dict, db: AsyncSession = Depends(get_db),
                            ctx: SalesCtx = Depends(require_role(*_DRAW_MGR))):
    from fastapi import HTTPException

    from app.services.sales.draw.draw_engine import create_group
    try:
        return await create_group(db, ctx.site_id, body.get("name", ""))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@actions_router.post("/draw/groups/{group_id}/pool")
async def draw_group_pool(group_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                          ctx: SalesCtx = Depends(require_role(*_DRAW_MGR))):
    """그룹 동·호판(추첨 대상 세대) 지정. body.unit_ids[]"""
    from app.services.sales.draw.draw_engine import set_pool
    return await set_pool(db, ctx.site_id, group_id, body.get("unit_ids") or [])


@actions_router.post("/draw/groups/{group_id}/candidates")
async def draw_add_candidates(group_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                              ctx: SalesCtx = Depends(require_role(*_DRAW_MGR))):
    """대상자 일괄 등록. body.rows=[{name, phone?, customer_id?}]"""
    from app.services.sales.draw.draw_engine import add_candidates
    return await add_candidates(db, ctx.site_id, group_id, body.get("rows") or [])


@actions_router.post("/draw/groups/{group_id}/candidates/from-customers")
async def draw_from_customers(group_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                              ctx: SalesCtx = Depends(require_role(*_DRAW_MGR))):
    """계약자/고객 명부에서 대상자 선별 등록. body.customer_ids[](미지정=현장 전체)"""
    from app.services.sales.draw.draw_engine import from_customers
    return await from_customers(db, ctx.site_id, group_id, body.get("customer_ids"))


@actions_router.post("/draw/groups/{group_id}/candidates/from-winners")
async def draw_from_winners(group_id: uuid.UUID, body: dict, db: AsyncSession = Depends(get_db),
                            ctx: SalesCtx = Depends(require_role(*_DRAW_MGR))):
    """청약 당첨자 명부 → 동·호 추첨 대상자 시드(청약→당첨→동·호배정 흐름 연결). body.announcement_id 필수."""
    from fastapi import HTTPException

    from app.services.sales.draw.draw_engine import from_winners
    ann = body.get("announcement_id")
    if not ann:
        raise HTTPException(400, "announcement_id(청약 공고) 필요")
    try:
        return await from_winners(db, ctx.site_id, group_id, ann)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@actions_router.post("/draw/groups/{group_id}/candidates/excel")
async def draw_import_excel(group_id: uuid.UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                            ctx: SalesCtx = Depends(require_role(*_DRAW_MGR))):
    """고객명부 Excel(.xlsx) 업로드 → 대상자 등록(이름·연락처 자동인식)."""
    from fastapi import HTTPException

    from app.services.sales.draw.draw_engine import add_candidates, parse_excel
    try:
        content = await file.read()
        rows = parse_excel(content)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"엑셀 파싱 실패: {str(e)[:120]}") from e
    if not rows:
        raise HTTPException(400, "엑셀에서 대상자를 찾지 못했습니다(1행 헤더: 이름/연락처).")
    return await add_candidates(db, ctx.site_id, group_id, rows)


@actions_router.post("/draw/groups/{group_id}/candidates/{candidate_id}/draw")
async def draw_run(group_id: uuid.UUID, candidate_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                   ctx: SalesCtx = Depends(require_role("MEMBER", *_DRAW_MGR))):
    """즉석추첨 — 대상자가 누르면 남은 동호 중 무작위 1개 배정·공개(seed 해시체인 감사)."""
    from fastapi import HTTPException

    from app.services.sales.draw.draw_engine import draw_for_candidate
    try:
        return await draw_for_candidate(db, ctx.site_id, group_id, candidate_id, by=getattr(ctx.user, "id", None))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@actions_router.post("/draw/groups/{group_id}/candidates/{candidate_id}/contract")
async def draw_candidate_contract(group_id: uuid.UUID, candidate_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                                  ctx: SalesCtx = Depends(require_role(*_DRAW_MGR))):
    """추첨 배정(HOLD) 당첨자 → 계약 생성(청약→당첨→동·호배정→계약 완결). 멱등(기존 계약 시 반환)."""
    from fastapi import HTTPException

    from app.services.sales.draw.draw_engine import contract_from_candidate
    try:
        return await contract_from_candidate(db, ctx.site_id, group_id, candidate_id, by=getattr(ctx.user, "id", None))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@actions_router.get("/draw/groups/{group_id}/status")
async def draw_group_status(group_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                            ctx: SalesCtx = Depends(sales_ctx)):
    """추첨그룹 현황 — 대상자 순번·배정세대·진행률·남은 세대."""
    from fastapi import HTTPException

    from app.services.sales.draw.draw_engine import group_status
    try:
        return await group_status(db, ctx.site_id, group_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
