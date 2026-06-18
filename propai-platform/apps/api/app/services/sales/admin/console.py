"""분양관리요약(관리자) 현장별 통합 관리 콘솔 — 담당자·근태·계약·매출·수수료·방문·광고·회계 집계.

'같이 또 따로': 시행사/관리자가 보유 현장 전체(포트폴리오)와 현장 단위 상세를 모두 본다.
기존 자산(org/contracts/commission/mh_visitors/attendance/ad)을 집계하고, 신규 회계 원장
(sales_site_accounting: 인건비/경비/공과금/광고비/기타)으로 현장별 손익을 산출한다.
가짜값 금지: 데이터 없으면 0/빈값으로 정직 표기.
"""
from __future__ import annotations

import contextlib
import logging
import re
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_ENTRY_TYPES = {"LABOR": "인건비", "EXPENSE": "경비", "UTILITY": "공과금", "AD": "광고비", "ETC": "기타"}

# 귀속월(ym) 형식 검증: 정확히 'YYYY-MM' 이고 월은 01~12 만 허용한다.
# 비정상 ym(예 2026-13·2026/06·2026-6)은 유니크키 분기(uq_site_acct_site_ym_type)를
# 우회해 멱등을 깨뜨릴 수 있으므로 입력 단계에서 차단한다(은폐 금지=ValueError).
_YM_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _validate_ym(ym: str) -> str:
    """'YYYY-MM'(월 01~12) 정규식 검증. 통과 시 원문 반환, 아니면 ValueError.

    멱등 귀속키/월 경계 계산의 단일 진입 검증점. actions.py·add_accounting_entry·
    _month_bounds 가 모두 이 함수를 거쳐 비정규 ym 우회를 차단한다.
    """
    if not isinstance(ym, str) or not _YM_RE.match(ym):
        raise ValueError("ym 형식 오류: 'YYYY-MM'(월 01~12)이어야 합니다(예: 2026-06).")
    return ym

# 테이블/컬럼 미존재 PostgreSQL SQLSTATE(asyncpg). 이것만 '정상 0' 으로 본다.
# 42P01=undefined_table, 42703=undefined_column. 그 외 DB 오류는 은폐 금지.
_MISSING_OBJECT_SQLSTATES = frozenset({"42P01", "42703"})

# ── 런타임 DDL race 제거용 advisory-lock 키(임의 상수, 충돌 회피용 고유값) ──────
# 정본은 Alembic 032_sales_admin_accounting. 마이그레이션 미적용 환경(개발/신규배포)
# 에서만 부팅 안전망으로 동작하며, 동시 부팅 시 advisory-lock 으로 중복 DDL race 를 제거한다.
_LOCK_ACCT = 880421001
_LOCK_WAGE = 880421002

_ACCT_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_site_accounting ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  site_id uuid NOT NULL,"
    "  entry_type varchar(12) NOT NULL,"          # LABOR/EXPENSE/UTILITY/AD/ETC
    "  amount numeric(16,0) NOT NULL,"
    "  memo text,"
    "  entry_date date NOT NULL DEFAULT current_date,"
    "  ym varchar(7),"                            # 자동전기 귀속월 'YYYY-MM'(수기 전기는 NULL)
    "  created_by uuid,"
    "  created_at timestamptz NOT NULL DEFAULT now()"
    ")"
)


async def _ensure_acct(db: AsyncSession) -> None:
    """sales_site_accounting 멱등 보장(부팅 안전망). advisory-lock 으로 동시부팅 race 제거.

    정본은 Alembic 032_sales_admin_accounting. 여기서는 마이그레이션 미적용 환경 대비
    CREATE/ALTER IF NOT EXISTS 만 수행한다(파괴적 변경 없음).
    """
    # advisory-lock: 트랜잭션 종료(commit/rollback) 시 자동 해제(pg_advisory_xact_lock).
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_ACCT})
    await db.execute(text(_ACCT_DDL))
    # 기존(구버전) 테이블에 ym 컬럼 멱등 추가.
    await db.execute(text("ALTER TABLE sales_site_accounting ADD COLUMN IF NOT EXISTS ym varchar(7)"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_site_acct_site ON sales_site_accounting(site_id)"))
    # 자동전기 멱등 인덱스 — 동일 (site_id, ym, entry_type) 중복 차단. ym NULL(수기)은 미적용.
    await db.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_site_acct_site_ym_type "
        "ON sales_site_accounting (site_id, ym, entry_type) WHERE ym IS NOT NULL"))
    await db.commit()


