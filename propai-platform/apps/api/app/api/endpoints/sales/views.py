"""sales 읽기 뷰 — 프론트(현장목록/조직트리/Unit360/분양가표/시행사 투영) 지원 집계 엔드포인트."""

import contextlib
import logging
import uuid
from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.deps_sales import SalesCtx, sales_ctx
from apps.api.database.models.sales.commission_mh_harness import (
    SalesCommissionDistribution,
    SalesCommissionMaster,
)
from apps.api.database.models.sales.contract_crm_ad import SalesContractExt, SalesContractInstallment
from apps.api.database.models.sales.site_org import SalesOrgNode, SalesSite, SalesSiteSummary
from apps.api.database.models.sales.units_pricing import (
    SalesUnitInventory,
    SalesUnitPriceBreakdown,
    SalesUnitPriceTable,
    SalesUnitStatusLog,
)

views_router = APIRouter(tags=["sales-views"])

_log = logging.getLogger(__name__)

# 운영자에게 노출해도 안전한 오류 분류 코드(원문은 서버 로그만). SQLSTATE/스키마/테이블명 미노출.
#   42501=insufficient_privilege(권한) → PERMISSION
#   08xxx=connection_exception 계열 → DB_CONNECTION
#   그 외 DBAPIError → DB_ERROR, 비-DB 예외 → INTERNAL
def _classify_error(exc: BaseException) -> str:
    """예외를 운영자 노출용 분류코드로 환원(원문 비노출). 분류 근거=SQLSTATE 접두.

    원문(str(exc))에는 컬럼/테이블/스키마/SQLSTATE 가 포함될 수 있어 그대로 응답에 실으면
    내부 구조가 누출된다. 여기서는 안전한 카테고리만 반환하고, 원문은 호출부에서 로그로만 남긴다.
    """
    if isinstance(exc, DBAPIError):
        orig = getattr(exc, "orig", None) or exc
        raw = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None) or ""
        # asyncpg는 보통 sqlstate 를 문자열로 주지만, 일부 드라이버/경로는 int 로 줄 수 있다.
        # int 42501 이 그대로 비교되면 PERMISSION 을 놓쳐 generic DB_ERROR 로 오분류된다 →
        # 문자열로 통일해 int/str 양쪽 모두 정확히 분류한다(은폐 금지=정밀 분류).
        code = str(raw)
        if code == "42501":
            return "PERMISSION"
        if code.startswith("08"):
            return "DB_CONNECTION"
        return "DB_ERROR"
    return "INTERNAL"


# ── [보안 HIGH] 시행사 연결결산(통합회계) 조회 권한 게이트 ─────────────────────────
#   projection_summary / projection_accounting_rollup 은 '단일 현장'이 아니라 한 테넌트가
#   보유한 모든 현장의 연결결산(매출·비용·수수료·손익)을 노출한다. 따라서 actions.py 의
#   현장단위 형제(/admin/site-detail·/accounting/*)와 동일한 등급
#   (GM_DIRECTOR/SUBAGENCY/AGENCY/DEVELOPER/SUPERADMIN)으로 보호해야 한다.
#
#   ★주의(왜 require_role 을 직접 못 쓰나): require_role→sales_ctx→resolve_site 는 '단일 현장
#     컨텍스트(X-Site-Code/경로 site_id/서브도메인)'를 강제하는데, 이 두 엔드포인트는
#     테넌트 전역(현장 컨텍스트 없음·salesGlobal 가 X-Site-Code 미전송)이라 그대로 붙이면
#     resolve_site 가 400 으로 전 응답을 깨뜨린다(회귀). 그래서 동일 '등급 강제'를 테넌트
#     스코프로 환원한 게이트를 둔다 — get_current_user 로 테넌트(user.tenant_id) 스코프를
#     유지하면서, 플랫폼 등급(superadmin/developer) 또는 '본인 테넌트 현장 소유(시행사)'만
#     허용한다. 이는 sales_ctx 의 분류(_SUPERADMIN_ROLES/_DEVELOPER_ROLES/owns_site→DEVELOPER)
#     와 동일 의미다. 순수 viewer(영업직/구독 최하위, 소유현장 0)는 403 으로 차단(권한상승 방지).
_TENANT_FINANCE_ROLES = {
    "superadmin", "super_admin", "admin", "owner", "총괄관리자", "platform_admin",
    "developer", "시행사", "dev",
}


