"""세무 — 지급명세서(수수료 원천징수 집계)/세금계산서(건물 과세·토지 면세). 산출/기록만, 제출은 어댑터+승인."""

from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.tax import SalesTaxInvoice, SalesWithholdingStatement
from apps.api.database.models.sales.units_pricing import SalesUnitPriceBreakdown

# 지급(payout) 2소스 합산 + 수령노드별 그룹핑 집계 SQL(공용 — build/read 가 동일 기준으로 본다).
#   ① claim 경로 : payout.claim_id → claim → split → event(site).
#   ② 스케줄 경로: payout(claim_id NULL) ← schedule.paid_payout_id → split → event(site).
# 중복합산 차단: ① 경로는 claim_id 가 채워진 payout 만, ② 경로는 p.claim_id IS NULL 만 집계해
# 같은 payout 이 두 소스에 동시 잡히지 않게 한다(상호배타).
# site 스코프는 event(e.site_id) 로 잡는다(claim.site_id 단독 의존 제거 — 스케줄 경로엔 claim 이 없음).
#
# ★[KST 세무월 고정(iter-8 MEDIUM·correctness·TZ)] period(YYYY-MM)는 p.paid_at(timestamptz)로 거른다.
#   to_char(p.paid_at,'YYYY-MM') 은 'DB 세션 타임존'에 의존해, 세션이 UTC 면 한국시간 자정 근처(예: KST
#   6/1 08:00 = UTC 5/31 23:00)에 지급된 건이 5월로 귀속돼 다른 세무월에 잡힌다. 한국 세무서류는 KST(달력)
#   기준이라, AT TIME ZONE 'Asia/Seoul' 로 paid_at 을 KST 로 변환한 뒤 'YYYY-MM' 을 뽑아 세션TZ 무관하게
#   고정한다(월 경계 귀속 오류 차단).
# ★[소득구분 분기(iter-8 MEDIUM·correctness)] payout 의 tax_type 을 함께 끌어와 노드별로 집계한다.
#   WITHHOLDING(3.3% 사업소득)은 income_type='BIZ_3_3', VAT(세금계산서 발행 사업자)는 'VAT' 로 분기한다.
#   VAT 수령자는 3.3% 원천징수 대상이 아니므로 'BIZ_3_3' 하드코딩은 법적 서류의 소득구분 오류였다.
#   노드 1건의 tax_type 은 set_node_tax_type 으로 단일 선호가 유지되므로(노드당 1유형), node_id 로
#   그룹핑하며 max(tax_type) 으로 그 노드의 소득구분을 대표시킨다(tax_type NULL 행은 기본 WITHHOLDING).
_WH_AGG_SQL = (
    "SELECT node_id, coalesce(sum(g),0), coalesce(sum(wh),0),"
    "       coalesce(max(tt),'WITHHOLDING') FROM ("
    "  SELECT sp.node_id AS node_id, p.gross AS g, p.withholding AS wh,"
    "         coalesce(p.tax_type,'WITHHOLDING') AS tt"
    "    FROM sales_commission_payouts p"
    "    JOIN sales_commission_claims c ON c.id = p.claim_id"
    "    JOIN sales_commission_splits sp ON sp.id = c.split_id"
    "    JOIN sales_commission_events e ON e.id = sp.event_id"
    "   WHERE e.site_id = :sid"
    "     AND to_char(p.paid_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM') = :period"
    "  UNION ALL "
    "  SELECT sp.node_id AS node_id, p.gross AS g, p.withholding AS wh,"
    "         coalesce(p.tax_type,'WITHHOLDING') AS tt"
    "    FROM sales_commission_payouts p"
    "    JOIN sales_commission_payout_schedule sch ON sch.paid_payout_id = p.id"
    "    JOIN sales_commission_splits sp ON sp.id = sch.split_id"
    "    JOIN sales_commission_events e ON e.id = sp.event_id"
    "   WHERE e.site_id = :sid"
    "     AND to_char(p.paid_at AT TIME ZONE 'Asia/Seoul', 'YYYY-MM') = :period"
    "     AND p.claim_id IS NULL"
    ") u GROUP BY node_id"
)

# payout.tax_type → 지급명세서 income_type(소득구분) 매핑(법적 서류 분류 정합).
#   WITHHOLDING → BIZ_3_3(3.3% 사업소득 원천징수), VAT → VAT(세금계산서 발행 사업자, 원천 비대상).
#   income_type 컬럼은 varchar(10)이라 두 코드 모두 길이 내(BIZ_3_3=7, VAT=3).
_INCOME_TYPE_BY_TAX = {"WITHHOLDING": "BIZ_3_3", "VAT": "VAT"}