async def add_accounting_entry(db: AsyncSession, site_id, entry_type: str, amount: int,
                               memo: str | None, entry_date: str | None, by,
                               ym: str | None = None) -> dict[str, Any]:
    """현장 회계 전기. ym(귀속월 'YYYY-MM') 지정 시 (site_id, ym, entry_type) 멱등 —
    동일 월·동일 항목 자동전기를 ON CONFLICT 로 한 번만 기록(중복전기 차단)."""
    et = (entry_type or "").upper()
    if et not in _ENTRY_TYPES or int(amount) <= 0:
        raise ValueError("entry_type(LABOR/EXPENSE/UTILITY/AD/ETC)·amount(양수) 필요")
    if ym is not None:
        # 멱등 귀속키로 쓰이는 ym 은 반드시 'YYYY-MM'(월 01~12)이어야 한다.
        # 비정규 ym 은 부분 유니크 인덱스 분기를 우회해 중복전기를 허용하므로 차단.
        _validate_ym(ym)
    await _ensure_acct(db)
    # asyncpg는 date 컬럼 파라미터에 문자열을 받으면 toordinal 오류 → date 객체로 변환(없으면 NULL→오늘).
    ed = date.fromisoformat(entry_date) if entry_date else None
    params = {"s": str(site_id), "t": et, "a": int(amount), "m": memo, "d": ed,
              "u": str(by) if by else None, "ym": ym}
    if ym:
        # 멱등 전기: 부분 유니크 인덱스 uq_site_acct_site_ym_type 와 정합. 이미 있으면 무시.
        res = await db.execute(text(
            "INSERT INTO sales_site_accounting (site_id, entry_type, amount, memo, entry_date, created_by, ym) "
            "VALUES (:s,:t,:a,:m,COALESCE(:d, current_date),:u,:ym) "
            "ON CONFLICT (site_id, ym, entry_type) WHERE ym IS NOT NULL DO NOTHING"), params)
        await db.commit()
        inserted = (res.rowcount or 0) > 0
        return {"ok": True, "entry_type": et, "amount": int(amount), "ym": ym, "inserted": inserted,
                "duplicate": not inserted}
    # 수기 전기(ym 없음): 멱등 미적용 — 사람이 의도적으로 같은 항목을 여러 번 기록 가능.
    await db.execute(text(
        "INSERT INTO sales_site_accounting (site_id, entry_type, amount, memo, entry_date, created_by, ym) "
        "VALUES (:s,:t,:a,:m,COALESCE(:d, current_date),:u, NULL)"), params)
    await db.commit()
    return {"ok": True, "entry_type": et, "amount": int(amount)}


async def _cost_by_type(db: AsyncSession, site_id) -> dict[str, int]:
    await _ensure_acct(db)
    rows = (await db.execute(text(
        "SELECT entry_type, COALESCE(SUM(amount),0) FROM sales_site_accounting WHERE site_id=:s GROUP BY entry_type"),
        {"s": str(site_id)})).all()
    return {t: int(a) for t, a in rows}


def _missing_object_sqlstate(exc: BaseException) -> str | None:
    """예외가 '테이블/컬럼 미존재'(42P01/42703)면 해당 SQLSTATE, 아니면 None.

    asyncpg 의 원본 예외는 SQLAlchemy DBAPIError.orig 에 래핑된다. orig.sqlstate
    (또는 pgcode)로 분류한다. 이 두 코드만 '정상 0'(아직 안 만든 테이블) 으로 본다.
    """
    orig = getattr(exc, "orig", None) or exc
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if code in _MISSING_OBJECT_SQLSTATES:
        return code
    return None


