"""수납 — 가상계좌 발급/입금 대사(미납 회차 충당)/연체이자 산정. 자금이체 미수행(기록·대사·산출)."""

import contextlib
import logging
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sales_crypto import encrypt
from apps.api.database.models.sales.contract_crm_ad import SalesContractExt, SalesContractInstallment
from apps.api.database.models.sales.payment import SalesPayment, SalesVirtualAccount
from apps.api.database.models.sales.site_org import SalesSiteConfig

logger = logging.getLogger(__name__)

# 테이블/컬럼 미존재 PostgreSQL SQLSTATE(asyncpg). 이것만 '정상 0'(아직 안 만든 테이블)으로 본다.
# 42P01=undefined_table, 42703=undefined_column. 그 외 DB 오류는 은폐 금지(분류 로깅 후 전파).
# (app/services/sales/commission/engine.py 의 검증된 분류 패턴과 동일.)
_MISSING_OBJECT_SQLSTATES = frozenset({"42P01", "42703"})


def _missing_object_sqlstate(exc: BaseException) -> str | None:
    """예외가 '테이블/컬럼 미존재'(42P01/42703)면 해당 SQLSTATE, 아니면 None(전파신호)."""
    orig = getattr(exc, "orig", None) or exc
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if code in _MISSING_OBJECT_SQLSTATES:
        return code
    return None


def overdue_interest(unpaid: int, days: int, rate: Decimal) -> int:
    """연체이자 순수 산식 — 미납액 × 연체일수 × (연이율/365), 원 단위 반올림.

    quantize(Decimal("1")) 는 기본 ROUND_HALF_EVEN(은행가 반올림) — 기존 overdue_calc 의
    산식·반올림을 그대로 보존한다(무회귀). unpaid<=0/days<=0/rate<=0 이면 0(면책).
    DB 무관 순수함수(단위테스트로 산식 회귀를 막는다).
    """
    if unpaid <= 0 or days <= 0 or rate <= 0:
        return 0
    return int((Decimal(unpaid) * days * (Decimal(rate) / Decimal(365))).quantize(Decimal("1")))


async def issue_va(db: AsyncSession, site_id, contract_id, bank, va_number, holder, pool_ref=None):
    db.add(SalesVirtualAccount(site_id=site_id, contract_ext_id=contract_id, bank=bank,
           va_number_enc=encrypt(va_number), holder=holder, pool_ref=pool_ref))
    await db.flush()


def _order_installments(insts: list, preferred_seq=None) -> list:
    """미납 회차 충당 순서 결정 — 기본은 seq 오름차순. preferred_seq 가 주어지면
    그 회차(들)부터 먼저 충당하고 나머지는 seq 오름차순으로 잇는다(회차지정 충당 옵션).

    DB 무관 순수함수(정렬규칙) — 단위테스트로 회차충당 순서를 고정한다.
    """
    ordered = sorted(insts, key=lambda x: (x.seq is None, x.seq or 0))
    if preferred_seq is None:
        return ordered
    head = [x for x in ordered if x.seq == preferred_seq]
    tail = [x for x in ordered if x.seq != preferred_seq]
    return head + tail


def _dup_response(dup) -> dict:
    """이미 처리된 입금(raw_ref 중복)을 응답계약 공통 키집합으로 직렬화한다.

    선조회 fast-path 와 동시 INSERT 충돌(23505) 재조회 폴백이 같은 형식을 쓰도록 단일화한다.
    matched 면 충당액(amount)을 allocated 로, 아니면 0. duplicate=True 로 중복임을 명시한다.
    """
    return {"matched": bool(dup.matched), "status": dup.status, "duplicate": True,
            "contract": str(dup.contract_ext_id) if dup.contract_ext_id else None,
            "allocated": int(dup.amount or 0) if dup.matched else 0, "unapplied": 0}