async def require_tenant_finance(
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """테넌트 연결결산 조회 게이트 — 플랫폼 등급 또는 본인 테넌트 현장 소유자만 허용.

    현장 컨텍스트 없는 테넌트 전역 집계라 require_role(현장 게이트)를 쓸 수 없어, 동일 등급
    의도(GM_DIRECTOR/SUBAGENCY/AGENCY/DEVELOPER/SUPERADMIN)를 테넌트 스코프로 강제한다.
    허용: ①플랫폼 role 이 superadmin/developer 계열 ②또는 본인 테넌트가 현장 1곳 이상 소유(시행사).
    차단: 순수 viewer(영업직/구독 최하위, 소유 현장 0) → 403(연결결산 권한상승 방지).
    """
    role_lower = (getattr(user, "role", "") or "").lower()
    if role_lower in _TENANT_FINANCE_ROLES:
        return user
    # 본인 테넌트가 소유한 현장이 1곳이라도 있으면 시행사(DEVELOPER)로 인정(sales_ctx owns_site 와 동일).
    #   소유 판정은 SalesSite.organization_id == user.tenant_id (provision 시 저장되는 소유 테넌트).
    tenant_id = getattr(user, "tenant_id", None)
    if tenant_id:
        owns = (await db.execute(select(func.count()).select_from(SalesSite).where(
            SalesSite.organization_id == tenant_id, SalesSite.deleted_at.is_(None)))).scalar() or 0
        if owns > 0:
            return user
    raise HTTPException(403, "시행사 연결결산(통합회계) 조회 권한이 없습니다(시행사·관리자 등급 전용).")


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
    from datetime import datetime

    from apps.api.database.models.sales.contract_crm_ad import (
        SalesCustomer,
        SalesCustomerCall,
        SalesCustomerConsent,
        SalesCustomerConsultation,
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
    """조직 트리 — ★서브트리 가시성 스코프(2026-07-23 직속 파이프라인 스펙).

    org_path(내 노드)가 있는 역할은 '자신이 승인·지정한 하부'(내 노드 포함 서브트리)만 본다.
    본사 권한(SUPERADMIN/DEVELOPER/AGENCY 멤버십 등 org_path 없음)은 현장 전체.
    응답 shape 은 기존 배열 그대로(소비처 OrgTree·CommissionDutchPay 무회귀 — 더치페이
    참여자 선택도 내 하부로 좁아지는 것이 스펙 정합).
    """
    q = select(SalesOrgNode).where(
        SalesOrgNode.site_id == ctx.site_id, SalesOrgNode.deleted_at.is_(None))
    my_path = getattr(ctx, "org_path", None) or ""
    rows = (await db.execute(q)).scalars().all()
    if my_path:
        rows = [n for n in rows
                if str(n.path) == my_path or str(n.path).startswith(my_path + ".")]
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
async def projection_summary(db: AsyncSession = Depends(get_db), user=Depends(require_tenant_finance)):
    """시행사 투영 — 현장별 누적 집계(개인정보 없음). sales_site_summary 증분행 합산.

    [보안] 테넌트 연결결산 조회는 require_tenant_finance 로 보호(시행사·관리자 등급 전용).
    """
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
async def projection_accounting_rollup(db: AsyncSession = Depends(get_db), user=Depends(require_tenant_finance)):
    """시행사 통합회계 — 보유 현장 회계(매출·비용항목별·수수료·손익)를 유기적으로 합산(연결결산).

    각 현장 ERP가 단일 원장(sales_site_accounting)에 기록한 비용 + 계약 매출·수수료배분을
    현장별로 집계(site_management_detail)하고, 시행사 레벨로 롤업한다. '같이(통합)·따로(현장별)'.

    [보안] 연결결산(매출·비용·수수료·손익) 전체 노출 → require_tenant_finance 로 보호
      (시행사·관리자 등급 전용, 순수 viewer/영업직 403). actions.py 형제 엔드포인트와 동일 등급.
    """
    from app.services.sales.admin.console import site_management_detail
    log = _log
    # site_management_detail 내부 _scalar 가 오류 시 rollback 하면 ORM 객체가 만료돼
    # 이후 s.id/s.site_name 접근이 lazy load(MissingGreenlet) 된다. 루프 전에 평문 추출.
    rows = (await db.execute(select(
        SalesSite.id, SalesSite.site_name, SalesSite.status).where(
        SalesSite.organization_id == user.tenant_id, SalesSite.deleted_at.is_(None)))).all()
    sites: list[dict] = []
    # 연결결산 합산기 — 발생주의(profit_estimate=accrual)는 하위호환 유지, 현금흐름·선수금·미수금 추가.
    con = {"revenue": 0, "cost_total": 0, "commission": 0, "profit_estimate": 0,
           "cash_collected": 0, "cash_profit": 0, "deferred_revenue": 0, "receivable": 0}
    by_type: dict[str, int] = {}
    errors: list[dict[str, str]] = []  # 현장별 부분내결함 표기(은폐 금지: 응답+로깅)
    # 독립 대사(reconciliation) 실패 현장 수 — site_management_detail 의 reconciliation.balanced
    #   가 False(약정-계약/비율/수납초과 불일치 또는 '서명매출>0인데 약정표 누락')인 현장의 합.
    #   지금까지 reconciliation 은 응답에 실려 있었으나 프론트가 전혀 소비하지 않는 dead output
    #   이었다(grep 소비 0). 이를 consolidated.reconcile_failed_count(머신리더블)로 전파해
    #   '연결결산 정합 경고' 배너를 결정적으로 띄운다(은폐 금지). balanced=None(판정보류)은 실패가
    #   아니므로 세지 않는다(약정표 부재로 대사 불가일 뿐, 데이터 불일치는 아님).
    reconcile_failed_count = 0
    for sid, sname, sstatus in rows:
        # [부분내결함] 한 현장의 비-미존재 DB오류(권한·연결)가 전체 롤업 500 을 유발하지 않도록
        # 현장 단위로 격리한다. 실패 현장은 error 로 표기하고 나머지는 정상 합산한다(은폐 금지).
        try:
            d = await site_management_detail(db, sid)
        except Exception as e:  # noqa: BLE001 — 분류 로깅+응답 표기 후 다음 현장 진행(전체 500 방지).
            # _scalar 가 전파한 실오류로 트랜잭션이 오염됐을 수 있어 롤백 후 다음 현장 계속.
            with contextlib.suppress(Exception):
                await db.rollback()
            # [오류원문 비노출] str(e) 원문에는 SQLSTATE/테이블/컬럼/스키마가 섞여 내부구조를
            #   누출한다 → 응답엔 안전한 분류코드(error_code)+상관ID(correlation_id)만 싣고,
            #   원문은 서버 로그에만 남긴다(운영자가 로그에서 correlation_id 로 역추적).
            error_code = _classify_error(e)
            corr_id = uuid.uuid4().hex[:12]
            log.error("accounting-rollup 현장(%s) 집계 실패(격리) code=%s corr=%s: %s",
                      sid, error_code, corr_id, str(e)[:300])
            # 실패 현장은 errors[] 단일출처로만 표기한다(프론트 통합회계 배너가 errors[] 를
            #   조인 없이 직접 렌더 — ERROR 배지+분류코드+상관ID). sites[] 에는 합산 가능한
            #   '데이터 행'만 넣으므로 실패 현장은 sites[] 에서 제외해 dead output(status='ERROR'·
            #   site_status·error_code·correlation_id 미소비)을 완전 제거한다(타입-데이터 정합).
            errors.append({"site_id": str(sid), "site_name": sname,
                           "error_code": error_code, "correlation_id": corr_id})
            continue
        cf = d.get("cash_flow") or {}
        acc = d.get("accrual") or {}
        rec = d.get("reconciliation") or {}
        if rec.get("balanced") is False:  # None(판정보류)·True(통과)는 제외, False(불일치)만 카운트
            reconcile_failed_count += 1
        for t in d["accounting"]["by_type"]:
            by_type[t["label"]] = by_type.get(t["label"], 0) + int(t["amount"])
        con["revenue"] += int(d["revenue"])
        con["commission"] += int(d["commission"])
        con["profit_estimate"] += int(d["profit_estimate"])
        con["cost_total"] += int(d["accounting"]["cost_total"])
        con["cash_collected"] += int(cf.get("cash_collected", 0))
        con["cash_profit"] += int(cf.get("profit", 0))
        con["deferred_revenue"] += int(d.get("deferred_revenue", 0))
        con["receivable"] += int(acc.get("receivable", 0))
        sites.append({
            "site_id": str(sid), "site_name": sname, "status": sstatus,
            "revenue": d["revenue"], "cost_total": d["accounting"]["cost_total"],
            "commission": d["commission"], "profit_estimate": d["profit_estimate"],
            # 손익 2-뷰 + 선수금/미수금 — 현장별 드릴다운에서도 동일 3지표 표기.
            "cash_flow": cf, "accrual": acc, "deferred_revenue": d.get("deferred_revenue", 0),
            "by_type": d["accounting"]["by_type"],
            # 독립 대사 결과 — 프론트 현장 드릴다운/배너가 balanced·discrepancies(약정표 누락·수납초과)
            #   를 가시화한다(dead output 해소). 합산 불가 메타라 con 에는 넣지 않고 행에만 동봉.
            "reconciliation": rec,
        })
    # ── 통합총계 완전성 플래그(머신리더블) — dead output 해소 ──────────────────────
    #   실패 현장은 continue 로 합산에서 제외돼 consolidated 가 '과소계상'된다. 이 사실이
    #   지금까지 note(산문)에만 있어 클라이언트가 코드로 판별할 수 없었다(dead output).
    #   complete=실패 0건(전부 합산), failed_count=실패 현장 수, partial=일부만 합산(과소계상).
    #   프론트는 이 플래그로 '통합총계가 일부 누락' 배너를 결정적으로 띄운다.
    failed_count = len(errors)
    complete = failed_count == 0
    return {
        "consolidated": {**con, "by_type": [{"label": k, "amount": v} for k, v in sorted(by_type.items())],
                         "complete": complete, "failed_count": failed_count, "partial": not complete,
                         # 독립 대사 불일치 현장 수(reconciliation.balanced=False 합). 집계실패(failed_count)
                         #   와 별개 신호 — 합산은 됐지만 현장 원장 정합이 깨진 곳이 있음을 알린다.
                         "reconcile_failed_count": reconcile_failed_count},
        "sites": sites,
        "errors": errors,
        "note": ("통합회계 = 보유 현장 연결결산. 손익 2-뷰: profit_estimate=발생주의(계약매출 기준, "
                 "미수금 포함 과대계상 가능)·cash_profit=현금흐름(실수납 기준). 선수금(deferred_revenue)·"
                 "미수금(receivable) 별도 표기. 현장 ERP 원장 단일출처 합산. "
                 "일부 현장 집계 실패 시 errors[] 에 분류코드(error_code)+상관ID(correlation_id)로 표기하고 "
                 "나머지는 합산(부분내결함). 실패 현장은 sites[] 에서 제외(errors[] 단일출처). "
                 "consolidated.complete/failed_count/partial 로 과소계상 여부를 머신리더블 신호로 제공 "
                 "(원문은 서버로그만, 응답엔 분류코드+상관ID). 또한 각 현장의 독립 대사 결과는 "
                 "sites[].reconciliation 에 동봉하고, 불일치(balanced=False) 현장 수는 "
                 "consolidated.reconcile_failed_count 로 제공(합산은 됐으나 원장 정합 경고)."),
    }
