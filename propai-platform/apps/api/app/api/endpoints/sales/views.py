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
from apps.api.database.models.sales.commission_mh_harness import (
    SalesCommissionMaster, SalesCommissionDistribution,
)
from datetime import UTC

views_router = APIRouter(tags=["sales-views"])


@views_router.get("/integrity/check")
async def integrity_check(db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    """무결성 가드 — 1호1계약·배분초과·미보증·미가격 등 위반 실시간 적발."""
    site = ctx.site_id
    findings: list[dict] = []

    # 1) 중복 동·호(1호1계약 위반 소지)
    dup = (await db.execute(
        select(SalesUnitInventory.dong, SalesUnitInventory.ho, func.count().label("c"))
        .where(SalesUnitInventory.site_id == site, SalesUnitInventory.deleted_at.is_(None))
        .group_by(SalesUnitInventory.dong, SalesUnitInventory.ho).having(func.count() > 1))).all()
    if dup:
        findings.append({"key": "dup_unit", "severity": "critical", "count": len(dup),
                         "title": "중복 동·호",
                         "detail": ", ".join(f"{d.dong}-{d.ho}({d.c})" for d in dup[:10])})

    # 2) 한 세대 다중 활성계약
    multi = (await db.execute(
        select(SalesContractExt.unit_id, func.count().label("c"))
        .where(SalesContractExt.site_id == site, SalesContractExt.status == "ACTIVE")
        .group_by(SalesContractExt.unit_id).having(func.count() > 1))).all()
    if multi:
        findings.append({"key": "multi_contract", "severity": "critical", "count": len(multi),
                         "title": "한 세대 다중 활성계약", "detail": f"{len(multi)}개 세대"})

    # 3) 수수료 배분 초과(활성 마스터)
    master = (await db.execute(select(SalesCommissionMaster).where(
        SalesCommissionMaster.site_id == site)
        .order_by(SalesCommissionMaster.effective_at.desc()).limit(1))).scalar_one_or_none()
    if master:
        dists = list((await db.execute(select(SalesCommissionDistribution).where(
            SalesCommissionDistribution.site_id == site,
            SalesCommissionDistribution.master_id == master.id))).scalars())
        rate_sum = sum(float(d.value or 0) for d in dists if d.basis == "RATE")
        fixed_sum = sum(float(d.value or 0) for d in dists if d.basis == "FIXED")
        over = False; note = ""
        if rate_sum > 1.0:
            over = True; note = f"배분 비율 합 {rate_sum * 100:.0f}% > 100%"
        total = float(master.fixed_amount or master.pool_total or 0) if master.basis != "RATE_OF_PRICE" else 0
        if total and fixed_sum > total:
            over = True; note = (note + " · " if note else "") + f"정액 배분 {fixed_sum:,.0f} > 총액 {total:,.0f}"
        if over:
            findings.append({"key": "comm_over", "severity": "high", "count": 1,
                             "title": "수수료 배분 초과(Σ>총액)", "detail": note})

    # 4) 미보증 계약(서명 이상인데 활성 보증 없음)
    try:
        from apps.api.database.models.sales.guarantee import SalesGuaranteePolicy
        signed = (await db.execute(select(func.count()).select_from(SalesContractExt).where(
            SalesContractExt.site_id == site, SalesContractExt.status == "ACTIVE",
            SalesContractExt.stage.in_(["SIGNED", "MIDDLE", "BALANCE"])))).scalar() or 0
        has_g = (await db.execute(select(func.count()).select_from(SalesGuaranteePolicy).where(
            SalesGuaranteePolicy.site_id == site, SalesGuaranteePolicy.status == "ACTIVE"))).scalar() or 0
        if signed > 0 and has_g == 0:
            findings.append({"key": "no_guarantee", "severity": "high", "count": int(signed),
                             "title": "미보증 계약", "detail": f"서명 이상 계약 {signed}건, 활성 분양보증/신탁 0"})
    except Exception:  # noqa: BLE001
        pass

    # 5) 미가격 세대(분양가능인데 가격표 없음)
    priced = select(SalesUnitPriceTable.unit_id).where(
        SalesUnitPriceTable.site_id == site).distinct().scalar_subquery()
    unpriced = (await db.execute(select(func.count()).select_from(SalesUnitInventory).where(
        SalesUnitInventory.site_id == site, SalesUnitInventory.deleted_at.is_(None),
        SalesUnitInventory.status == "AVAILABLE", SalesUnitInventory.id.not_in(priced)))).scalar() or 0
    if unpriced > 0:
        findings.append({"key": "unpriced", "severity": "medium", "count": int(unpriced),
                         "title": "미가격 세대", "detail": f"분양가능 {unpriced}세대 분양가 미산정"})

    return {"ok": len(findings) == 0, "findings": findings}


@views_router.get("/crm/grade-suggestions")
async def crm_grade_suggestions(db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
    """AI 가망고객 예측 — 상담·통화·재방문·마케팅동의·최근성 가중 점수로 등급(A/B/C)·다음액션 제안."""
    from datetime import datetime, timezone
    from apps.api.database.models.sales.contract_crm_ad import (
        SalesCustomer, SalesCustomerCall, SalesCustomerConsent, SalesCustomerConsultation,
    )

    now = datetime.now(UTC)
    customers = list((await db.execute(select(SalesCustomer).where(
        SalesCustomer.site_id == ctx.site_id, SalesCustomer.deleted_at.is_(None)))).scalars())
    out = []
    for c in customers:
        consults = list((await db.execute(select(SalesCustomerConsultation).where(
            SalesCustomerConsultation.customer_id == c.id))).scalars())
        call_sec = (await db.execute(select(func.coalesce(func.sum(SalesCustomerCall.duration), 0)).where(
            SalesCustomerCall.customer_id == c.id))).scalar() or 0
        mkt = (await db.execute(select(func.count()).select_from(SalesCustomerConsent).where(
            SalesCustomerConsent.customer_id == c.id, SalesCustomerConsent.consent_type == "MARKETING",
            SalesCustomerConsent.agreed.is_(True)))).scalar() or 0

        score = 0; reasons = []
        n = len(consults)
        if n:
            score += min(n * 20, 40); reasons.append(f"상담 {n}회")
        if call_sec:
            score += 15; reasons.append(f"통화 {int(call_sec)//60}분")
        if mkt:
            score += 15; reasons.append("마케팅 수신동의")
        last = max((x.consulted_at for x in consults if x.consulted_at), default=None)
        if last:
            days = (now - (last if last.tzinfo else last.replace(tzinfo=UTC))).days
            if days <= 7:
                score += 20; reasons.append("최근 7일 내 상담")
            elif days <= 30:
                score += 10; reasons.append("최근 30일 내 상담")
        if c.first_visit_at:
            score += 10; reasons.append("방문 이력")

        grade = "A" if score >= 60 else "B" if score >= 30 else "C"
        next_action = next((x.next_action for x in consults if x.next_action), None) or (
            "계약 권유·잔여 혜택 안내" if grade == "A" else
            "재상담 예약·관심 평형 제안" if grade == "B" else "정보 발송·관심 환기")
        out.append({
            "customer_id": str(c.id), "name": c.name, "phone": c.phone_e164,
            "status": c.status, "current_grade": c.grade,
            "score": score, "suggested_grade": grade, "reasons": reasons, "next_action": next_action,
        })
    out.sort(key=lambda x: -x["score"])
    return {"count": len(out), "customers": out}


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


@views_router.get("/projection/accounting-rollup")
async def projection_accounting_rollup(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """시행사 통합회계 — 보유 현장 회계(매출·비용항목별·수수료·손익)를 유기적으로 합산(연결결산).

    각 현장 ERP가 단일 원장(sales_site_accounting)에 기록한 비용 + 계약 매출·수수료배분을
    현장별로 집계(site_management_detail)하고, 시행사 레벨로 롤업한다. '같이(통합)·따로(현장별)'.
    """
    from app.services.sales.admin.console import site_management_detail
    # site_management_detail 내부 _scalar 가 오류 시 rollback 하면 ORM 객체가 만료돼
    # 이후 s.id/s.site_name 접근이 lazy load(MissingGreenlet) 된다. 루프 전에 평문 추출.
    rows = (await db.execute(select(
        SalesSite.id, SalesSite.site_name, SalesSite.status).where(
        SalesSite.organization_id == user.tenant_id, SalesSite.deleted_at.is_(None)))).all()
    sites = []
    con = {"revenue": 0, "cost_total": 0, "commission": 0, "profit_estimate": 0}
    by_type: dict[str, int] = {}
    for sid, sname, sstatus in rows:
        d = await site_management_detail(db, sid)
        for t in d["accounting"]["by_type"]:
            by_type[t["label"]] = by_type.get(t["label"], 0) + int(t["amount"])
        con["revenue"] += int(d["revenue"])
        con["commission"] += int(d["commission"])
        con["profit_estimate"] += int(d["profit_estimate"])
        con["cost_total"] += int(d["accounting"]["cost_total"])
        sites.append({
            "site_id": str(sid), "site_name": sname, "status": sstatus,
            "revenue": d["revenue"], "cost_total": d["accounting"]["cost_total"],
            "commission": d["commission"], "profit_estimate": d["profit_estimate"],
            "by_type": d["accounting"]["by_type"],
        })
    return {
        "consolidated": {**con, "by_type": [{"label": k, "amount": v} for k, v in sorted(by_type.items())]},
        "sites": sites,
        "note": "통합회계 = 보유 현장 연결결산(매출 − 회계비용 − 수수료배분). 현장 ERP 원장 단일출처 합산.",
    }
