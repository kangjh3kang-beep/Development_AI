"""Phase1-F 전자 해촉증명서 — 발급주체/직인·개별/일괄발급·근무이력·일괄PDF·해시체인.

프리랜서 분양상담사가 연말정산용 해촉증명서를 여러 현장에서 쉽게 받도록:
  - 발급주체(시행/대행 법인)가 직인을 등록하고 개별/일괄로 발급
  - 프리랜서가 본인 근무이력을 확인하고 개별/일괄 신청, 기간/현장별로 관리, 일괄 PDF 다운로드

재사용(기존 무파괴)
  - 근무이력/기간 : sales_org_nodes(user_id·active·created_at) + sales_org_membership_history
  - 소득/원천징수 : sales_commission_payouts(gross/withholding/net) (claim→split→event→site 경로) +
                    sales_withholding_statements(payee 집계) 폴백
  - 직인 이미지   : 기존 /api/v1/uploads/image 로 업로드한 public URL 을 등록 시 전달
  - PDF          : app.services.sales.cert.termination_cert_pdf (reportlab, 직인 날인)
  - 해시체인     : analysis_ledger_service.append_analysis (best-effort)
  - 컨텍스트/격리 : deps_sales.sales_ctx / require_role (site·user 격리)

신규 테이블(_ensure, 멱등)
  cert_issuers              : 발급주체 법인(org/site·법인명·사업자번호·대표·직인url)
  termination_certificates  : 발급분(issuer·freelancer·site·기간·소득·pdf_url·ledger_hash·status)
  cert_requests             : 프리랜서 발급신청(user·site·기간·status)
"""

import contextlib
import logging
import uuid
from datetime import datetime

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_sales import SalesCtx, sales_ctx

logger = logging.getLogger(__name__)

termination_cert_router = APIRouter(tags=["sales-termination-cert"])

# 발급주체 등록 / 발급을 할 수 있는 현장 관리자 역할
_ISSUER_ROLES = {"SUPERADMIN", "DEVELOPER", "AGENCY", "GM_DIRECTOR"}

# 테이블/컬럼 미존재 PostgreSQL SQLSTATE(asyncpg). 이것만 '정상 0'(아직 안 만든 테이블)으로 본다.
# 42P01=undefined_table, 42703=undefined_column. 그 외 DB 오류는 은폐 금지(분류 로깅 후 전파).
# (settle_summary / admin.console 의 검증된 분류 패턴과 동일.)
_MISSING_OBJECT_SQLSTATES = frozenset({"42P01", "42703"})


def _missing_object_sqlstate(exc: BaseException) -> str | None:
    """예외가 '테이블/컬럼 미존재'(42P01/42703)면 해당 SQLSTATE, 아니면 None.

    asyncpg 의 원본 예외는 SQLAlchemy DBAPIError.orig 에 래핑된다. orig.sqlstate
    (또는 pgcode)로 분류한다. 이 두 코드만 '정상 0'(지급 전이라 아직 없는 테이블)으로 본다.
    """
    orig = getattr(exc, "orig", None) or exc
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if code in _MISSING_OBJECT_SQLSTATES:
        return code
    return None


