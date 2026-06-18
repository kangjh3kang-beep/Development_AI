"""분양관리요약(관리자) 현장별 통합 관리 콘솔 — 담당자·근태·계약·매출·수수료·방문·광고·회계 집계.

'같이 또 따로': 시행사/관리자가 보유 현장 전체(포트폴리오)와 현장 단위 상세를 모두 본다.
기존 자산(org/contracts/commission/mh_visitors/attendance/ad)을 집계하고, 신규 회계 원장
(sales_site_accounting: 인건비/경비/공과금/광고비/기타)으로 현장별 손익을 산출한다.
가짜값 금지: 데이터 없으면 0/빈값으로 정직 표기.
"""
from __future__ import annotations

import asyncio
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

# ── 독립 대사(reconcile) 범위: '회차가 실재하는 계약단계' ────────────────────────
#   ★SSOT 확인(contract/service.py): contract.stage 상태기계는 RESERVED→SIGNED→CANCELLED
#     만 생성한다. sign_contract() 만이 분납 회차(sales_contract_installments)를 만들고
#     stage='SIGNED' 로 둔다. MIDDLE/BALANCE 는 contract.stage 가 아니라 '회차 종류'
#     (installment.kind, sign_contract 의 s["kind"]) 개념이며, stage 로 설정되는 코드 경로가
#     전혀 없다(모델 주석 'RESERVED/SIGNED/MIDDLE/BALANCE' 는 미실현 표기). 따라서 회차가
#     실재하는 단계는 'SIGNED' 하나뿐이라 그 범위로만 정렬해 대사한다(MIDDLE/BALANCE 를 넣으면
#     영구히 매치되지 않는 dead 분기). 향후 stage 에 중도금/잔금 전이가 '실제로' 추가되면
#     이 튜플에만 단계를 더하면 전체 대사 쿼리가 일괄 정합 확장된다(단일 변경점).
#   ※ f-string 리터럴 대신 모듈 상수 튜플 — 값은 전부 하드코딩 리터럴(외부입력 0)이라
#     SQL 주입 위험이 없고, IN 절은 _stage_in_clause() 로 1곳에서 안전 조립한다.
_RECONCILE_STAGES: tuple[str, ...] = ("SIGNED",)


def _stage_in_clause(stages: tuple[str, ...] = _RECONCILE_STAGES) -> str:
    """하드코딩 stage 리터럴 튜플 → SQL IN 절 문자열('SIGNED','MIDDLE',...). 외부입력 없음(주입無)."""
    return "(" + ",".join(f"'{st}'" for st in stages) + ")"

# 귀속월(ym) 형식 검증: 정확히 'YYYY-MM' 이고 월은 01~12 만 허용한다.
# 비정상 ym(예 2026-13·2026/06·2026-6)은 유니크키 분기(uq_site_acct_site_ym_type)를
# 우회해 멱등을 깨뜨릴 수 있으므로 입력 단계에서 차단한다(은폐 금지=ValueError).
# ★iter-5 회귀수정: 끝을 '$' 로 두면 후행 개행 1개('2026-06\n')를 허용한다(파이썬 정규식에서
#   '$'는 문자열 끝 '또는' 마지막 개행 직전에 매치). 그러면 '2026-06\n' 같은 값이 PASS 되어
#   부분 유니크키(uq_site_acct_site_ym_type)를 우회 → 멱등이 깨진다. 문자열 절대 끝만 매치하는
#   '\Z' 로 바꿔 후행 개행/공백을 전부 차단한다(아래는 re.fullmatch 로 처음~끝 강제도 병행).
_YM_RE = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


def _validate_ym(ym: str) -> str:
    """'YYYY-MM'(월 01~12) 정규식 검증. 통과 시 원문 반환, 아니면 ValueError.

    멱등 귀속키/월 경계 계산의 단일 진입 검증점. actions.py·add_accounting_entry·
    _month_bounds 가 모두 이 함수를 거쳐 비정규 ym 우회를 차단한다.
    ★iter-5: re.fullmatch 로 '문자열 처음~절대 끝' 전체 일치만 통과시킨다. 이로써
      '2026-06\\n'(후행 개행)·'2026-06 '(후행 공백)·' 2026-06'(선행 공백) 전부 REJECT 된다.
    """
    if not isinstance(ym, str) or not _YM_RE.fullmatch(ym):
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