async def _scalar(db: AsyncSession, sql: str, **p) -> int:
    """단일 스칼라 집계. 테이블/컬럼 미존재(42P01/42703)만 0 폴백.

    그 외 실쿼리 오류(권한·문법·연결·데이터)는 분류 로깅 후 전파한다 —
    오류를 0 으로 은폐하면 'revenue=0원' 오판으로 이어지므로 절대 흡수하지 않는다.
    """
    try:
        r = (await db.execute(text(sql), p)).first()
        return int(r[0] or 0) if r else 0
    except DBAPIError as e:
        # 트랜잭션 오염 방지를 위해 먼저 롤백(미존재/전파 공통). 롤백 자체 실패는 무시.
        with contextlib.suppress(Exception):
            await db.rollback()
        code = _missing_object_sqlstate(e)
        if code is not None:
            # 정상 0: 아직 생성되지 않은 테이블/컬럼(예: 회계 원장 미생성 환경).
            logger.debug("_scalar 미존재객체(%s) → 0 폴백: %s", code, sql.split(" FROM ")[-1][:80])
            return 0
        # 실오류는 은폐 금지 — 분류 로깅 후 호출자에게 전파.
        logger.error("_scalar DB오류(전파): sql=%s err=%s", sql[:120], str(e)[:200])
        raise