async def ingest_payment(db: AsyncSession, site_id, payload: dict) -> dict:
    """payload: {va_number, amount, depositor?, paid_at?, raw_ref?, preferred_installment_seq?}.

    미매칭 → 수동 대사 큐(status=UNMATCHED). 매칭 성공 → status=MATCHED.
    회차지정 충당: preferred_installment_seq 지정 시 그 회차부터 우선 충당한다.
    """
    target = encrypt(payload["va_number"])
    amount = Decimal(str(payload["amount"]))
    paid_at = payload.get("paid_at")
    pref_seq = payload.get("preferred_installment_seq")
    if pref_seq is not None:
        pref_seq = int(pref_seq)

    # 입금액이 0 이하면 거부(은행/PG 페이로드 위조·오류 방어).
    if amount <= 0:
        raise HTTPException(400, "입금액이 0 이하입니다.")

    # 멱등성(★보장수준=DB UNIQUE): 같은 거래참조(raw_ref)가 이미 처리됐으면 다시 충당하지 않고
    # 그대로 반환한다(PG·은행 webhook 은 네트워크 재시도로 같은 입금을 여러 번 보내는 게 정상).
    # 앱레벨 선조회(아래)는 빠른 경로(fast-path)일 뿐 멱등의 정본이 아니다 — 두 콜백이 동시에
    # 조회→둘 다 미발견→둘 다 INSERT 하는 TOCTOU 가 있어, 035 의 partial UNIQUE
    # (uq_pay_site_raw_ref, site_id+raw_ref WHERE raw_ref IS NOT NULL)가 2번째 INSERT 를 23505 로
    # 막는 게 정본이다(아래 flush 의 IntegrityError 폴백에서 기존 행을 재조회해 중복으로 반환).
    raw_ref = payload.get("raw_ref")
    if raw_ref:
        dup = (await db.execute(select(SalesPayment).where(
            SalesPayment.site_id == site_id, SalesPayment.raw_ref == raw_ref))).scalar_one_or_none()
        if dup is not None:
            return _dup_response(dup)
    va = (await db.execute(select(SalesVirtualAccount).where(
        SalesVirtualAccount.site_id == site_id, SalesVirtualAccount.va_number_enc == target))).scalar_one_or_none()
    if not va:
        # 계좌를 못 찾으면 자동충당 불가 → 미대사 큐로 보관(나중에 수동매칭). matched=False ⇔ UNMATCHED.
        db.add(SalesPayment(site_id=site_id, method="VA", amount=amount, paid_at=paid_at,
               matched=False, status="UNMATCHED", raw_ref=payload.get("raw_ref")))
        await db.flush()
        return {"matched": False, "status": "UNMATCHED", "duplicate": False,
                "contract": None, "allocated": 0, "unapplied": int(amount)}
    # 회차 충당 루프 진입 전 회차를 행잠금(FOR UPDATE)한다 — manual_match/reverse 와 잠금 대칭.
    # 동시 입금/취소/수동매칭 콜백이 같은 회차의 paid_amount 를 경쟁 갱신해 이중 충당되는 것을 막는다.
    insts = list((await db.execute(select(SalesContractInstallment).where(
        SalesContractInstallment.contract_ext_id == va.contract_ext_id).with_for_update())).scalars())
    remaining = amount
    pay_inst_id = None
    # 회차별 실제 충당액을 기록한다(다회차 분산 충당 시 취소 정확복원의 근거).
    allocations: list[dict] = []
    for it in _order_installments(insts, pref_seq):
        due = (it.amount or 0) - (it.paid_amount or 0)
        if due <= 0:
            continue
        applied = min(Decimal(due), remaining)
        it.paid_amount = (it.paid_amount or 0) + int(applied)
        if applied >= due:
            it.paid_at = paid_at or datetime.now(UTC)
        pay_inst_id = pay_inst_id or it.id
        allocations.append({"installment_id": str(it.id), "applied_amount": int(applied)})
        remaining -= applied
        if remaining <= 0:
            break
    # ★[과오납 silent 오표기 차단] VA 는 있으나 충당된 회차가 0(모든 회차 완납·due<=0)이면
    #   이건 회차에 들어가지 못한 '과오납(surplus)'이다. 예전엔 allocations=[] 인데도 matched=True/
    #   status=MATCHED 로 기록해 "회차 충당됨"으로 거짓 표기됐다 → status='SURPLUS'/matched=False 로
    #   분기하고 matched:False·unapplied=전액 을 반환한다. 금액(amount 컬럼)은 그대로 보존해(손실 0)
    #   환급/재배정의 근거로 남긴다(소비자가 '충당 0·미충당 잔여' 를 정직하게 인지).
    matched_any = bool(allocations)
    status = "MATCHED" if matched_any else "SURPLUS"
    pay = SalesPayment(site_id=site_id, contract_ext_id=va.contract_ext_id, installment_id=pay_inst_id,
           method="VA", amount=amount, paid_at=paid_at, matched=matched_any, status=status,
           preferred_installment_seq=pref_seq, allocations=allocations or None,
           raw_ref=raw_ref)
    db.add(pay)
    # ★멱등 DB 게이트(동시 webhook): raw_ref 가 있으면 INSERT 를 savepoint 안에서 flush 해
    #   동시 콜백이 같은 raw_ref 로 먼저 INSERT 한 경우의 UNIQUE 위반(23505)을 IntegrityError 로
    #   잡는다. 그땐 이 savepoint 만 되돌리고(회차 충당 ORM 변경은 보존) 기존 행을 재조회해 '중복'
    #   으로 반환한다 → 선조회를 통과한 TOCTOU 도 회차가 두 번 충당되지 않는다.
    #   ★주의: 회차 paid_amount 가산은 이 savepoint '밖'에서 이미 일어났다. 중복이면 그 가산이 잘못
    #   남으므로, savepoint rollback 후 충당했던 회차를 allocations 대로 정확히 되돌린다(이중 충당 0).
    nested = getattr(db, "begin_nested", None)
    if raw_ref and callable(nested):
        try:
            async with db.begin_nested():
                await db.flush()
        except IntegrityError:
            # 동시 콜백이 먼저 같은 raw_ref 를 넣었다 → 이번 INSERT 는 무효, 회차 가산을 되돌린다.
            for a in allocations:
                it = next((x for x in insts if str(x.id) == a["installment_id"]), None)
                if it is not None:
                    it.paid_amount = int(it.paid_amount or 0) - int(a["applied_amount"])
                    if int(it.paid_amount) < int(it.amount or 0):
                        it.paid_at = None
            dup = (await db.execute(select(SalesPayment).where(
                SalesPayment.site_id == site_id, SalesPayment.raw_ref == raw_ref))).scalar_one_or_none()
            if dup is not None:
                return _dup_response(dup)
            raise  # 같은 raw_ref 가 아닌 다른 무결성 위반이면 은폐 금지(전파).
    else:
        # raw_ref 없는 수동 입금(중복 허용) 또는 savepoint 미지원 세션은 일반 flush.
        await db.flush()
    # ★응답계약 통일: 다섯 분기(중복/미매칭/매칭/과오납/동시중복)가 같은 키집합을 항상 반환한다(소비자 키 가정 안정).
    return {"matched": matched_any, "status": status, "duplicate": False,
            "contract": str(va.contract_ext_id),
            "allocated": int(amount - remaining), "unapplied": int(max(remaining, 0))}