# ── 프로세스 1회 게이트(읽기경로 DDL race 잔재 제거) ────────────────────────────
# iter-4: _ensure_acct/_ensure_wage 가 호출될 때마다 advisory-lock+CREATE/ALTER+commit 을
#   직렬 실행하던 것이 문제였다(특히 롤업이 N현장×_cost_by_type 마다 반복 → 직렬화 비용).
#   해결: 프로세스당 '최초 1회'만 실제 DDL 을 수행하고, 성공 후엔 즉시 반환(no-op)한다.
#   - 정본은 032 마이그레이션이므로 운영(마이그레이션 적용) 환경에선 DDL 자체가 IF NOT EXISTS
#     로 무변경이며, 게이트 덕분에 매 요청 advisory-lock/commit 비용도 사라진다.
#   - asyncio.Lock 으로 동시 첫 호출(코루틴 경합)도 1회로 합류시킨다(워커=단일 이벤트루프).
#   - 멀티프로세스 동시 부팅 race 는 기존 advisory-lock 이 그대로 막는다(게이트는 in-process).
#   읽기경로(_cost_by_type 등)에서는 보장 호출 자체를 제거했고, 쓰기경로만 1회 게이트를 거친다.
_acct_ready = False
_wage_ready = False
_acct_lock = asyncio.Lock()
_wage_lock = asyncio.Lock()

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
    """sales_site_accounting 멱등 보장(부팅 안전망) — 프로세스 1회만 실제 DDL 수행.

    정본은 Alembic 032_sales_admin_accounting. 여기서는 마이그레이션 미적용 환경 대비
    CREATE/ALTER IF NOT EXISTS 만 수행한다(파괴적 변경 없음).
    ★iter-4: 최초 1회 성공 후엔 즉시 반환(no-op) — 매 호출 advisory-lock/commit 직렬화 제거.
    쓰기경로(add_accounting_entry·post_payroll)에서만 호출하며, 읽기경로는 호출하지 않는다.
    """
    global _acct_ready
    if _acct_ready:  # 이미 보장됨 → DB 왕복 없이 즉시 반환.
        return
    async with _acct_lock:  # 동시 첫 호출(코루틴 경합)을 1회로 합류.
        if _acct_ready:
            return
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
        _acct_ready = True  # 성공 시에만 게이트 닫음(실패 시 다음 쓰기 호출이 재시도).


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
    """현장 비용 항목별 합계 — 순수 읽기경로(DDL 보장 호출 안 함).

    ★iter-4: 여기서 _ensure_acct 를 호출하면 롤업 N현장마다 advisory-lock+DDL+commit 이
      직렬 반복된다. 테이블 미존재(42P01)는 아래 _scalar 와 동일 정책으로 graceful 0 폴백한다
      (DBAPIError→미존재면 빈 dict). 테이블 생성 책임은 쓰기경로(_ensure_acct)·032 마이그레이션.
    """
    try:
        rows = (await db.execute(text(
            "SELECT entry_type, COALESCE(SUM(amount),0) FROM sales_site_accounting "
            "WHERE site_id=:s GROUP BY entry_type"),
            {"s": str(site_id)})).all()
    except DBAPIError as e:
        # 트랜잭션 오염 방지 롤백(미존재/전파 공통). 롤백 자체 실패는 무시.
        with contextlib.suppress(Exception):
            await db.rollback()
        code = _missing_object_sqlstate(e)
        if code is not None:
            # 정상 0: 회계 원장 미생성 환경(아직 쓰기 1건도 없음). 빈 dict.
            logger.debug("_cost_by_type 미존재객체(%s) → 빈 dict 폴백", code)
            return {}
        # 실오류는 은폐 금지 — 분류 로깅 후 호출자에게 전파.
        logger.error("_cost_by_type DB오류(전파): err=%s", str(e)[:200])
        raise
    return {t: int(a) for t, a in rows}


async def _load_wages(db: AsyncSession, site_id) -> dict[str, tuple[str, int, str]]:
    """현장 직원 단가표 읽기 — 순수 읽기경로(DDL 보장 호출 안 함).

    ★iter-5(작업5): compute_payroll(GET /payroll)이 _ensure_wage 로 읽기경로에서 DDL을
      돌리던 것을 제거하고, _cost_by_type 와 동일한 graceful 폴백으로 강등한다.
      sales_staff_wage 미존재(42P01)/컬럼 미존재(42703)는 '단가 미설정'(정상 0) → 빈 dict.
      → 단가 미설정 직원은 base_wage=0 으로 산정(무급, 정직). 테이블 생성 책임은
      쓰기경로(set_staff_wage→_ensure_wage)·032 마이그레이션이 진다(읽기경로 DDL 완전강등).
      그 외 실오류(권한·연결)는 은폐 금지 — 분류 로깅 후 전파.
    """
    try:
        rows = (await db.execute(text(
            "SELECT staff_id, wage_type, base_wage, tax_mode FROM sales_staff_wage WHERE site_id=:s"),
            {"s": str(site_id)})).all()
    except DBAPIError as e:
        with contextlib.suppress(Exception):
            await db.rollback()
        code = _missing_object_sqlstate(e)
        if code is not None:
            logger.debug("_load_wages 미존재객체(%s) → 빈 dict 폴백(단가 미설정)", code)
            return {}
        logger.error("_load_wages DB오류(전파): err=%s", str(e)[:200])
        raise
    return {str(k): (wt, int(w), tm) for k, wt, w, tm in rows}


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