async def site_management_detail(db: AsyncSession, site_id) -> dict[str, Any]:
    """현장 1곳의 통합 관리 지표 — 담당자·근태·계약·매출·수수료·방문·광고·회계·손익."""
    s = str(site_id)
    today = datetime.now(UTC).date()  # date 객체(asyncpg 바인딩 안전)
    staff = await _scalar(db,
        "SELECT count(*) FROM sales_org_nodes WHERE site_id=:s AND user_id IS NOT NULL AND deleted_at IS NULL", s=s)
    contracts = await _scalar(db,
        "SELECT count(*) FROM sales_contracts_ext WHERE site_id=:s AND status='ACTIVE'", s=s)
    revenue = await _scalar(db,
        "SELECT COALESCE(SUM(total_price),0) FROM sales_contracts_ext WHERE site_id=:s AND status='ACTIVE'", s=s)
    # 수수료 이벤트엔 site_id 가 없으므로 계약(contract_ext_id)을 경유해 현장을 잇는다.
    commission = await _scalar(db,
        "SELECT COALESCE(SUM(sp.amount),0) FROM sales_commission_splits sp "
        "JOIN sales_commission_events e ON e.id=sp.event_id "
        "JOIN sales_contracts_ext c ON c.id=e.contract_ext_id WHERE c.site_id=:s", s=s)
    visitors = await _scalar(db, "SELECT count(*) FROM mh_visitors WHERE site_id=:s", s=s)
    attend_today = await _scalar(db,
        "SELECT count(*) FROM sales_staff_attendance WHERE site_id=:s AND check_in::date=:d", s=s, d=today)
    ad_budget = await _scalar(db, "SELECT COALESCE(SUM(budget),0) FROM sales_ad_campaigns WHERE site_id=:s", s=s)

    # 실수납액(현금흐름 매출) — sales_payments(입금 기록·대사 원장)에서 대사완료(matched=true)
    # 입금만 인정. 미수금은 매출로 잡지 않는다(현금주의). 원장 미존재 시 _scalar 가 0 폴백.
    cash_collected = await _scalar(db,
        "SELECT COALESCE(SUM(amount),0) FROM sales_payments WHERE site_id=:s AND matched=true", s=s)

    cost = await _cost_by_type(db, site_id)
    cost_total = sum(cost.values())
    # [회계손익=발생주의/수익인식] 계약 총액(ACTIVE)을 매출로 인식 − 회계비용 − 수수료배분.
    #   주의: 계약총액 즉시인식은 미수금까지 매출로 잡아 과대계상될 수 있다(K-IFRS 1115 는
    #   '이행의무 충족 시점' 인식 — 분양은 통상 진행기준/인도시점). 아래 cash_flow 와 분리 표기.
    profit = revenue - cost_total - commission
    # [현금흐름손익=현금주의] 실수납액 − 회계비용 − 수수료배분. 실제 들어온 돈 기준.
    cash_profit = cash_collected - cost_total - commission
    # ── 실수납·인식매출 차액 정밀화(단순 등치 제거) ─────────────────────────────
    #   두 값은 출처가 다르다: revenue_recognized=계약총액(sales_contracts_ext.total_price,
    #   발생주의 즉시인식), cash_collected=실수납(sales_payments.matched 입금).
    #   ① 미수금(receivable) = 인식매출 − 실수납 (양수일 때) — 인식했으나 아직 못 받은 돈.
    #   ② 선수금(deferred_revenue) = 실수납 − 인식매출 (양수일 때) — 받았으나 아직 인식 안 한 돈.
    #   현재 모델은 계약총액 즉시인식이라 통상 미수금이 발생하고 선수금은 0 에 수렴한다.
    #   (인도시점/진행기준 인식으로 정밀화하면 선수금이 실재화 — 그때 동일 식으로 자동 반영됨.)
    receivable = max(revenue - cash_collected, 0)
    deferred_revenue = max(cash_collected - revenue, 0)
    # 검산 정합: 인식매출 = 실수납 − 선수금 + 미수금 (출처 상이 차액의 항등식).
    reconcile_ok = (revenue == cash_collected - deferred_revenue + receivable)
    by_type_list = [{"type": t, "label": _ENTRY_TYPES.get(t, t), "amount": a} for t, a in sorted(cost.items())]
    return {
        "site_id": s,
        "staff_assigned": staff,
        "contracts": contracts,
        "revenue": revenue,
        "commission": commission,
        "visitors": visitors,
        "attendance_today": attend_today,
        "ad_budget": ad_budget,
        "accounting": {
            "by_type": by_type_list,
            "cost_total": cost_total,
        },
        # 하위호환: profit_estimate=회계손익(발생주의). 기존 화면/롤업이 참조.
        "profit_estimate": profit,
        # ── 손익 2-뷰 명확 분리(은폐 금지) ──
        "cash_flow": {
            # 현금흐름 손익: 실제 수납된 돈 기준. 납입원장 없으면 cash_collected=0(정직).
            "cash_collected": cash_collected,
            "cost_total": cost_total,
            "commission": commission,
            "profit": cash_profit,
            "note": "현금흐름 손익 = 실수납액(대사완료 입금) − 회계비용 − 수수료배분. 납입원장 미기록 시 0.",
        },
        "accrual": {
            # 회계 손익: 계약 매출(발생주의) 기준. 미수금 포함 과대계상 주의.
            "revenue_recognized": revenue,
            "cost_total": cost_total,
            "commission": commission,
            "profit": profit,
            # 미수금 = 인식매출 − 실수납(양수). 발생주의 매출 중 아직 못 받은 부분.
            "receivable": receivable,
            "note": ("회계 손익 = 계약 매출(발생주의) − 회계비용 − 수수료배분. "
                     "계약총액 즉시인식이라 미수금(receivable)까지 매출 반영(과대계상 가능)."),
        },
        # 선수금(부채): 실수납 − 인식매출(양수). 받았으나 아직 인식 안 한 돈(K-IFRS 1115 선수금).
        #   현재 계약총액 즉시인식 모델에선 통상 0(미수금 측이 양수). 단순 등치(=실수납) 아님.
        "deferred_revenue": deferred_revenue,
        # 검산 정합: 인식매출 = 실수납 − 선수금 + 미수금. 출처 상이(계약/입금) 차액의 항등식 검증.
        "reconciliation": {
            "revenue_recognized": revenue,
            "cash_collected": cash_collected,
            "deferred_revenue": deferred_revenue,
            "receivable": receivable,
            "balanced": reconcile_ok,
            "note": ("검산: 인식매출 = 실수납 − 선수금 + 미수금. "
                     "revenue_recognized(계약총액)와 cash_collected(실수납)는 출처가 달라, "
                     "차액은 선수금/미수금으로 분해되어 정합한다."),
        },
        "note": ("손익은 두 관점으로 분리: ①현금흐름(cash_flow, 실수납 기준) "
                 "②회계/발생주의(accrual, 계약매출 기준). profit_estimate=accrual.profit(하위호환). "
                 "K-IFRS 1115상 분양 매출은 이행의무 충족(진행/인도) 시 인식 — "
                 "계약총액 즉시인식은 과대계상 소지가 있어 "
                 "실수납(cash_flow)·선수금(deferred_revenue)·미수금(accrual.receivable)을 함께 표기."),
    }


# ── 급여관리(근태×단가 자동산정 + 원천징수·4대보험 자동공제) ──────────────────
_WAGE_TYPES = {"DAILY": "일급", "HOURLY": "시급", "MONTHLY": "월급"}
# 세무 모드: 사업소득(영업직 위촉)=3.3% 원천징수 / 근로소득(정규)=4대보험+간이세액 / NONE=공제없음(총액)
_TAX_MODES = {"FREELANCE": "사업소득3.3%", "EMPLOYEE": "근로소득4대보험", "NONE": "공제없음"}