async def reverse_payment(db: AsyncSession, site_id, payment_id, reason: str | None = None) -> dict:
    """입금 취소/반려(MATCHED → REVERSED). 충당했던 회차 납입액을 되돌리고 종료상태로 전이한다.

    - 현장 격리: 같은 현장(site_id)의 결제만 취소 가능(타 현장 결제 위조 차단).
    - 멱등/종료상태 가드: 이미 REVERSED 면 추가 차감 없이 그대로 반환(중복 반려 콜백 방어).
      UNMATCHED(미충당)도 회차에 가산된 적이 없으니 차감 없이 상태만 REVERSED 로 표기.
    - MATCHED 였다면 충당했던 회차를 ★회차별 정확히★ 되돌린다:
        · allocations(다회차 분배 기록)가 있으면 회차별 applied_amount 만큼 정확히 차감한다
          (다회차 분산 입금을 취소해도 첫 회차 과차감·둘째이후 미복원 유령잔존이 없다).
        · allocations 가 없는 구행은 단일 installment_id 에서 결제 전액 차감(0 하한) 폴백 — 무회귀.
      회차가 다시 미납이 되면 paid_at 을 비운다(완납 취소 재계산).
    - LOAN 가드: 대출 실행분(method='LOAN')은 대출 상환경로(repay_loan)에서만 되돌려야 한다.
      수납 취소로 회차만 되돌리면 대출-수납 정합이 깨진(고아) 상태가 되므로 409 로 막는다.
    - 자금이동 미수행(기록 되돌림만). 반환=취소 결과 요약(소비자 키 가정 안정 위해 키집합 통일).
    """
    from apps.api.database.models.sales.contract_crm_ad import SalesContractInstallment
    # 같은 현장 결제만 행잠금으로 조회(동시 취소 콜백 경쟁 차단).
    p = (await db.execute(select(SalesPayment).where(
        SalesPayment.id == payment_id, SalesPayment.site_id == site_id
    ).with_for_update())).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "해당 현장의 결제 내역을 찾을 수 없습니다.")
    if p.status == "REVERSED":
        # ★응답계약 통일: 멱등·정상 두 분기가 같은 키집합(status/reversed/duplicate/reverted_amount).
        return {"status": "REVERSED", "reversed": False, "duplicate": True, "reverted_amount": 0}
    # 대출 실행분 입금은 수납 취소로 되돌리면 대출-수납 고아가 된다 → 상환경로에서만 취소.
    if (p.method or "").upper() == "LOAN":
        raise HTTPException(409, "대출 실행분 입금은 대출 상환 경로(repay_loan)에서만 취소할 수 있습니다.")
    reverted = 0
    # MATCHED(대사완료)였고 충당한 회차가 있으면 그만큼 되돌린다(이중취소 방지: 아래 상태전이로 종료).
    if p.matched:
        # 회차별 차감 계획: allocations 기록이 있으면 그대로, 없으면 단일 installment_id 폴백.
        plan: list[tuple] = []
        allocs = p.allocations if isinstance(p.allocations, list) else None
        if allocs:
            for a in allocs:
                iid = a.get("installment_id") if isinstance(a, dict) else None
                amt = int((a.get("applied_amount") or 0) if isinstance(a, dict) else 0)
                if iid and amt > 0:
                    plan.append((iid, amt))
        elif p.installment_id is not None:
            plan.append((str(p.installment_id), int(p.amount or 0)))
        for iid, amt in plan:
            it = (await db.execute(select(SalesContractInstallment).where(
                SalesContractInstallment.id == iid).with_for_update())).scalar_one_or_none()
            if it is None:
                continue
            new_paid = max(int(it.paid_amount or 0) - amt, 0)
            reverted += int(it.paid_amount or 0) - new_paid
            it.paid_amount = new_paid
            # 회차가 다시 미납이 되면 완납 시각을 비운다.
            if new_paid < int(it.amount or 0):
                it.paid_at = None
    p.matched = False
    p.status = "REVERSED"
    # 취소 사유를 거래참조에 남겨 추적성을 보존한다(별도 감사컬럼 없음 → raw_ref 에 부기).
    if reason:
        base = (p.raw_ref or "")[:80]
        p.raw_ref = (f"{base}|reversed:{reason}")[:120]
    await db.flush()
    return {"status": "REVERSED", "reversed": True, "duplicate": False, "reverted_amount": reverted}