# ── 멱등 테이블(_ensure) ─────────────────────────────────────────────────────
_ISSUER_DDL = (
    "CREATE TABLE IF NOT EXISTS cert_issuers ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  site_id uuid NOT NULL,"
    "  issuer_type varchar(12) NOT NULL DEFAULT 'AGENCY',"   # AGENCY(대행)|DEVELOPER(시행)
    "  company_name varchar(200) NOT NULL,"
    "  biz_reg_no varchar(20),"
    "  ceo_name varchar(120),"
    "  stamp_url text,"                                       # 직인 이미지 public URL
    "  created_by uuid,"
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_CERT_DDL = (
    "CREATE TABLE IF NOT EXISTS termination_certificates ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  certificate_no varchar(40) NOT NULL,"
    "  issuer_id uuid NOT NULL,"
    "  site_id uuid NOT NULL,"
    "  freelancer_user_id uuid NOT NULL,"
    "  freelancer_name varchar(120),"
    "  period_start date,"
    "  period_end date,"
    "  payee_name varchar(120),"
    "  payee_account varchar(120),"
    "  income_total numeric(16,0) DEFAULT 0,"
    "  withholding_total numeric(16,0) DEFAULT 0,"
    "  net_total numeric(16,0) DEFAULT 0,"
    "  tax_year int,"
    "  pdf_url text,"
    "  ledger_hash varchar(80),"
    "  status varchar(16) NOT NULL DEFAULT 'ISSUED',"        # ISSUED|REVOKED
    "  issued_by uuid,"
    "  issued_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_REQUEST_DDL = (
    "CREATE TABLE IF NOT EXISTS cert_requests ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  site_id uuid NOT NULL,"
    "  freelancer_user_id uuid NOT NULL,"
    "  period_start date,"
    "  period_end date,"
    "  status varchar(16) NOT NULL DEFAULT 'PENDING',"       # PENDING|ISSUED|REJECTED
    "  certificate_id uuid,"
    "  created_at timestamptz NOT NULL DEFAULT now()"
    ")"
)


async def _ensure(db: AsyncSession) -> None:
    """해촉증명서 관련 테이블 멱등 생성(최초 호출 시 1회). 기존 sales 테이블 무파괴."""
    await db.execute(text(_ISSUER_DDL))
    await db.execute(text(_CERT_DDL))
    await db.execute(text(_REQUEST_DDL))


# ── 스키마 ───────────────────────────────────────────────────────────────────
class IssuerCreate(BaseModel):
    company_name: str
    biz_reg_no: str | None = None
    ceo_name: str | None = None
    stamp_url: str | None = None       # /api/v1/uploads/image 로 업로드한 직인 URL
    issuer_type: str = "AGENCY"


class IssueTarget(BaseModel):
    user_id: uuid.UUID
    site_id: uuid.UUID | None = None   # 미지정 시 현재 컨텍스트 site
    period_start: str | None = None    # ISO date; 미지정 시 근무이력에서 자동
    period_end: str | None = None
    tax_year: int | None = None
    payee_name: str | None = None
    payee_account: str | None = None


class IssueRequest(BaseModel):
    issuer_id: uuid.UUID
    targets: list[IssueTarget]         # 개별=1건, 일괄=다건


class CertRequestCreate(BaseModel):
    sites: list[uuid.UUID]             # 개별=1, 일괄=다
    tax_year: int | None = None


class BulkPdfRequest(BaseModel):
    ids: list[uuid.UUID]


# ── 근무이력·소득 자동채움(재사용) ────────────────────────────────────────────
async def _work_history(db: AsyncSession, user_id: uuid.UUID,
                        site_id: uuid.UUID | None = None) -> list[dict]:
    """sales_org_nodes(+history) 로 사용자 근무이력(현장·기간·이름) 도출."""
    where = "n.user_id = :uid"
    params: dict = {"uid": str(user_id)}
    if site_id is not None:
        where += " AND n.site_id = :sid"
        params["sid"] = str(site_id)
    rows = (await db.execute(text(
        "SELECT n.site_id, s.site_name, n.active, n.created_at, n.display_name,"
        "       (SELECT max(h.at) FROM sales_org_membership_history h"
        "          WHERE h.node_id = n.id AND h.action = 'LEAVE') AS left_at"
        "  FROM sales_org_nodes n"
        "  LEFT JOIN sales_sites s ON s.id = n.site_id"
        f" WHERE {where}"
        " ORDER BY n.created_at"), params)).all()
    out: list[dict] = []
    for r in rows:
        out.append({
            "site_id": str(r[0]),
            "site_name": r[1] or "-",
            "active": bool(r[2]),
            "period_start": str(r[3].date()) if isinstance(r[3], datetime) else (str(r[3]) if r[3] else None),
            "display_name": r[4],
            "period_end": (str(r[5].date()) if isinstance(r[5], datetime) else (str(r[5]) if r[5] else None)),
        })
    return out


async def _income_for(db: AsyncSession, user_id: uuid.UUID, site_id: uuid.UUID,
                      tax_year: int | None) -> dict:
    """원천징수/소득 자동채움 — payout(claim→split→event→site) 합계, withholding_statements 폴백."""
    year_sql = ""
    params: dict = {"uid": str(user_id), "sid": str(site_id)}
    if tax_year:
        # ★[KST 세무연도 고정(iter-8 MEDIUM·correctness·TZ)] extract(year FROM p.paid_at) 은 DB 세션
        #   타임존에 의존해, 세션 UTC 면 한국시간 연초/연말 자정 근처(예: KST 1/1 08:00 = UTC 전년 12/31
        #   23:00) 지급이 전년으로 귀속돼 다른 세무연도에 잡힌다. 한국 원천징수영수증은 KST(달력) 기준이라
        #   AT TIME ZONE 'Asia/Seoul' 로 KST 변환 후 연도를 뽑아 세션TZ 무관하게 고정한다(연 경계 귀속 오류 차단).
        year_sql = " AND extract(year FROM (p.paid_at AT TIME ZONE 'Asia/Seoul')) = :yr"
        params["yr"] = tax_year
    # 경로: payout → (claim 또는 스케줄) → split → event(site) ; split.node→user 와 매칭
    #   ★[원천징수증명 정합] 소득증명(원천징수영수증)은 '공급가액 기준'(gross)이 정합이다 — 부가세(vat)는
    #     수령자(사업자)가 별도 신고하는 매출세액이지 본인의 소득/원천징수 대상이 아니므로 gross 만 합산한다.
    #     (extension.total_paid_of=gross+vat 는 '현금흐름' 집계용이라 의도가 다르다. 여기서는 손대지 않는다.)
    #   ★[지급 2소스 합산 — 구조적 누락 해소(iter-6 HIGH·법적 세무서류 정확성)] 지급(payout)은 두 경로로
    #     생긴다. 기존 1차 쿼리는 'INNER JOIN claims c ON c.id=p.claim_id' 만 사용했는데, 전 코드베이스에서
    #     payout 은 항상 마일스톤 스케줄 경로(extension.run_due_payouts → claim_id=None)로만 생성된다.
    #     그 결과 INNER JOIN claims 가 실재 지급 전량을 0 으로 떨궈, 분할지급 프리랜서의 원천징수영수증/
    #     해촉증명서 income_total·withholding_total 이 0 으로 과소표시됐다(법적 세무서류 오류).
    #     → settle_summary 와 동일하게 2소스 UNION ALL 로 합산한다.
    #       ① claim 경로 : payout.claim_id → claim → split → event(site) ; split.node→user.
    #       ② 스케줄 경로: payout(claim_id NULL) ← schedule.paid_payout_id → split → event(site) ;
    #                       split.node→user.
    #     중복합산 차단: ① 경로는 claim_id 가 채워진 payout 만, ② 경로는 p.claim_id IS NULL 만 집계해
    #     같은 payout 이 두 소스에 동시 잡히지 않게 한다(상호배타). 두 경로 모두 e.site_id=:sid +
    #     n.user_id=:uid 로 현장·사용자 격리를 동일하게 유지한다(원천징수증명은 gross-only — vat 미가산).
    try:
        row = (await db.execute(text(
            "SELECT coalesce(sum(g),0), coalesce(sum(wh),0), coalesce(sum(nt),0) FROM ("
            "  SELECT p.gross AS g, p.withholding AS wh, p.net AS nt"
            "    FROM sales_commission_payouts p"
            "    JOIN sales_commission_claims c ON c.id = p.claim_id"
            "    JOIN sales_commission_splits sp ON sp.id = c.split_id"
            "    JOIN sales_commission_events e ON e.id = sp.event_id"
            "    JOIN sales_org_nodes n ON n.id = sp.node_id"
            f"   WHERE e.site_id = :sid AND n.user_id = :uid{year_sql}"
            "  UNION ALL "
            "  SELECT p.gross AS g, p.withholding AS wh, p.net AS nt"
            "    FROM sales_commission_payouts p"
            "    JOIN sales_commission_payout_schedule sch ON sch.paid_payout_id = p.id"
            "    JOIN sales_commission_splits sp ON sp.id = sch.split_id"
            "    JOIN sales_commission_events e ON e.id = sp.event_id"
            "    JOIN sales_org_nodes n ON n.id = sp.node_id"
            f"   WHERE e.site_id = :sid AND n.user_id = :uid AND p.claim_id IS NULL{year_sql}"
            ") u"), params)).first()
        if row and (row[0] or row[1] or row[2]):
            return {"income_total": int(row[0]), "withholding_total": int(row[1]), "net_total": int(row[2])}
    except DBAPIError as e:
        # ★silent-fail 차단(iter-5): 과거엔 bare 'except Exception: pass' 로 모든 DB 오류를 삼켜
        #   소득=0 으로 은폐했다(증명서 금액 오판). settle_summary 와 동일하게 분류한다 —
        #   테이블/컬럼 미존재(42P01/42703)만 '정상 0'(아직 지급 도메인 미생성)으로 보고 폴백 경로로
        #   넘어가고, 권한·문법·연결 등 실오류는 0 으로 흡수하지 않고 전파한다.
        with contextlib.suppress(Exception):
            await db.rollback()  # 트랜잭션 오염 방지 롤백(미존재/전파 공통). 롤백 자체 실패는 무시.
        if _missing_object_sqlstate(e) is None:
            logger.error("_income_for 1차 소득집계 DB오류(전파): user=%s err=%s", str(user_id), str(e)[:200])
            raise
        logger.debug("_income_for 1차 소득집계 미존재객체 → 폴백 경로로 진행(user=%s)", str(user_id))
    # 폴백: withholding_statements(payee_node → user) 집계
    #   ★[폴백 year 누락 해소(iter-7 HIGH·correctness)] 1차 쿼리는 tax_year 를 p.paid_at 으로 거는데,
    #     폴백 쿼리엔 period/tax_year 필터가 전무했다. 그래서 폴백이 발화하면(1차 미존재 등) '전 기간'
    #     명세를 SUM 해, 특정 tax_year 의 원천징수영수증 income_total/withholding_total 이 과대표시됐다
    #     (예: 2025·2026 두 해 명세가 다 합산). statement.period(YYYY-MM)의 앞 4자리(연도)를 tax_year 로
    #     제약해 1차 쿼리와 동일한 연도 집계 기준을 맞춘다. period NULL 행은 연도불명이라 tax_year
    #     지정 시 자동 제외된다(left(NULL,4)=NULL → '<>' 비교 거짓). tax_year 미지정이면 기존 동작(전 기간).
    fb_year_sql = ""
    fb_params: dict = {"uid": str(user_id), "sid": str(site_id)}
    if tax_year:
        fb_year_sql = " AND left(w.period, 4) = :yr_str"
        fb_params["yr_str"] = str(tax_year)
    try:
        row = (await db.execute(text(
            "SELECT coalesce(sum(w.gross),0), coalesce(sum(w.withholding),0)"
            "  FROM sales_withholding_statements w"
            "  JOIN sales_org_nodes n ON n.id = w.payee_node_id"
            f" WHERE w.site_id = :sid AND n.user_id = :uid{fb_year_sql}"),
            fb_params)).first()
        if row:
            g, wh = int(row[0] or 0), int(row[1] or 0)
            return {"income_total": g, "withholding_total": wh, "net_total": g - wh}
    except DBAPIError as e:
        # ★silent-fail 차단(iter-5): 폴백 집계도 동일 분류 — 미존재만 0(정상), 실오류는 전파.
        with contextlib.suppress(Exception):
            await db.rollback()
        if _missing_object_sqlstate(e) is None:
            logger.error("_income_for 폴백 소득집계 DB오류(전파): user=%s err=%s", str(user_id), str(e)[:200])
            raise
        logger.debug("_income_for 폴백 소득집계 미존재객체 → 0 폴백(user=%s)", str(user_id))
    return {"income_total": 0, "withholding_total": 0, "net_total": 0}


async def _ledger(ctx: SalesCtx, cert_id: uuid.UUID, event: str, payload: dict) -> str | None:
    """발급 이벤트를 해시체인 원장에 best-effort 기록. content_hash 반환(있으면)."""
    try:
        from app.services.ledger import analysis_ledger_service as ledger
        tenant_id = getattr(ctx.user, "tenant_id", None)
        res = await ledger.append_analysis(
            analysis_type="termination_certificate",
            payload={"event": event, "certificate_id": str(cert_id),
                     "site_id": str(ctx.site_id), **payload},
            tenant_id=str(tenant_id) if tenant_id else None,
            project_id=str(cert_id),
            source="sales_cert",
            created_by=str(ctx.user.id),
        )
        return res.get("content_hash") if isinstance(res, dict) else None
    except Exception:  # noqa: BLE001 — 원장 기록 실패는 발급을 막지 않음
        return None


async def _load_cert(db: AsyncSession, cert_id: uuid.UUID) -> dict | None:
    row = (await db.execute(text(
        "SELECT c.id, c.certificate_no, c.issuer_id, c.site_id, c.freelancer_user_id,"
        "       c.freelancer_name, c.period_start, c.period_end, c.payee_name, c.payee_account,"
        "       c.income_total, c.withholding_total, c.net_total, c.tax_year, c.pdf_url,"
        "       c.ledger_hash, c.status, c.issued_at,"
        "       i.company_name, i.biz_reg_no, i.ceo_name, i.stamp_url, s.site_name"
        "  FROM termination_certificates c"
        "  LEFT JOIN cert_issuers i ON i.id = c.issuer_id"
        "  LEFT JOIN sales_sites s ON s.id = c.site_id"
        " WHERE c.id = :id"), {"id": str(cert_id)})).first()
    if not row:
        return None
    return {
        "id": str(row[0]), "certificate_no": row[1], "issuer_id": str(row[2]),
        "site_id": str(row[3]), "freelancer_user_id": str(row[4]),
        "freelancer_name": row[5],
        "period_start": str(row[6]) if row[6] else None,
        "period_end": str(row[7]) if row[7] else None,
        "payee_name": row[8], "payee_account": row[9],
        "income_total": int(row[10] or 0), "withholding_total": int(row[11] or 0),
        "net_total": int(row[12] or 0), "tax_year": row[13], "pdf_url": row[14],
        "ledger_hash": row[15], "status": row[16],
        "issued_at": str(row[17]) if row[17] else None,
        "issuer_company_name": row[18], "issuer_biz_no": row[19],
        "issuer_ceo_name": row[20], "issuer_stamp_url": row[21],
        "site_name": row[22] or "-",
    }


# ── 1) 발급주체 등록(직인 이미지 url) ─────────────────────────────────────────
@termination_cert_router.post("/cert/issuers", summary="발급주체(법인) 등록·직인 등록")
async def create_issuer(body: IssuerCreate, db: AsyncSession = Depends(get_db),
                        ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    if ctx.role not in _ISSUER_ROLES:
        raise HTTPException(403, "발급주체를 등록할 권한이 없습니다(시행/대행 본부장↑·관리자)")
    await _ensure(db)
    iss_id = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO cert_issuers (id, site_id, issuer_type, company_name, biz_reg_no, ceo_name, stamp_url, created_by)"
        " VALUES (:id, :sid, :tp, :cn, :biz, :ceo, :stamp, :by)"),
        {"id": str(iss_id), "sid": str(ctx.site_id), "tp": body.issuer_type,
         "cn": body.company_name, "biz": body.biz_reg_no, "ceo": body.ceo_name,
         "stamp": body.stamp_url, "by": str(ctx.user.id)})
    await db.commit()
    return {"id": str(iss_id), "site_id": str(ctx.site_id), "company_name": body.company_name,
            "biz_reg_no": body.biz_reg_no, "ceo_name": body.ceo_name, "stamp_url": body.stamp_url}