def _reconcile(revenue_signed: int, scheduled_total: int, installment_paid: int,
               installment_count: int, ratio_invalid_count: int) -> dict[str, Any]:
    """독립 대사(실불일치 탐지) — 순수 로직(DB 무관, 단위테스트 대상).

    ★iter-5 회귀수정 — 두 가지를 분리/완화한다.
      (회귀1·거짓경보) 회차 약정금은 amount=int(round(total_price×ratio))로 '반올림'되어
        저장된다. 회차 N개면 합계에 최대 약 N/2 원의 반올림 잔차가 생겨
        약정총액(scheduled_total)이 계약총액(revenue_signed)과 몇 원 어긋날 수 있다.
        엄격 '!=' 비교는 이 정상 잔차를 거짓 불일치(discrepancy·balanced=False)로 올린다.
      (계약결함 분리) 약정 ratio 합이 1.0 이 아니어서 회차합이 계약총액과 '크게' 어긋나는
        계약(tol 초과)은 진짜 데이터 결함이다. 이건 별도 규칙 schedule_ratio_invalid 로
        분리 제시해 운영자가 '반올림오차(무시 가능)'와 '계약결함(점검 필요)'을 구분하게 한다.

    허용오차 tol = (installment_count + 1) // 2 + 1  (= ceil(N/2)+1, 회차 0개면 1=eps).
      누적 반올림 잔차의 수학적 상한(±N/2)은 흡수하되 그 이상은 실불일치로 본다(탐지력↑).
      ①약정-계약 차이(schedule_vs_contract)와 ③수납-약정 초과(paid_exceeds_schedule) 양쪽에
      대칭으로 같은 tol 을 적용한다(반올림 비대칭으로 인한 거짓경보 제거).

    인자:
      revenue_signed     : SIGNED(회차 실생성) 계약의 계약총액 합(독립대사 비교 기준).
      scheduled_total    : 같은 범위 회차 약정금 합(독립 제3 출처).
      installment_paid   : 같은 범위 회차 실수납 합(matched 입금).
      installment_count  : 같은 범위 회차 행 수(반올림 허용오차 tol 산정용).
      ratio_invalid_count: 계약별 회차합이 자기 계약총액과 tol 초과로 어긋난 '결함 계약' 수.

    반환: balanced, discrepancies[], tolerance.
      balanced 의미:
        None  = '서명매출도 0(revenue_signed==0)' → 서명계약 자체가 없어 판정보류(N/A, 거짓안심 금지).
        False = '약정표 누락(scheduled_total==0)인데 서명매출>0'(schedule_missing_for_signed) 또는
                약정-계약/비율/수납초과 불일치(discrepancies 적발).
        True  = 독립 출처(약정표) 존재 + tol 흡수 후 불일치 0(대사 통과).
    """
    # 허용오차 tol — 회차 약정금은 round(계약총액×비율) 저장이라 회차마다 ±0.5원 반올림 잔차가
    #   누적된다. N회차면 최악 누적 잔차는 ±N/2 원이므로 ceil(N/2)+1 이 수학적으로 충분한 상한이다.
    #   ★iter-6 타이트화(탐지력↑): 종전 tol=max(N, eps)는 다회차(예 1000회) 계약에서 최대 ±1000원의
    #     '진짜 불일치'까지 흡수해 탐지를 무디게 했다. ceil(N/2)+1 로 절반 수준으로 좁혀 반올림
    #     잔차(±N/2)는 그대로 흡수하면서 그 이상의 실불일치 탐지력을 높인다. 회차 0개여도 +1 로
    #     최소 1원 잔차(eps)는 보장(정수 반올림 하한).
    tol = (installment_count + 1) // 2 + 1
    schedule_present = scheduled_total > 0
    discrepancies: list[dict[str, Any]] = []
    if not schedule_present:
        # 독립 출처(분납 약정표) 부재.
        #   ★iter-6: 두 경우를 분리한다(조용한 과소대사 승격).
        #     ① 서명매출도 0(revenue_signed==0) → 아직 서명계약 자체가 없음 → 진짜 판정보류(None).
        #     ② 서명매출>0 인데 약정표가 비었음(scheduled_total==0) → '서명했는데 분납약정표 미생성'
        #        이라는 실데이터 결함이다. 이를 None('N/A')로 숨기면 약정표 누락이 정합처럼 보여
        #        조용한 과소대사가 된다. 그래서 schedule_missing_for_signed 경고로 승격(balanced=False).
        if revenue_signed > 0:
            discrepancies.append({
                "key": "schedule_missing_for_signed",
                "detail": f"SIGNED 계약총액({revenue_signed:,}) 존재하나 분납 약정표가 비어 있음 "
                          f"(약정표 미생성 — 독립 대사 불가, 회차 생성 점검 필요)",
                "delta": revenue_signed,
            })
            return {"balanced": False, "discrepancies": discrepancies, "tolerance": tol}
        # 서명매출도 0 → 독립 출처 부재로 판정 보류(미탐지를 '정합'으로 위장 금지).
        return {"balanced": None, "discrepancies": [], "tolerance": tol}
    delta_sc = scheduled_total - revenue_signed
    # ① 약정총액 vs 계약총액(SIGNED) — 반올림 잔차(±tol)는 흡수, 그 이상만 불일치로 본다.
    if abs(delta_sc) > tol:
        discrepancies.append({
            "key": "schedule_vs_contract",
            "detail": f"분납 약정총액({scheduled_total:,}) ≠ SIGNED 계약총액({revenue_signed:,}) "
                      f"(차이 {delta_sc:+,}, 허용오차 ±{tol:,})",
            "delta": delta_sc,
        })
    # ② 약정 ratio 합 결함(계약별 회차합이 자기 계약총액과 tol 초과로 어긋난 계약 존재).
    #    '반올림오차'와 구분되는 진짜 계약결함 — 별도 규칙으로 분리 제시.
    if ratio_invalid_count > 0:
        discrepancies.append({
            "key": "schedule_ratio_invalid",
            "detail": f"분납 약정 비율 합≠100% 의심 계약 {ratio_invalid_count}건 "
                      f"(회차합이 계약총액과 허용오차 초과로 불일치 — 계약결함)",
            "count": ratio_invalid_count,
        })
    # ③ 회차 실수납이 약정총액 초과(중복/오대사 신호).
    #   ★iter-6 회귀수정(거짓경보 비대칭): 약정총액(scheduled_total)은 Σround(계약총액×비율)이라
    #     반올림으로 '하향'(최대 N원 부족)될 수 있다. 반면 완납 계약의 회차 실수납(installment_paid)은
    #     실제 입금액(보통 계약총액=Σ원래금액)이라 scheduled_total 보다 몇 원 클 수 있다.
    #     엄격 '>' 비교는 이 정상 반올림 잔차를 거짓 적발(paid_exceeds_schedule)로 올린다.
    #     →  ① 약정총액(±tol) 흡수와 대칭이 되도록 동일 tol 을 적용한다(그 이상만 진짜 초과로 본다).
    if installment_paid > scheduled_total + tol:
        discrepancies.append({
            "key": "paid_exceeds_schedule",
            "detail": f"회차 실수납({installment_paid:,}) > 약정총액({scheduled_total:,}, 허용오차 +{tol:,})",
            "delta": installment_paid - scheduled_total,
        })
    return {"balanced": len(discrepancies) == 0, "discrepancies": discrepancies, "tolerance": tol}


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
    # commission(발생주의 수수료) = 배분(split) 합. accrual.profit 에 쓴다(아직 미지급분 포함).
    commission = await _scalar(db,
        "SELECT COALESCE(SUM(sp.amount),0) FROM sales_commission_splits sp "
        "JOIN sales_commission_events e ON e.id=sp.event_id "
        "JOIN sales_contracts_ext c ON c.id=e.contract_ext_id WHERE c.site_id=:s", s=s)
    # ── 수수료 '실지급 현금'(현금흐름용) — VAT 포함(gross+vat=total_paid_of 규약) ─────────────
    #   ★[VAT 과소집계 해소(iter-5 HIGH·완결)] cash_profit(현금흐름 손익)의 수수료 현금유출을
    #     발생주의 split 합(commission)으로 빼면 두 가지가 어긋난다: ① split 은 '발생'이라 아직
    #     지급 안 된 분까지 현금유출로 과대 차감되고, ② VAT 수령자가 실제로 지급받은 부가세(현금)가
    #     반영되지 않는다. 현금흐름은 '실제로 빠져나간 돈' = 지급(payout) 의 gross+vat 합이어야 한다
    #     (extension.total_paid_of 규약과 동일: WITHHOLDING 은 vat=0 이라 gross 와 같고, VAT 수령자는
    #      부가세만큼 현금유출이 더 크다). 지급은 2소스(claim 승인·마일스톤 스케줄)이며 둘 다 합산한다.
    #   - claim 경로: payout.claim_id → claim → split → event → contract(현장).
    #   - 스케줄 경로: payout(claim_id NULL) ← schedule.paid_payout_id → split → event → contract.
    #     (settle_summary 의 2소스 UNION 규약과 동일. 같은 payout 이 두 소스에 동시 잡히지 않도록
    #      스케줄 경로는 p.claim_id IS NULL 로 상호배타.)
    #   - vat 컬럼은 정본 033 마이그레이션 이후 존재. 미적용 클린 DB(컬럼 부재 42703)나 지급 테이블
    #     미존재(42P01)는 _scalar 가 '정상 0'(아직 지급 없음)으로 폴백한다(silent-fail 아님 — 실오류는 전파).
    commission_paid_cash = await _scalar(db,
        "SELECT COALESCE(SUM(g),0) FROM ("
        "  SELECT COALESCE(p.gross,0)+COALESCE(p.vat,0) AS g FROM sales_commission_payouts p "
        "  JOIN sales_commission_claims cl ON cl.id=p.claim_id "
        "  JOIN sales_commission_splits sp ON sp.id=cl.split_id "
        "  JOIN sales_commission_events e ON e.id=sp.event_id "
        "  JOIN sales_contracts_ext c ON c.id=e.contract_ext_id WHERE c.site_id=:s "
        "  UNION ALL "
        "  SELECT COALESCE(p.gross,0)+COALESCE(p.vat,0) AS g FROM sales_commission_payouts p "
        "  JOIN sales_commission_payout_schedule sch ON sch.paid_payout_id=p.id "
        "  JOIN sales_commission_splits sp ON sp.id=sch.split_id "
        "  JOIN sales_commission_events e ON e.id=sp.event_id "
        "  JOIN sales_contracts_ext c ON c.id=e.contract_ext_id "
        "  WHERE c.site_id=:s AND p.claim_id IS NULL"
        ") u", s=s)
    visitors = await _scalar(db, "SELECT count(*) FROM mh_visitors WHERE site_id=:s", s=s)
    attend_today = await _scalar(db,
        "SELECT count(*) FROM sales_staff_attendance WHERE site_id=:s AND check_in::date=:d", s=s, d=today)
    ad_budget = await _scalar(db, "SELECT COALESCE(SUM(budget),0) FROM sales_ad_campaigns WHERE site_id=:s", s=s)

    # 실수납액(현금흐름 매출) — sales_payments(입금 기록·대사 원장)에서 대사완료(matched=true)
    # 입금만 인정. 미수금은 매출로 잡지 않는다(현금주의). 원장 미존재 시 _scalar 가 0 폴백.
    cash_collected = await _scalar(db,
        "SELECT COALESCE(SUM(amount),0) FROM sales_payments WHERE site_id=:s AND matched=true", s=s)
    # ── 독립 약정총액(분납 회차합) — reconcile 실불일치 탐지용 '제3의 출처' ───────────
    #   sales_contract_installments(계약 회차별 약정금)은 계약총액(total_price)과도, 실수납과도
    #   별개로 기록되는 독립 원장이다.
    #   ★iter-5 범위정렬(회귀3): 회차(installment)는 '서명(SIGNED)' 시점에 생성된다
    #     (contract.service.sign_contract). 그런데 revenue/scheduled_total 를 status='ACTIVE'
    #     로 집계하면 미서명 ACTIVE(예약·RESERVED)까지 매출엔 잡히는데 회차는 없어
    #     scheduled_total < revenue 거짓 불일치가 난다. 독립대사는 회차가 실재하는
    #     'SIGNED' 범위로 매출·약정·수납을 '같은 범위'로 정렬해 비교한다.
    #   ★iter-7 SSOT 정정(투기적 스코프 제거): 회차가 실재하는 contract.stage 는 'SIGNED'
    #     하나뿐이다(_RECONCILE_STAGES 주석의 service.py 근거 참조). 직전 iter-6 의
    #     stage IN ('SIGNED','MIDDLE','BALANCE') 확장은 MIDDLE/BALANCE 가 stage 로 설정되는
    #     코드가 없어 영구 dead 분기였고, installment.kind 와 stage 를 혼동한 것이었다 →
    #     실재 단계(_RECONCILE_STAGES)로 복원한다. 미래에 stage 전이가 '실제로' 추가되면
    #     _RECONCILE_STAGES 튜플 1곳만 늘리면 전체 대사 쿼리가 일괄 정합 확장된다.
    #   원장 미존재(분납표 미생성) 시 0 폴백(정상) → 그 경우 _reconcile 가 서명매출 유무로
    #     '판정보류(None)' vs '약정표 누락 경고(False)'를 분리한다(거짓안심 금지).
    _stage_signed = _stage_in_clause()  # 회차 실재 단계 IN 절('SIGNED'). 외부입력 없음(주입無)
    revenue_signed = await _scalar(db,
        "SELECT COALESCE(SUM(total_price),0) FROM sales_contracts_ext "
        f"WHERE site_id=:s AND status='ACTIVE' AND stage IN {_stage_signed}", s=s)
    scheduled_total = await _scalar(db,
        "SELECT COALESCE(SUM(i.amount),0) FROM sales_contract_installments i "
        "JOIN sales_contracts_ext c ON c.id=i.contract_ext_id "
        f"WHERE c.site_id=:s AND c.status='ACTIVE' AND c.stage IN {_stage_signed}", s=s)
    # 회차 행 수 — 반올림 허용오차 tol=ceil(N/2)+1 산정용(SIGNED 범위로 정렬, _reconcile 참조).
    installment_count = await _scalar(db,
        "SELECT count(*) FROM sales_contract_installments i "
        "JOIN sales_contracts_ext c ON c.id=i.contract_ext_id "
        f"WHERE c.site_id=:s AND c.status='ACTIVE' AND c.stage IN {_stage_signed}", s=s)
    # 회차별 실수납 합(installment_id 로 연결된 matched 입금). 약정 대비 수납 진척의 독립 출처.
    installment_paid = await _scalar(db,
        "SELECT COALESCE(SUM(p.amount),0) FROM sales_payments p "
        "JOIN sales_contract_installments i ON i.id=p.installment_id "
        "JOIN sales_contracts_ext c ON c.id=i.contract_ext_id "
        f"WHERE c.site_id=:s AND c.status='ACTIVE' AND c.stage IN {_stage_signed} AND p.matched=true", s=s)
    # 계약별 회차합이 '자기 계약총액'과 반올림 허용오차(회차수)를 초과해 어긋난 '결함 계약' 수.
    #   amount=round(total_price×ratio) 저장이므로 회차합과 계약총액 차이는 보통 ≤ 회차수(반올림).
    #   그 초과는 ratio 합≠1.0(계약결함)을 시사 → schedule_ratio_invalid 로 분리 제시.
    ratio_invalid_count = await _scalar(db,
        "SELECT count(*) FROM ("
        "  SELECT c.id, abs(COALESCE(SUM(i.amount),0) - COALESCE(MAX(c.total_price),0)) AS diff, "
        "         count(i.id) AS n "
        "  FROM sales_contracts_ext c "
        "  JOIN sales_contract_installments i ON i.contract_ext_id=c.id "
        f"  WHERE c.site_id=:s AND c.status='ACTIVE' AND c.stage IN {_stage_signed} "
        "  GROUP BY c.id"
        ") t WHERE t.diff > greatest(t.n, 1)", s=s)

    cost = await _cost_by_type(db, site_id)
    cost_total = sum(cost.values())
    # [회계손익=발생주의/수익인식] 계약 총액(ACTIVE)을 매출로 인식 − 회계비용 − 수수료배분.
    #   주의: 계약총액 즉시인식은 미수금까지 매출로 잡아 과대계상될 수 있다(K-IFRS 1115 는
    #   '이행의무 충족 시점' 인식 — 분양은 통상 진행기준/인도시점). 아래 cash_flow 와 분리 표기.
    profit = revenue - cost_total - commission
    # [현금흐름손익=현금주의] 실수납액 − 회계비용 − '실지급 수수료 현금'(payout gross+vat).
    #   ★iter-5: 수수료 현금유출은 발생주의 배분(commission=Σsplit)이 아니라 '실제 지급(payout)'으로
    #     뺀다. 그래야 ① 아직 미지급분이 현금유출로 과대차감되지 않고, ② VAT 수령자에게 실제로 나간
    #     부가세(현금)가 반영된다(gross-only 대비 vat 만큼 현금유출 ↑). 미지급분은 cash_flow 에서 빠지지
    #     않는 게 정합(아직 돈이 안 나갔으므로). 발생주의 commission 은 accrual.profit 에 그대로 쓴다.
    cash_profit = cash_collected - cost_total - commission_paid_cash
    # ── 실수납·인식매출 차액 정밀화(단순 등치 제거) ─────────────────────────────
    #   두 값은 출처가 다르다: revenue_recognized=계약총액(sales_contracts_ext.total_price,
    #   발생주의 즉시인식), cash_collected=실수납(sales_payments.matched 입금).
    #   ① 미수금(receivable) = 인식매출 − 실수납 (양수일 때) — 인식했으나 아직 못 받은 돈.
    #   ② 선수금(deferred_revenue) = 실수납 − 인식매출 (양수일 때) — 받았으나 아직 인식 안 한 돈.
    #   현재 모델은 계약총액 즉시인식이라 통상 미수금이 발생하고 선수금은 0 에 수렴한다.
    #   (인도시점/진행기준 인식으로 정밀화하면 선수금이 실재화 — 그때 동일 식으로 자동 반영됨.)
    receivable = max(revenue - cash_collected, 0)
    deferred_revenue = max(cash_collected - revenue, 0)
    # ── 독립 대사(실불일치 탐지) — 항등식 거짓안심 제거 + 반올림오차/계약결함 분리 ─────────
    #   [거짓안심 제거] receivable=max(rev−cash,0)·deferred=max(cash−rev,0) 정의상
    #     revenue == cash − deferred + receivable 는 모든 부호조합에서 '대수 항등식'이라
    #     항상 참 → 절대 불일치를 못 잡는다(자기참조 검산). 그래서 출처가 다른
    #     '제3의 독립 원장'(분납 약정표)으로 실제 불일치를 탐지한다.
    #   ★iter-5: 순수 로직 _reconcile 로 분리(단위테스트 대상). SIGNED 범위로 정렬한
    #     매출/약정/수납을 받아 — 반올림 잔차(±회차수)는 흡수하고, 그를 초과하는 약정-계약
    #     불일치(계약결함=schedule_ratio_invalid)·수납초과(paid_exceeds_schedule)만 적발한다.
    #     분납표 미생성(scheduled_total==0)이면 balanced=None('N/A', 거짓안심 금지).
    rec = _reconcile(revenue_signed, scheduled_total, installment_paid,
                     installment_count, ratio_invalid_count)
    reconcile_ok = rec["balanced"]
    discrepancies = rec["discrepancies"]
    schedule_present = scheduled_total > 0
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
            # ★iter-5: 'commission' 키는 이제 '실지급 수수료 현금'(payout gross+vat)을 담는다.
            #   현금흐름 관점에선 발생주의 배분(Σsplit)이 아니라 실제 지급된 돈만 빼야 정합이다
            #   (미지급분 제외 + VAT 수령자 부가세 현금 포함). 하위호환을 위해 기존 키 이름
            #   'commission' 을 그대로 유지하되(프론트 CashFlow.commission 참조 무파괴), 값의 의미를
            #   '현금흐름상 실지급액'으로 교체한다. 'commission_paid' 별칭도 함께 노출해 의미를 명시한다.
            #   발생주의 배분 원값은 accrual.commission 에서 별도로 본다(두 관점 분리).
            "commission": commission_paid_cash,
            "commission_paid": commission_paid_cash,
            "profit": cash_profit,
            "note": ("현금흐름 손익 = 실수납액(대사완료 입금) − 회계비용 − 실지급 수수료(payout gross+vat). "
                     "수수료는 발생주의 배분(accrual.commission)이 아닌 '실제 지급분'만 차감(VAT 포함). "
                     "납입원장·지급원장 미기록 시 0."),
        },
        "accrual": {
            # 회계 손익: 계약 매출(발생주의) 기준. 미수금 포함 과대계상 주의.
            "revenue_recognized": revenue,
            "cost_total": cost_total,
            "commission": commission,
            "profit": profit,
            # 미수금 = 인식매출 − 실수납(양수). 발생주의 매출 중 아직 못 받은 부분.
            "receivable": receivable,
            # [K-IFRS 1115 경고] 계약총액 즉시 전액인식은 '이행의무 충족 시점' 인식 원칙과 불일치.
            #   분양은 통상 공정 진행기준(over time)·인도시점(point in time)으로 인식해야 하며,
            #   즉시인식은 매출을 선반영(과대계상)한다. 운영 의사결정 시 cash_flow(현금흐름)·
            #   미수금(receivable)을 반드시 병독할 것.
            "revenue_overstated_warning": True,
            "recognition_basis": "CONTRACT_TOTAL_IMMEDIATE",  # 현재 모델(즉시인식). 정밀화 전 단계.
            # 진행기준/인도시점 정밀 인식(공정률·인도 이벤트 연동)은 deploy-pending(스키마/이벤트 필요).
            "ifrs1115_compliant": False,
            "note": ("회계 손익 = 계약 매출(발생주의) − 회계비용 − 수수료배분. "
                     "★K-IFRS 1115 미준수: 계약총액 즉시 전액인식이라 미수금(receivable)까지 매출에 "
                     "선반영(과대계상). 1115 는 이행의무 충족 시점(분양=진행기준/인도시점) 인식을 요구. "
                     "진행기준/인도시점 정밀화는 deploy-pending(공정률·인도 이벤트 원장 연동 필요)."),
        },
        # 선수금(부채): 실수납 − 인식매출(양수). 받았으나 아직 인식 안 한 돈(K-IFRS 1115 선수금).
        #   현재 계약총액 즉시인식 모델에선 통상 0(미수금 측이 양수). 단순 등치(=실수납) 아님.
        "deferred_revenue": deferred_revenue,
        # ── 독립 대사(실불일치 탐지) — 자기참조 항등식이 아닌 '제3 원장' 대조 ──────────
        #   balanced: True=독립 대사 통과 / False=실불일치 적발(discrepancies 참조) /
        #             None=독립 출처(분납 약정표) 부재로 판정 보류('N/A', 거짓안심 금지).
        "reconciliation": {
            "revenue_recognized": revenue,
            # ★iter-5: 독립대사 비교는 회차가 실재하는 SIGNED 범위(revenue_signed)와 정렬.
            #   revenue_recognized(ACTIVE 전체)는 표시용, 대사 판정은 revenue_signed 기준.
            "revenue_signed": revenue_signed,
            "cash_collected": cash_collected,
            "deferred_revenue": deferred_revenue,
            "receivable": receivable,
            # 독립 제3 출처: 분납 약정표(계약총액·실수납과 별개 입력 원장).
            "scheduled_total": scheduled_total,
            "installment_paid": installment_paid,
            "installment_count": installment_count,
            # 반올림 허용오차(±회차수) 흡수 후에도 자기 계약총액과 어긋난 '계약결함' 계약 수.
            "ratio_invalid_count": ratio_invalid_count,
            "tolerance": rec["tolerance"],
            "schedule_present": schedule_present,
            "balanced": reconcile_ok,
            "discrepancies": discrepancies,
            "note": ("독립 대사(자기참조 항등식 아님): 분납 약정표(scheduled_total)를 "
                     "SIGNED 계약총액(revenue_signed)·실수납(installment_paid)과 대조해 실불일치를 탐지. "
                     "회차 약정금은 round(계약총액×비율) 저장이라 ±tol(=ceil(회차수/2)+1, 회차0이면1) "
                     "반올림 잔차는 흡수하고(약정-계약·수납초과 양쪽 대칭 적용), 그를 초과하는 약정-계약 "
                     "불일치는 계약결함(schedule_ratio_invalid)으로 분리 제시. balanced: True=대사통과 / "
                     "False=불일치 적발 또는 '서명매출>0인데 약정표 누락'(schedule_missing_for_signed) / "
                     "None=서명매출도 0(서명계약 부재로 판정보류). "
                     "선수금/미수금 분해(deferred_revenue/receivable)는 두 출처 차액 표기이며 "
                     "그 자체로는 정합을 보장하지 않는다(독립 대사로 별도 검증)."),
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
    """sales_staff_wage 멱등 보장(부팅 안전망) — 프로세스 1회만 실제 DDL 수행.

    정본은 Alembic 032_sales_admin_accounting. 마이그레이션 미적용 환경 대비
    CREATE/ALTER IF NOT EXISTS 만 수행한다(파괴적 변경 없음).
    ★iter-4: 최초 1회 성공 후엔 즉시 반환(no-op).
    ★iter-5(작업5): 쓰기경로(set_staff_wage)에서만 호출한다. compute_payroll(읽기경로)은
      _load_wages 의 graceful 폴백으로 전환해 더 이상 이 함수를 부르지 않는다(읽기경로 DDL 강등).
    """
    global _wage_ready
    if _wage_ready:
        return
    async with _wage_lock:
        if _wage_ready:
            return
        await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_WAGE})
        await db.execute(text(_WAGE_DDL))
        # 기존 테이블에 tax_mode 컬럼 멱등 추가.
        await db.execute(text(
            "ALTER TABLE sales_staff_wage ADD COLUMN IF NOT EXISTS tax_mode "
            "varchar(12) NOT NULL DEFAULT 'FREELANCE'"))
        await db.execute(text("CREATE INDEX IF NOT EXISTS ix_staff_wage_site ON sales_staff_wage(site_id)"))
        await db.commit()
        _wage_ready = True


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
    """현장 직원별 급여 자동산정 — 근태(출근일수·근무분) × 단가. 회계 인건비 후보.

    ★iter-5(작업5): 읽기경로에서 _ensure_wage(DDL) 호출을 제거한다. 단가표는 _load_wages
      가 graceful 폴백(테이블 미존재=단가 미설정)으로 읽으므로, 조회용 GET /payroll 이
      DDL/advisory-lock/commit 을 트리거하지 않는다(읽기경로 DDL 완전강등).
    """
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
    # 단가표는 읽기 graceful 폴백(미존재=단가 미설정). 쓰기경로(set_staff_wage)가 테이블을 보장.
    wages = await _load_wages(db, site_id)
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