async def overdue_calc(db: AsyncSession, site_id, as_of: datetime) -> int:
    """현장 미납 회차의 연체이자를 'as_of 날짜 기준'으로 산정해 적재한다(자금이동 없음).

    멱등(★실제 보장수준): 같은 (site_id, installment_id, calc_date) 조합은 1건만 남는다.
    INSERT 를 ON CONFLICT (site_id, installment_id, calc_date) WHERE calc_date IS NOT NULL
    DO UPDATE 로 적재하므로, 같은 날 재실행하거나(수동/일배치) 두 경로가 동시에 진입해도
    UNIQUE(uq_overdue_site_inst_date) 위반(23505)이 발생하지 않고 마지막 산출값으로 덮어쓴다
    (advisory-lock 없이도 race 안전). 반환=적재(또는 갱신) 건수.

    ※ 정본 멱등키(UNIQUE 부분 인덱스)는 Alembic 035 마이그레이션에서 만든다(WHERE calc_date IS
      NOT NULL 부분 인덱스). ★ON CONFLICT 의 술어는 그 부분 인덱스의 술어와 '글자 그대로' 같아야
      arbiter 추론이 된다 — 술어를 빼면 42P10(no unique constraint matching ON CONFLICT)이 나고
      42P10 은 미존재 폴백(42P01/42703)에 없어 전파→500 이 되므로, '부분 마이그라 무해'가 아니라
      술어 정합이 정합성·무장애의 전제다. 마이그 미적용(인덱스 부재) 환경에서는 ON CONFLICT 가
      발동할 충돌 대상이 없어 일반 INSERT 처럼 동작하고, 그 경우 동시진입은 일배치 advisory-lock 이
      직렬화한다(부분 인덱스가 아예 없으면 42P10 이 아니라 충돌 미발생이라 그대로 INSERT).

    테이블/컬럼 미존재(42P01/42703)는 마이그레이션 직전 환경의 '정상 0'으로 본다(site-list
    SELECT 뿐 아니라 DELETE/INSERT 경로에도 일관 적용). 그 외 DB 오류는 은폐 금지(분류 로깅 후 전파).

    연체이율(overdue_rate)은 현장 설정의 약관 파라미터다 — 미설정(0)이면 이자 0(면책·정직표기).
    """
    try:
        cfg = (await db.execute(select(SalesSiteConfig).where(
            SalesSiteConfig.site_id == site_id))).scalar_one_or_none()
        # 연체이율(파라미터, 약관 재확인) — 현장 설정의 stage_def.overdue_rate, 미설정이면 0(이자 0·면책).
        rate = Decimal(str(((cfg.stage_def if cfg else None) or {}).get("overdue_rate", 0)))
        as_of_date = as_of.date()
        # 현장 스코프: contracts_ext 조인으로 site_id 필터
        insts = list((await db.execute(
            select(SalesContractInstallment)
            .join(SalesContractExt, SalesContractExt.id == SalesContractInstallment.contract_ext_id)
            .where(SalesContractExt.site_id == site_id,
                   SalesContractInstallment.due_date < as_of_date))).scalars())
        n = 0
        for it in insts:
            unpaid = (it.amount or 0) - (it.paid_amount or 0)
            if unpaid <= 0:
                continue
            days = (as_of_date - it.due_date).days
            interest = overdue_interest(int(unpaid), days, rate)
            # ★멱등 upsert: 같은 (site_id, installment_id, calc_date) 면 덮어쓴다(중복 행 0·동시진입 23505 0).
            #   delete-before-insert 대신 ON CONFLICT 로 바꿔 일배치(advisory-lock)와 수동 트리거가
            #   같은 현장·날짜에 동시 진입해도 UNIQUE 위반이 나지 않게 한다.
            #   ★[CRITICAL] ON CONFLICT 의 술어(WHERE calc_date IS NOT NULL)는 035 마이그가 만든
            #   '부분(partial)' UNIQUE 인덱스(uq_overdue_site_inst_date, 같은 술어)와 정확히 일치해야
            #   Postgres 가 arbiter 인덱스를 추론할 수 있다. 술어를 빼면 부분 인덱스를 arbiter 로 못 찾아
            #   42P10(invalid_column_reference: no unique constraint matching ON CONFLICT)이 나고,
            #   42P10 은 미존재(42P01/42703) 폴백에 없어 그대로 전파돼 500 이 된다.
            await db.execute(text(
                "INSERT INTO sales_overdue_interest "
                "(id, site_id, installment_id, overdue_days, rate, amount, calc_date, calculated_at) "
                "VALUES (gen_random_uuid(), :s, :inst, :days, :rate, :amt, :d, now()) "
                "ON CONFLICT (site_id, installment_id, calc_date) WHERE calc_date IS NOT NULL "
                "DO UPDATE SET overdue_days = EXCLUDED.overdue_days, rate = EXCLUDED.rate, "
                "amount = EXCLUDED.amount, calculated_at = now()"),
                {"s": str(site_id), "inst": str(it.id), "days": days,
                 "rate": str(rate), "amt": interest, "d": as_of_date})
            n += 1
        await db.flush()
        return n
    except Exception as e:  # noqa: BLE001 — 미존재(정상0)만 폴백, 실오류는 재전파(은폐 금지).
        if _missing_object_sqlstate(e):
            # ★aborted txn 정리: 테이블/컬럼 미존재(42P01/42703)로 INSERT/SELECT 가 실패하면
            #   현재 트랜잭션이 'aborted' 상태로 남는다 → 이대로 0 을 반환하면 호출부의 후속
            #   commit 이 25P02(in_failed_sql_transaction)로 500 이 되고, 일배치는 다음 현장
            #   SELECT 까지 같은 에러가 전파돼 잔여 현장 처리가 통째로 막힌다(cascade skip).
            #   rollback 으로 트랜잭션을 깨끗이 비워 후속 commit·다음 현장 SELECT 가 정상 진행되게 한다.
            await db.rollback()
            logger.info("연체 산정 skip — 수납 테이블 미생성(정상 0)")
            return 0
        raise