# 법정 공제율(근로자 부담분, 2025년 기준 — 요율 변경 시 아래 상수만 조정).
# ★출처/면책: 4대보험 요율은 각 공단 고시 기준(국민연금공단·건강보험공단·고용노동부),
#   사업소득 3.3%(소득세 3% + 지방소득세 0.3%)는 소득세법 원천징수 규정.
#   근로소득세는 법정 확정액이 아니라 간이세액표 '추정'(_est_income_tax 참조).
#   상수는 매년 고시로 바뀌므로 운영 시 최신 요율로 갱신해야 함(여기 값은 2025년 기준).
_R_PENSION = 0.045          # 국민연금 4.5%(근로자부담분, 국민연금공단 고시)
_PENSION_CAP = 6170000      # 국민연금 기준소득월액 상한(월, 2025년 적용분)
_R_HEALTH = 0.03545         # 건강보험 3.545%(근로자부담분, 건강보험공단 고시)
_R_LTC_OF_HEALTH = 0.1295   # 장기요양 = 건강보험료 × 12.95%(2025년 요율)
_R_EMPLOY = 0.009           # 고용보험 0.9%(근로자부담분, 고용노동부 고시)
_R_FREELANCE_IT = 0.03      # 사업소득 원천 소득세 3%(소득세법)
_R_LOCAL_OF_IT = 0.10       # 지방소득세 = 소득세 × 10%(지방세법)

_WAGE_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_staff_wage ("
    "  staff_id uuid PRIMARY KEY,"
    "  site_id uuid NOT NULL,"
    "  wage_type varchar(10) NOT NULL DEFAULT 'DAILY',"   # DAILY/HOURLY/MONTHLY
    "  base_wage numeric(14,0) NOT NULL DEFAULT 0,"
    "  tax_mode varchar(12) NOT NULL DEFAULT 'FREELANCE',"  # FREELANCE/EMPLOYEE/NONE
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)