async def build_withholding_statements(db: AsyncSession, site_id, period: str):
    """기간(YYYY-MM) 내 현장 수수료 지급(원천징수) 집계 → 지급명세서(수령노드별 1건) 적재(멱등).

    ★[지급 2소스 합산 — 구조적 누락 해소(iter-6 HIGH·법적 세무서류 정확성)] 지급(payout)은 두 경로로
      생긴다(claim 승인 / 마일스톤 스케줄). 기존 1소스(INNER JOIN claims)만 쓰면 스케줄 지급분
      (claim_id=None)이 전량 누락돼 명세 gross/withholding 이 0 으로 과소표시되고, payee_node_id 도
      비어 폴백 JOIN(_income_for)이 실패한다. → _WH_AGG_SQL 로 두 소스를 합산하고 수령노드별로
      그룹핑해 statement 마다 payee_node_id 를 채운다(폴백 JOIN 복구).

    ★[멱등화 — 쓰기 GET 증폭 차단(iter-7 HIGH)] 과거엔 GET 호출마다 무조건 INSERT 라, (site,period,node)
      유니크가 없는 상태에서 동일 기간 재호출 시 같은 명세가 N행으로 중복누적됐다(법적 서류 중복).
      → MEMORY G2B rebuild_award_stats 의 'delete-before-insert' 패턴을 차용해, 이번 (site,period)
        명세를 먼저 전부 DELETE 한 뒤 재집계 INSERT 한다. 따라서 같은 기간을 몇 번 빌드해도 행수·합계가
        불변이다(정본 멱등키는 Alembic 034 uq_withholding_site_period_node — 동시 빌드 race 까지 차단).
        DELETE 범위는 '이 현장·이 기간(payee_node_id 무관)'으로, 노드 구성이 바뀌어도(노드 추가/삭제)
        잔존 행이 남지 않게 한다(중복·유령행 동시 차단).
    """
    # 1) 동일 (site, period) 기존 명세 선삭제(멱등 — 재빌드 시 누적 방지). period 한정이라 타 기간 보존.
    await db.execute(text(
        "DELETE FROM sales_withholding_statements WHERE site_id = :sid AND period = :period"),
        {"sid": str(site_id), "period": period})
    # 2) 2소스 합산·노드별 그룹핑 재집계 → INSERT.
    rows = (await db.execute(text(_WH_AGG_SQL),
                             {"sid": str(site_id), "period": period})).all()
    statements: list[SalesWithholdingStatement] = []
    for r in rows:
        node_id, gross, wh = r[0], int(r[1] or 0), int(r[2] or 0)
        # ★[소득구분 분기] 노드의 tax_type(집계 4번째 컬럼)으로 income_type 을 정한다(BIZ_3_3/VAT).
        #   알 수 없는 값은 보수적으로 WITHHOLDING(BIZ_3_3)으로 본다(기존 기본값과 동일·하위호환).
        tax_type = (r[3] or "WITHHOLDING") if len(r) > 3 else "WITHHOLDING"
        income_type = _INCOME_TYPE_BY_TAX.get(str(tax_type).upper(), "BIZ_3_3")
        st = SalesWithholdingStatement(site_id=site_id, period=period, income_type=income_type,
                                       payee_node_id=node_id, gross=gross, withholding=wh)
        db.add(st)
        statements.append(st)
    await db.flush()
    return statements


async def read_withholding_statements(db: AsyncSession, site_id, period: str) -> list[dict]:
    """[조회 전용·safe GET] 이미 적재된 지급명세서를 읽기만 한다(쓰기 없음).

    ★[GET 시맨틱 복원(iter-7 HIGH)] 지급명세서 빌드(쓰기)는 POST /tax/withholding-statements/build 로
      분리됐다. 이 함수는 GET 경로용으로, 적재된 명세 행을 그대로 돌려준다(db.add/commit 없음).
      → 동일 GET 을 몇 번 호출해도 DB 상태가 변하지 않는다(safe/idempotent GET 복원).
      아직 빌드 전이면 빈 목록을 돌려준다(정상 0 — 은폐가 아니라 '아직 빌드 안 함').
    """
    rows = (await db.execute(text(
        "SELECT payee_node_id, coalesce(gross,0), coalesce(withholding,0)"
        "  FROM sales_withholding_statements"
        " WHERE site_id = :sid AND period = :period"
        " ORDER BY payee_node_id"),
        {"sid": str(site_id), "period": period})).all()
    return [{"payee_node_id": str(r[0]) if r[0] else None,
             "gross": int(r[1] or 0), "withholding": int(r[2] or 0)} for r in rows]


async def issue_tax_invoice(db: AsyncSession, site_id, direction, counterparty_biz_no,
                            supply_amount, vat_amount, item):
    inv = SalesTaxInvoice(site_id=site_id, direction=direction, counterparty_biz_no=counterparty_biz_no,
                          supply_amount=supply_amount, vat_amount=vat_amount, item=item,
                          issued_at=datetime.now(UTC), status="DRAFT")
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