async def run_overdue_all_sites(db: AsyncSession, as_of: datetime | None = None) -> dict:
    """전 현장 연체이자 일배치 — 미납 회차가 있는 현장만 골라 overdue_calc 를 돈다.

    스케줄러/크론 엔드포인트에서 호출하는 진입점. 현장 목록 조회 자체가 '테이블 미존재'(42P01/
    42703)면 아직 마이그레이션 전이므로 정상 0(빈 결과)로 본다 — 그 외 DB 오류는 은폐 금지(전파).

    ★[per-site 격리] 한 현장 산정이 실패(예: 42P10·일시 DB 오류)해도 그 현장만 건너뛰고 나머지
      현장은 계속 처리한다. 각 현장을 savepoint(begin_nested)로 감싸 실패 시 그 savepoint 만
      되돌리고(이미 성공한 이전 현장 작업은 보존), 실패 현장은 결과의 failed 목록에 사유와 함께
      집계한다. begin_nested 가 없는(가짜) 세션이면 savepoint 없이 try/except 로만 격리한다.
    """
    when = as_of or datetime.now(UTC)
    # 반환키 균일화: 어느 경로로 끝나도 {sites, rows, as_of, skipped, failed} 를 항상 채워 반환한다
    # (skipped 는 미존재 폴백일 때만 사유 문자열, 정상이면 None / failed 는 현장별 실패 사유 목록).
    try:
        site_ids = list((await db.execute(
            select(SalesContractExt.site_id).distinct())).scalars())
    except Exception as e:  # noqa: BLE001 — 미존재(정상0)만 폴백, 실오류는 재전파.
        if _missing_object_sqlstate(e):
            # aborted txn 정리(위 overdue_calc 와 동일 사유): 실패한 SELECT 로 트랜잭션이 막혀
            # 호출부(일배치 루프)의 다음 작업에 25P02 가 전파되지 않게 rollback 한다.
            await db.rollback()
            logger.info("연체 일배치 skip — 계약 테이블 미생성(정상 0)")
            return {"sites": 0, "rows": 0, "as_of": str(when.date()),
                    "skipped": "missing_table", "failed": []}
        raise
    total = 0
    done = 0
    failed: list[dict] = []
    for sid in site_ids:
        if sid is None:
            continue
        # savepoint 로 현장 단위 격리(실세션). 가짜 세션엔 begin_nested 가 없으니 None 폴백.
        nested = getattr(db, "begin_nested", None)
        has_savepoint = callable(nested)
        try:
            if has_savepoint:
                async with db.begin_nested():
                    total += await overdue_calc(db, sid, when)
            else:
                total += await overdue_calc(db, sid, when)
            done += 1
        except Exception as e:  # noqa: BLE001 — 한 현장 실패가 배치 전체를 끊지 않게 격리(silent-fail 아님: 분류 로깅+집계).
            # ★[CASE A·savepoint 경로] begin_nested 의 async with 가 예외로 빠져나갈 때
            #   savepoint 의 __aexit__ 가 '그 savepoint 만' 자동 rollback 한다(ROLLBACK TO SAVEPOINT).
            #   바깥 트랜잭션과 이미 성공한 이전 현장 작업은 그대로 살아 있으므로, 여기서 추가로
            #   db.rollback()(전체 롤백)을 부르면 오히려 성공분까지 날린다 → savepoint 경로에선
            #   별도 rollback 을 하지 않는다(중복·과잉 롤백 제거).
            # ★[CASE B·가짜/savepoint 미지원 세션] savepoint 가 없으면 실패한 SQL 로 트랜잭션이
            #   aborted 상태로 남아 다음 현장 작업이 25P02 로 막힌다 → 이 경로에서만 db.rollback()
            #   으로 트랜잭션을 비운다(이미 commit 된 건 없어 손실 없음).
            if not has_savepoint:
                with contextlib.suppress(Exception):  # rollback 자체 실패도 배치를 끊지 않는다.
                    await db.rollback()
            reason = _missing_object_sqlstate(e) or (
                getattr(getattr(e, "orig", None) or e, "sqlstate", None)
                or getattr(getattr(e, "orig", None) or e, "pgcode", None)
                or type(e).__name__)
            logger.warning("연체 일배치 — 현장 %s 산정 실패(격리·계속): %s", str(sid), str(reason)[:80])
            failed.append({"site_id": str(sid), "reason": str(reason)[:80]})
    await db.commit()
    return {"sites": done, "rows": total, "as_of": str(when.date()),
            "skipped": None, "failed": failed}