async def _ensure_wage(db: AsyncSession) -> None:
    """sales_staff_wage 멱등 보장(부팅 안전망). advisory-lock 으로 동시부팅 race 제거.

    정본은 Alembic 032_sales_admin_accounting. 마이그레이션 미적용 환경 대비
    CREATE/ALTER IF NOT EXISTS 만 수행한다(파괴적 변경 없음).
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_WAGE})
    await db.execute(text(_WAGE_DDL))
    # 기존 테이블에 tax_mode 컬럼 멱등 추가.
    await db.execute(text(
        "ALTER TABLE sales_staff_wage ADD COLUMN IF NOT EXISTS tax_mode "
        "varchar(12) NOT NULL DEFAULT 'FREELANCE'"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_staff_wage_site ON sales_staff_wage(site_id)"))
    await db.commit()


def _est_income_tax(gross: int) -> int:
    """근로소득세 월 간이세액 '추정'(1인 가구·부양가족 0인 가정).

    ★면책: 이 값은 법적 원천징수액이 아니라 '추정치'다. 실제 원천징수액은
      국세청 '근로소득 간이세액표'(소득세법 시행령 제194조, 별표)와 부양가족 수·
      비과세소득·공제항목에 따라 달라지며, 연말정산으로 확정된다.
      여기서는 부양가족·세액공제 미반영(보수적 과대 방지) 구간별 실효율 '근사'만 적용한다.
    출처/근거: 국세청 간이세액표(매년 고시) 구조를 단순 구간 실효율로 근사. 상수는 추정용.
    """
    # (상한금액, 실효율 근사) — 월 총급여 구간. 마지막은 8,000,000원 초과 구간(rate=0.150).
    bands = [(1_060_000, 0.0), (2_000_000, 0.008), (3_000_000, 0.020),
             (4_000_000, 0.040), (6_000_000, 0.070), (8_000_000, 0.100)]
    rate = 0.150
    for ceil, r in bands:
        if gross <= ceil:
            rate = r
            break
    return round(gross * rate)


def _deductions(gross: int, mode: str) -> dict[str, Any]:
    """총급여 → 원천징수·4대보험 자동공제 + 실수령액."""
    g = int(gross)
    if g <= 0:
        return {"items": [], "total_deduction": 0, "net": 0}
    items: list[dict[str, Any]] = []
    if mode == "FREELANCE":
        it = round(g * _R_FREELANCE_IT)
        lit = round(it * _R_LOCAL_OF_IT)
        items = [{"key": "income_tax", "label": "원천소득세(3%)", "amount": it},
                 {"key": "local_tax", "label": "지방소득세(0.3%)", "amount": lit}]
    elif mode == "EMPLOYEE":
        np = round(min(g, _PENSION_CAP) * _R_PENSION)
        hi = round(g * _R_HEALTH)
        ltc = round(hi * _R_LTC_OF_HEALTH)
        ei = round(g * _R_EMPLOY)
        it = _est_income_tax(g)
        lit = round(it * _R_LOCAL_OF_IT)
        items = [{"key": "pension", "label": "국민연금(4.5%)", "amount": np},
                 {"key": "health", "label": "건강보험(3.545%)", "amount": hi},
                 {"key": "ltc", "label": "장기요양(건강×12.95%)", "amount": ltc},
                 {"key": "employ", "label": "고용보험(0.9%)", "amount": ei},
                 {"key": "income_tax", "label": "근로소득세(간이추정)", "amount": it},
                 {"key": "local_tax", "label": "지방소득세(소득세×10%)", "amount": lit}]
    total = sum(int(i["amount"]) for i in items)
    return {"items": items, "total_deduction": total, "net": g - total}


def _month_bounds(ym: str) -> tuple[date, date]:
    """'YYYY-MM' → (이달1일, 다음달1일) date 객체(asyncpg 바인딩 안전).

    먼저 형식 검증(_validate_ym): 비정규 ym(2026-13·2026/06·2026-6)은 ValueError 로 차단.
    """
    _validate_ym(ym)
    y, m = int(ym[:4]), int(ym[5:7])
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return date(y, m, 1), date(ny, nm, 1)


async def set_staff_wage(db: AsyncSession, site_id, staff_id, wage_type: str, base_wage: int,
                         tax_mode: str = "FREELANCE") -> dict[str, Any]:
    wt = (wage_type or "").upper()
    tm = (tax_mode or "FREELANCE").upper()
    if wt not in _WAGE_TYPES or int(base_wage) < 0 or tm not in _TAX_MODES:
        raise ValueError("wage_type(DAILY/HOURLY/MONTHLY)·base_wage(0 이상)·tax_mode(FREELANCE/EMPLOYEE/NONE) 필요")
    await _ensure_wage(db)
    await db.execute(text(
        "INSERT INTO sales_staff_wage (staff_id, site_id, wage_type, base_wage, tax_mode, updated_at) "
        "VALUES (:st,:s,:wt,:w,:tm, now()) "
        "ON CONFLICT (staff_id) DO UPDATE SET wage_type=:wt, base_wage=:w, tax_mode=:tm, updated_at=now()"),
        {"st": str(staff_id), "s": str(site_id), "wt": wt, "w": int(base_wage), "tm": tm})
    await db.commit()
    return {"ok": True, "staff_id": str(staff_id), "wage_type": wt, "base_wage": int(base_wage), "tax_mode": tm}


async def compute_payroll(db: AsyncSession, site_id, ym: str) -> dict[str, Any]:
    """현장 직원별 급여 자동산정 — 근태(출근일수·근무분) × 단가. 회계 인건비 후보."""
    await _ensure_wage(db)
    start, end = _month_bounds(ym)
    s = str(site_id)
    rows = (await db.execute(text(
        "SELECT s.id, s.name, s.position, "
        "  count(distinct a.check_in::date) AS days, "
        "  COALESCE(sum(a.work_minutes),0) AS minutes "
        "FROM sales_staff s "
        "LEFT JOIN sales_staff_attendance a ON a.staff_id=s.id "
        "  AND a.check_in >= :start AND a.check_in < :end "
        "WHERE s.site_id=:s AND s.deleted_at IS NULL AND s.status='ACTIVE' "
        "GROUP BY s.id, s.name, s.position ORDER BY s.name"),
        {"s": s, "start": start, "end": end})).all()
    wages = {str(k): (wt, int(w), tm) for k, wt, w, tm in (await db.execute(text(
        "SELECT staff_id, wage_type, base_wage, tax_mode FROM sales_staff_wage WHERE site_id=:s"), {"s": s})).all()}
    staff = []
    total_gross = total_ded = total_net = 0
    for sid, name, pos, days, minutes in rows:
        wt, base, tm = wages.get(str(sid), ("DAILY", 0, "FREELANCE"))
        hours = round(int(minutes) / 60)
        if wt == "HOURLY":
            gross = hours * base
        elif wt == "MONTHLY":
            gross = base if int(days) > 0 else 0  # 무출근이면 미지급
        else:  # DAILY
            gross = int(days) * base
        ded = _deductions(gross, tm)
        total_gross += gross
        total_ded += ded["total_deduction"]
        total_net += ded["net"]
        staff.append({
            "staff_id": str(sid), "name": name or "-", "position": pos,
            "days": int(days), "hours": hours,
            "wage_type": wt, "wage_label": _WAGE_TYPES.get(wt, wt), "base_wage": base,
            "tax_mode": tm, "tax_mode_label": _TAX_MODES.get(tm, tm),
            "gross": gross, "amount": gross,  # amount=총급여(하위호환)
            "deductions": ded["items"], "total_deduction": ded["total_deduction"], "net": ded["net"],
            "wage_set": str(sid) in wages,
        })
    return {"year_month": ym, "staff": staff, "headcount": len(staff),
            "total_payroll": total_gross,  # 총급여(하위호환)
            "total_gross": total_gross, "total_deduction": total_ded, "total_net": total_net,
            "note": ("급여=근태×단가. 공제: 사업소득3.3% 또는 "
                     "근로소득 4대보험(국민연금4.5%·건강3.545%·장기요양·고용0.9%)+근로소득세(간이세액 추정). "
                     "정확 소득세는 국세청 간이세액표/연말정산 기준.")}


async def post_payroll_to_accounting(db: AsyncSession, site_id, ym: str, by) -> dict[str, Any]:
    """산정 급여 총액을 회계 인건비(LABOR)로 자동전기 — 동일 월 중복전기 방지(멱등).

    멱등 보장은 DB 부분 유니크 인덱스 uq_site_acct_site_ym_type (site_id, ym, entry_type)
    + ON CONFLICT DO NOTHING(add_accounting_entry, ym 지정 경로)으로 처리한다.
    (이전의 memo 문자열 매칭 사전체크는 동시 전기 race 에 취약 → 원자적 ON CONFLICT 로 대체.)
    """
    pr = await compute_payroll(db, site_id, ym)
    total = int(pr["total_payroll"])
    if total <= 0:
        return {"ok": False, "reason": "산정 급여가 0원입니다(단가·근태 확인)."}
    memo = f"급여 {ym} 자동전기"
    # ym 지정 → (site_id, ym, 'LABOR') 멱등. 이미 전기됐으면 inserted=False(중복).
    res = await add_accounting_entry(db, site_id, "LABOR", total, memo, f"{ym}-01", by, ym=ym)
    if not res.get("inserted", True):
        return {"ok": False, "reason": f"{ym} 급여는 이미 전기되었습니다.", "total": total}
    return {"ok": True, "posted": total, "year_month": ym, "memo": memo}


# ── 광고집행 ROI(집행비 대비 집객·계약 효율) ─────────────────────────────────
async def ad_roi(db: AsyncSession, site_id) -> dict[str, Any]:
    """광고 집행비(예산/실집행) 대비 집객(방문·리드)·계약 효율 = 단가 산출."""
    s = str(site_id)
    budget = await _scalar(db, "SELECT COALESCE(SUM(budget),0) FROM sales_ad_campaigns WHERE site_id=:s", s=s)
    spend = await _scalar(db, "SELECT COALESCE(SUM(amount),0) FROM sales_ad_spend WHERE site_id=:s", s=s)
    leads = await _scalar(db, "SELECT count(*) FROM sales_ad_leads WHERE site_id=:s", s=s)
    visitors = await _scalar(db, "SELECT count(*) FROM mh_visitors WHERE site_id=:s", s=s)
    contracts = await _scalar(db, "SELECT count(*) FROM sales_contracts_ext WHERE site_id=:s AND status='ACTIVE'", s=s)
    eff = spend or budget  # 실집행 우선, 없으면 예산 기준
    return {
        "budget": budget, "spend": spend, "leads": leads, "visitors": visitors, "contracts": contracts,
        "cost_per_lead": round(eff / leads) if leads else 0,
        "cost_per_visitor": round(eff / visitors) if visitors else 0,
        "cost_per_contract": round(eff / contracts) if contracts else 0,
        "note": "단가=실집행비(없으면 예산)÷각 성과수. 광고 집행비는 회계 광고비(AD)로 전기 가능.",
    }