@termination_cert_router.get("/cert/issuers", summary="발급주체 목록(현장)")
async def list_issuers(db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    await _ensure(db)
    rows = (await db.execute(text(
        "SELECT id, issuer_type, company_name, biz_reg_no, ceo_name, stamp_url, created_at"
        "  FROM cert_issuers WHERE site_id = :sid ORDER BY created_at DESC"),
        {"sid": str(ctx.site_id)})).all()
    items = [{"id": str(r[0]), "issuer_type": r[1], "company_name": r[2], "biz_reg_no": r[3],
              "ceo_name": r[4], "stamp_url": r[5], "created_at": str(r[6])} for r in rows]
    return {"items": items, "count": len(items)}


# ── 2) 발급(개별 또는 일괄) ───────────────────────────────────────────────────
@termination_cert_router.post("/cert/issue", summary="해촉증명서 발급(개별/일괄)")
async def issue_certificates(body: IssueRequest, db: AsyncSession = Depends(get_db),
                             ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    if ctx.role not in _ISSUER_ROLES:
        raise HTTPException(403, "증명서를 발급할 권한이 없습니다(시행/대행 본부장↑·관리자)")
    if not body.targets:
        raise HTTPException(400, "발급 대상(targets)이 비어 있습니다")
    await _ensure(db)

    issuer = (await db.execute(text(
        "SELECT id, company_name, biz_reg_no, ceo_name, stamp_url FROM cert_issuers"
        " WHERE id = :id AND site_id = :sid"),
        {"id": str(body.issuer_id), "sid": str(ctx.site_id)})).first()
    if not issuer:
        raise HTTPException(404, "발급주체를 찾을 수 없습니다(현장 내 등록 필요)")

    issued: list[dict] = []
    for tgt in body.targets:
        site_id = tgt.site_id or ctx.site_id
        # site 격리 — 발급은 현재 컨텍스트 현장으로만(다른 현장 임의발급 차단)
        if str(site_id) != str(ctx.site_id):
            raise HTTPException(403, "발급은 현재 현장 컨텍스트에서만 가능합니다")

        history = await _work_history(db, tgt.user_id, site_id)
        hist = history[0] if history else {}
        p_start = tgt.period_start or hist.get("period_start")
        p_end = tgt.period_end or hist.get("period_end")
        income = await _income_for(db, tgt.user_id, site_id, tgt.tax_year)

        cert_id = uuid.uuid4()
        cert_no = f"TC-{datetime.utcnow():%Y%m%d}-{str(cert_id)[:8]}"
        await db.execute(text(
            "INSERT INTO termination_certificates"
            " (id, certificate_no, issuer_id, site_id, freelancer_user_id, freelancer_name,"
            "  period_start, period_end, payee_name, payee_account,"
            "  income_total, withholding_total, net_total, tax_year, status, issued_by)"
            " VALUES (:id,:no,:iss,:sid,:uid,:nm,:ps,:pe,:pn,:pa,:inc,:wh,:net,:yr,'ISSUED',:by)"),
            {"id": str(cert_id), "no": cert_no, "iss": str(body.issuer_id), "sid": str(site_id),
             "uid": str(tgt.user_id), "nm": hist.get("display_name"),
             "ps": p_start, "pe": p_end,
             "pn": tgt.payee_name or hist.get("display_name"), "pa": tgt.payee_account,
             "inc": income["income_total"], "wh": income["withholding_total"],
             "net": income["net_total"], "yr": tgt.tax_year, "by": str(ctx.user.id)})

        # 해시체인 기록(발급 무결성) → ledger_hash 저장
        lhash = await _ledger(ctx, cert_id, "issued", {
            "issuer_id": str(body.issuer_id), "freelancer_user_id": str(tgt.user_id),
            "period_start": p_start, "period_end": p_end, **income})
        if lhash:
            await db.execute(text(
                "UPDATE termination_certificates SET ledger_hash = :h WHERE id = :id"),
                {"h": lhash[:80], "id": str(cert_id)})

        # 해당 사용자의 동일 현장 PENDING 신청을 ISSUED 로 연결
        await db.execute(text(
            "UPDATE cert_requests SET status = 'ISSUED', certificate_id = :cid"
            " WHERE site_id = :sid AND freelancer_user_id = :uid AND status = 'PENDING'"),
            {"cid": str(cert_id), "sid": str(site_id), "uid": str(tgt.user_id)})

        issued.append({"id": str(cert_id), "certificate_no": cert_no,
                       "freelancer_user_id": str(tgt.user_id), "ledger_hash": lhash})

    await db.commit()
    return {"issued": issued, "count": len(issued)}


# ── 3) 프리랜서: 근무이력 ─────────────────────────────────────────────────────
@termination_cert_router.get("/cert/my-history", summary="내 근무이력(현장·기간 자동표시)")
async def my_history(db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    await _ensure(db)
    items = await _work_history(db, ctx.user.id)
    return {"items": items, "count": len(items)}


# ── 4) 프리랜서: 발급신청(개별/일괄) ──────────────────────────────────────────
@termination_cert_router.post("/cert/request", summary="해촉증명서 발급신청(개별/일괄)")
async def request_cert(body: CertRequestCreate, db: AsyncSession = Depends(get_db),
                       ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    if not body.sites:
        raise HTTPException(400, "신청할 현장(sites)이 비어 있습니다")
    await _ensure(db)
    created: list[str] = []
    for site_id in body.sites:
        # 본인이 근무한 현장만 신청 가능(이력 검증 — 임의 현장 신청 차단)
        hist = await _work_history(db, ctx.user.id, site_id)
        if not hist:
            continue
        h = hist[0]
        req_id = uuid.uuid4()
        await db.execute(text(
            "INSERT INTO cert_requests (id, site_id, freelancer_user_id, period_start, period_end, status)"
            " VALUES (:id, :sid, :uid, :ps, :pe, 'PENDING')"),
            {"id": str(req_id), "sid": str(site_id), "uid": str(ctx.user.id),
             "ps": h.get("period_start"), "pe": h.get("period_end")})
        created.append(str(req_id))
    await db.commit()
    return {"requested": created, "count": len(created)}


@termination_cert_router.get("/cert/my-requests", summary="내 발급신청 현황")
async def my_requests(db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    await _ensure(db)
    rows = (await db.execute(text(
        "SELECT r.id, r.site_id, s.site_name, r.period_start, r.period_end, r.status, r.certificate_id, r.created_at"
        "  FROM cert_requests r LEFT JOIN sales_sites s ON s.id = r.site_id"
        " WHERE r.freelancer_user_id = :uid ORDER BY r.created_at DESC"),
        {"uid": str(ctx.user.id)})).all()
    items = [{"id": str(r[0]), "site_id": str(r[1]), "site_name": r[2] or "-",
              "period_start": str(r[3]) if r[3] else None, "period_end": str(r[4]) if r[4] else None,
              "status": r[5], "certificate_id": str(r[6]) if r[6] else None,
              "created_at": str(r[7])} for r in rows]
    return {"items": items, "count": len(items)}


# ── 5) 프리랜서: 발급받은 증명서 관리(기간/현장별) ────────────────────────────
@termination_cert_router.get("/cert/my-certs", summary="내 증명서 목록(연도·현장별)")
async def my_certs(year: int | None = Query(default=None),
                   site_id: uuid.UUID | None = Query(default=None),
                   db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    await _ensure(db)
    where = "c.freelancer_user_id = :uid AND c.status = 'ISSUED'"
    params: dict = {"uid": str(ctx.user.id)}
    if year is not None:
        where += " AND (c.tax_year = :yr OR extract(year FROM c.issued_at) = :yr)"
        params["yr"] = year
    if site_id is not None:
        where += " AND c.site_id = :sid"
        params["sid"] = str(site_id)
    rows = (await db.execute(text(
        "SELECT c.id, c.certificate_no, c.site_id, s.site_name, c.period_start, c.period_end,"
        "       c.income_total, c.withholding_total, c.net_total, c.tax_year, c.issued_at,"
        "       i.company_name"
        "  FROM termination_certificates c"
        "  LEFT JOIN sales_sites s ON s.id = c.site_id"
        "  LEFT JOIN cert_issuers i ON i.id = c.issuer_id"
        f" WHERE {where} ORDER BY c.issued_at DESC"), params)).all()
    items = [{"id": str(r[0]), "certificate_no": r[1], "site_id": str(r[2]), "site_name": r[3] or "-",
              "period_start": str(r[4]) if r[4] else None, "period_end": str(r[5]) if r[5] else None,
              "income_total": int(r[6] or 0), "withholding_total": int(r[7] or 0),
              "net_total": int(r[8] or 0), "tax_year": r[9],
              "issued_at": str(r[10]) if r[10] else None, "issuer_company_name": r[11]}
             for r in rows]
    return {"items": items, "count": len(items)}


# ── 6) PDF (개별) ─────────────────────────────────────────────────────────────
def _can_access_cert(cert: dict, ctx: SalesCtx) -> bool:
    """본인(프리랜서) 또는 동일 현장의 발급권한 관리자만 접근(site·user 격리)."""
    if cert["freelancer_user_id"] == str(ctx.user.id):
        return True
    return ctx.role in _ISSUER_ROLES and cert["site_id"] == str(ctx.site_id)


@termination_cert_router.get("/cert/{cert_id}/pdf", summary="해촉증명서 PDF(개별)")
async def cert_pdf(cert_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                   ctx: SalesCtx = Depends(sales_ctx)) -> Response:
    await _ensure(db)
    cert = await _load_cert(db, cert_id)
    if not cert:
        raise HTTPException(404, "증명서를 찾을 수 없습니다")
    if not _can_access_cert(cert, ctx):
        raise HTTPException(403, "본인 또는 발급 현장 관리자만 열람할 수 있습니다")
    # P2-4: reportlab/urllib blocking → 스레드 오프로드(이벤트루프 비차단)
    pdf = await anyio.to_thread.run_sync(_build_pdf, cert, db)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{cert["certificate_no"]}.pdf"'})


def _build_image(cert: dict, db: AsyncSession, fmt: str) -> tuple[bytes, str]:
    """증명서 PDF → PNG/JPEG 래스터(PyMuPDF). 미설치 시 503 정직 안내."""
    try:
        import fitz  # PyMuPDF
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, "이미지 변환 모듈(PyMuPDF)이 아직 배포되지 않았습니다. PDF를 이용하세요.") from exc
    pdf = _build_pdf(cert, db)
    doc = fitz.open(stream=pdf, filetype="pdf")
    page = doc.load_page(0)
    pix = page.get_pixmap(dpi=150)               # 인쇄·공유용 적정 해상도
    out_fmt = "jpeg" if fmt in ("jpg", "jpeg") else "png"
    img = pix.tobytes(output=out_fmt, jpg_quality=92) if out_fmt == "jpeg" else pix.tobytes(output="png")
    doc.close()
    return img, ("image/jpeg" if out_fmt == "jpeg" else "image/png")


@termination_cert_router.get("/cert/{cert_id}/image", summary="해촉증명서 이미지(PNG/JPEG)")
async def cert_image(cert_id: uuid.UUID, fmt: str = "png", db: AsyncSession = Depends(get_db),
                     ctx: SalesCtx = Depends(sales_ctx)) -> Response:
    """발급된 증명서를 PNG/JPEG로 제공(인쇄·공유용). fmt=png|jpeg."""
    await _ensure(db)
    cert = await _load_cert(db, cert_id)
    if not cert:
        raise HTTPException(404, "증명서를 찾을 수 없습니다")
    if not _can_access_cert(cert, ctx):
        raise HTTPException(403, "본인 또는 발급 현장 관리자만 열람할 수 있습니다")
    # P2-4: PyMuPDF blocking 오프로드(이벤트루프 비차단)
    img, mime = await anyio.to_thread.run_sync(_build_image, cert, db, (fmt or "png").lower())
    ext = "jpg" if mime == "image/jpeg" else "png"
    return Response(content=img, media_type=mime,
                    headers={"Content-Disposition": f'inline; filename="{cert["certificate_no"]}.{ext}"'})


# ── 7) PDF (일괄 — zip) ──────────────────────────────────────────────────────
@termination_cert_router.post("/cert/bulk-pdf", summary="해촉증명서 일괄 PDF(zip)")
async def bulk_pdf(body: BulkPdfRequest, db: AsyncSession = Depends(get_db),
                   ctx: SalesCtx = Depends(sales_ctx)) -> Response:
    import io
    import zipfile

    if not body.ids:
        raise HTTPException(400, "다운로드할 증명서(ids)가 비어 있습니다")
    await _ensure(db)
    buf = io.BytesIO()
    n = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for cid in body.ids:
            cert = await _load_cert(db, cid)
            if not cert or not _can_access_cert(cert, ctx):
                continue  # 접근 불가/없는 항목은 조용히 제외(타인 증명서 노출 차단)
            pdf_bytes = await anyio.to_thread.run_sync(_build_pdf, cert, db)  # P2-4: blocking 오프로드(일괄 N건)
            zf.writestr(f"{cert['certificate_no']}.pdf", pdf_bytes)
            n += 1
    if n == 0:
        raise HTTPException(403, "다운로드 가능한 증명서가 없습니다")
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="termination_certificates.zip"'})


def _build_pdf(cert: dict, db: AsyncSession) -> bytes:
    """증명서 dict → PDF bytes. reportlab 미설치 시 503 안내(런타임 의존성)."""
    try:
        from app.services.sales.cert.termination_cert_pdf import build_termination_cert_pdf
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"PDF 생성 모듈 로드 실패: {exc}") from exc
    try:
        return build_termination_cert_pdf(cert)
    except ModuleNotFoundError as exc:
        raise HTTPException(503, "PDF 생성 라이브러리(reportlab)가 설치되지 않았습니다") from exc
