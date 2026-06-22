"""#4 수납·대출·보증 — 순수로직 회귀 안전망(Wave2 P1-1).

DB 무관(또는 가짜객체) 단위테스트로 다음 회귀를 영구 차단한다.
- overdue_interest: 미납액×연체일수×(연이율/365), 원 미만 절사. 0이하 인자 → 0(면책).
- _order_installments: 회차충당 순서(기본 seq 오름차순 / preferred_seq 우선).
- _missing_object_sqlstate: 42P01/42703 만 미존재(정상0)로 분류, 그 외 None(전파신호).
- _allocate_repayment: 대출 상환 배분(오래된 실행분 우선·과상환 차단).
- repay_loan 상태전이: 전액상환 시 status=REPAID, 멱등(REPAID 재호출 추가충당 0), 부분상환 누적.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid as uuid_mod
from datetime import UTC, datetime
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy.exc import DBAPIError, IntegrityError  # noqa: E402

from app.services.sales.loan import service as loan_svc  # noqa: E402
from app.services.sales.loan.service import _allocate_repayment, repay_loan  # noqa: E402
from app.services.sales.payment import service as payment_svc  # noqa: E402
from app.services.sales.payment.service import (  # noqa: E402
    _missing_object_sqlstate,
    _order_installments,
    ingest_payment,
    overdue_calc,
    overdue_interest,
    reverse_payment,
    run_overdue_all_sites,
)


# ── overdue_interest: 연체이자 산식 + 원 미만 절사 ──────────────────────────────
class TestOverdueInterest:
    def test_basic(self):
        """미납 10,000,000 × 30일 × 12%/365 = 98,630.13... → 절사 98,630."""
        assert overdue_interest(10_000_000, 30, Decimal("0.12")) == 98_630

    def test_rounds_won(self):
        """원 단위 반올림(ROUND_HALF_EVEN, 기존 산식 보존). 1,000,000 × 1일 × 15%/365 = 410.96 → 411."""
        assert overdue_interest(1_000_000, 1, Decimal("0.15")) == 411

    def test_zero_rate_is_zero(self):
        """연체이율 미설정(0) → 이자 0(면책·정직표기)."""
        assert overdue_interest(10_000_000, 30, Decimal("0")) == 0

    def test_nonpositive_args_zero(self):
        assert overdue_interest(0, 30, Decimal("0.12")) == 0
        assert overdue_interest(-100, 30, Decimal("0.12")) == 0
        assert overdue_interest(10_000_000, 0, Decimal("0.12")) == 0
        assert overdue_interest(10_000_000, -5, Decimal("0.12")) == 0


# ── _order_installments: 회차 충당 순서(회차지정 충당 옵션) ─────────────────────
class _Inst:
    def __init__(self, seq):
        self.seq = seq


class TestOrderInstallments:
    def test_default_ascending(self):
        order = _order_installments([_Inst(3), _Inst(1), _Inst(2)])
        assert [i.seq for i in order] == [1, 2, 3]

    def test_preferred_first(self):
        """preferred_seq=2 → 2번 회차를 먼저 충당하고 나머지는 seq 오름차순."""
        order = _order_installments([_Inst(3), _Inst(1), _Inst(2)], preferred_seq=2)
        assert [i.seq for i in order] == [2, 1, 3]

    def test_none_seq_sorts_last(self):
        order = _order_installments([_Inst(None), _Inst(1)])
        assert [i.seq for i in order] == [1, None]


# ── _missing_object_sqlstate: 미존재(정상0) vs 실오류(전파) 분류 ─────────────────
class _FakeOrigError(Exception):
    def __init__(self, sqlstate):
        super().__init__("fake")
        self.sqlstate = sqlstate


def _dbapi(sqlstate):
    return DBAPIError("stmt", {}, _FakeOrigError(sqlstate))


class TestMissingObjectSqlstate:
    def test_undefined_table_is_missing(self):
        assert _missing_object_sqlstate(_dbapi("42P01")) == "42P01"

    def test_undefined_column_is_missing(self):
        assert _missing_object_sqlstate(_dbapi("42703")) == "42703"

    def test_permission_is_not_missing(self):
        """★권한오류(42501)는 미존재가 아님 → None(전파신호). 0으로 은폐 금지."""
        assert _missing_object_sqlstate(_dbapi("42501")) is None

    def test_connection_is_not_missing(self):
        assert _missing_object_sqlstate(_dbapi("08006")) is None


# ── _allocate_repayment: 대출 상환 배분(오래된 실행분 우선·과상환 차단) ──────────
class _Disb:
    def __init__(self, amount, repaid_amount=0, disbursed_at=None, installment_seq=None):
        self.id = uuid_mod.uuid4()
        self.amount = amount
        self.repaid_amount = repaid_amount
        self.disbursed_at = disbursed_at
        self.installment_seq = installment_seq
        self.repaid_at = None


def _dt(day):
    return datetime(2026, 1, day, tzinfo=UTC)


class TestAllocateRepayment:
    def test_oldest_first(self):
        """오래된 실행분(disbursed_at 빠른 순)부터 채운다."""
        d1 = _Disb(1_000_000, disbursed_at=_dt(1))
        d2 = _Disb(2_000_000, disbursed_at=_dt(5))
        plan = _allocate_repayment([d2, d1], 1_500_000)
        # d1 먼저 1,000,000 채우고 남은 500,000 을 d2 에 충당.
        assert [(p[0].id, p[1]) for p in plan] == [(d1.id, 1_000_000), (d2.id, 500_000)]

    def test_partial_into_single(self):
        d1 = _Disb(1_000_000, disbursed_at=_dt(1))
        plan = _allocate_repayment([d1], 400_000)
        assert plan == [(d1, 400_000)]

    def test_over_repay_capped(self):
        """미상환총액 초과 상환은 미상환총액까지만 배분(과상환 차단)."""
        d1 = _Disb(1_000_000, repaid_amount=600_000, disbursed_at=_dt(1))
        plan = _allocate_repayment([d1], 999_999)
        # 잔여 400,000 만 배분.
        assert plan == [(d1, 400_000)]

    def test_already_full_skipped(self):
        d1 = _Disb(1_000_000, repaid_amount=1_000_000, disbursed_at=_dt(1))
        plan = _allocate_repayment([d1], 500_000)
        assert plan == []


# ── repay_loan: 상태전이(REPAID)·멱등·부분상환 ─────────────────────────────────
class _FakeResult:
    def __init__(self, value=None, items=None):
        self._value = value
        self._items = items or []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return list(self._items)

    def __iter__(self):
        return iter(self._items)


class _Agreement:
    def __init__(self, site_id, status="EXECUTED"):
        self.id = uuid_mod.uuid4()
        self.site_id = site_id
        self.status = status


class _RepayDB:
    """repay_loan 의 execute 호출 순서(약정 조회 → 실행분 FOR UPDATE 조회)를 흉내내는 가짜 세션."""

    def __init__(self, agreement, disbs):
        self._agreement = agreement
        self._disbs = disbs
        self._call = 0
        self.flushed = False

    async def execute(self, *_a, **_k):
        self._call += 1
        if self._call == 1:
            return _FakeResult(value=self._agreement)
        return _FakeResult(items=self._disbs)

    async def flush(self):
        self.flushed = True


SITE = uuid_mod.uuid4()


def _run(coro):
    return asyncio.run(coro)


class TestRepayLoan:
    def test_full_repay_transitions_repaid(self):
        ag = _Agreement(SITE)
        d1 = _Disb(1_000_000, disbursed_at=_dt(1))
        d2 = _Disb(2_000_000, disbursed_at=_dt(2))
        db = _RepayDB(ag, [d1, d2])
        res = _run(repay_loan(db, SITE, ag.id, 3_000_000))
        assert res["status"] == "REPAID"
        assert res["fully_repaid"] is True
        assert res["applied"] == 3_000_000
        assert res["outstanding"] == 0
        assert ag.status == "REPAID"
        # 완납된 실행분에 repaid_at 이 찍힌다.
        assert d1.repaid_at is not None and d2.repaid_at is not None

    def test_partial_repay_keeps_executed(self):
        ag = _Agreement(SITE)
        d1 = _Disb(1_000_000, disbursed_at=_dt(1))
        d2 = _Disb(2_000_000, disbursed_at=_dt(2))
        db = _RepayDB(ag, [d1, d2])
        res = _run(repay_loan(db, SITE, ag.id, 1_000_000))
        # 부분상환 → 약정은 아직 EXECUTED, 미상환 잔액 존재.
        assert res["status"] == "EXECUTED"
        assert res["fully_repaid"] is False
        assert res["outstanding"] == 2_000_000
        assert ag.status == "EXECUTED"
        # d1 완납 → repaid_at, d2 미상환 → None.
        assert d1.repaid_at is not None
        assert d2.repaid_at is None

    def test_idempotent_when_already_repaid(self):
        """이미 REPAID 약정 재상환 콜백 → 추가 충당 0(멱등·중복 상환 방어)."""
        ag = _Agreement(SITE, status="REPAID")
        d1 = _Disb(1_000_000, repaid_amount=1_000_000, disbursed_at=_dt(1))
        db = _RepayDB(ag, [d1])
        res = _run(repay_loan(db, SITE, ag.id, 1_000_000))
        assert res["status"] == "REPAID"
        assert res["applied"] == 0
        assert res.get("duplicate") is True

    def test_response_keys_uniform_across_branches(self):
        """★응답계약: 멱등(REPAID 재호출)·정상(부분상환) 두 분기가 같은 키집합을 반환한다."""
        expected = {"status", "applied", "fully_repaid", "duplicate", "disbursed", "repaid", "outstanding"}
        # 정상 부분상환 분기.
        ag1 = _Agreement(SITE)
        db1 = _RepayDB(ag1, [_Disb(1_000_000, disbursed_at=_dt(1)), _Disb(2_000_000, disbursed_at=_dt(2))])
        res1 = _run(repay_loan(db1, SITE, ag1.id, 1_000_000))
        # 멱등(REPAID) 분기.
        ag2 = _Agreement(SITE, status="REPAID")
        db2 = _RepayDB(ag2, [_Disb(1_000_000, repaid_amount=1_000_000, disbursed_at=_dt(1))])
        res2 = _run(repay_loan(db2, SITE, ag2.id, 1_000_000))
        assert set(res1) == expected
        assert set(res2) == expected
        # 멱등 분기도 fully_repaid/outstanding 가 채워진다(이전엔 누락).
        assert res2["fully_repaid"] is True
        assert res2["outstanding"] == 0
        assert res1["duplicate"] is False

    def test_nonpositive_amount_rejected(self):
        ag = _Agreement(SITE)
        db = _RepayDB(ag, [_Disb(1_000_000)])
        with pytest.raises(HTTPException) as ei:
            _run(repay_loan(db, SITE, ag.id, 0))
        assert ei.value.status_code == 400

    def test_missing_agreement_404(self):
        db = _RepayDB(None, [])
        with pytest.raises(HTTPException) as ei:
            _run(repay_loan(db, SITE, uuid_mod.uuid4(), 1_000_000))
        assert ei.value.status_code == 404

    def test_no_disbursement_conflict(self):
        ag = _Agreement(SITE)
        db = _RepayDB(ag, [])
        with pytest.raises(HTTPException) as ei:
            _run(repay_loan(db, SITE, ag.id, 1_000_000))
        assert ei.value.status_code == 409


# ── reverse_payment: 입금취소(MATCHED→REVERSED)·회차 되돌림·멱등 ────────────────
class _Payment:
    def __init__(self, site_id, amount, matched=True, status="MATCHED", installment_id=None,
                 raw_ref=None, method="VA", allocations=None, contract_ext_id=None):
        self.id = uuid_mod.uuid4()
        self.site_id = site_id
        self.amount = amount
        self.matched = matched
        self.status = status
        self.installment_id = installment_id
        self.contract_ext_id = contract_ext_id
        self.raw_ref = raw_ref
        self.method = method
        # 다회차 충당 내역([{installment_id, applied_amount}]). None 이면 단일 installment_id 폴백.
        self.allocations = allocations


class _InstPaid:
    def __init__(self, amount, paid_amount):
        self.id = uuid_mod.uuid4()
        self.amount = amount
        self.paid_amount = paid_amount
        self.paid_at = datetime.now(UTC)


class _ReverseDB:
    """reverse_payment 의 execute 순서(결제 조회 → (MATCHED일 때) 회차 조회)를 흉내내는 가짜 세션.

    첫 execute=결제 조회, 이후 execute=회차 조회(allocations 순서대로 차례로 반환).
    insts 가 단일 객체면 매 회차조회마다 그 객체를 반환(기존 단일 폴백 테스트 호환).
    """

    def __init__(self, payment, inst=None):
        self._payment = payment
        self._insts = inst if isinstance(inst, list) else None
        self._inst = inst if not isinstance(inst, list) else None
        self._call = 0
        self._inst_idx = 0
        self.flushed = False
        self.rolled_back = False

    async def execute(self, *_a, **_k):
        self._call += 1
        if self._call == 1:
            return _FakeResult(value=self._payment)
        if self._insts is not None:
            it = self._insts[self._inst_idx] if self._inst_idx < len(self._insts) else None
            self._inst_idx += 1
            return _FakeResult(value=it)
        return _FakeResult(value=self._inst)

    async def flush(self):
        self.flushed = True

    async def rollback(self):
        self.rolled_back = True


class TestReversePayment:
    def test_reverse_matched_reverts_installment(self):
        """MATCHED 결제 취소 → 회차 paid_amount 를 결제액만큼 되돌리고 REVERSED 전이."""
        inst = _InstPaid(amount=10_000_000, paid_amount=3_000_000)
        p = _Payment(SITE, amount=3_000_000, matched=True, status="MATCHED", installment_id=inst.id)
        db = _ReverseDB(p, inst)
        res = _run(reverse_payment(db, SITE, p.id))
        assert res["status"] == "REVERSED"
        assert res["reversed"] is True
        assert res["reverted_amount"] == 3_000_000
        assert inst.paid_amount == 0
        assert inst.paid_at is None  # 다시 미납 → 완납시각 비움.
        assert p.status == "REVERSED"
        assert p.matched is False

    def test_reverse_idempotent_when_already_reversed(self):
        """이미 REVERSED 결제 재취소 → 추가 차감 0(멱등)."""
        p = _Payment(SITE, amount=1_000_000, matched=False, status="REVERSED")
        db = _ReverseDB(p)
        res = _run(reverse_payment(db, SITE, p.id))
        assert res["status"] == "REVERSED"
        assert res["reversed"] is False
        assert res.get("duplicate") is True

    def test_reverse_unmatched_no_installment_revert(self):
        """미충당(UNMATCHED) 결제 취소 → 회차 차감 없이 상태만 REVERSED."""
        p = _Payment(SITE, amount=500_000, matched=False, status="UNMATCHED", installment_id=None)
        db = _ReverseDB(p)
        res = _run(reverse_payment(db, SITE, p.id))
        assert res["status"] == "REVERSED"
        assert res["reverted_amount"] == 0
        assert p.status == "REVERSED"

    def test_reverse_missing_payment_404(self):
        db = _ReverseDB(None)
        with pytest.raises(HTTPException) as ei:
            _run(reverse_payment(db, SITE, uuid_mod.uuid4()))
        assert ei.value.status_code == 404

    def test_reverse_reason_recorded_in_raw_ref(self):
        """취소 사유는 raw_ref 에 부기되어 추적성이 보존된다(별도 감사컬럼 없음)."""
        p = _Payment(SITE, amount=1_000_000, matched=False, status="UNMATCHED", raw_ref="dep-001")
        db = _ReverseDB(p)
        _run(reverse_payment(db, SITE, p.id, reason="중복입금"))
        assert "reversed:중복입금" in (p.raw_ref or "")

    def test_reverse_multi_installment_restores_each_exactly(self):
        """★HIGH 회귀: 한 입금이 2회차에 분산 충당된 뒤 취소 → 두 회차 각각 정확히 복원.

        기존(단일 installment_id 차감)은 첫 회차에서 결제 '전액'을 빼(과차감) 둘째 회차는
        미복원(유령 잔존)이었다. allocations(회차별 applied) 기반 역배분으로 회차별 정확 차감한다.
        2회차에 6,000,000(=4,000,000+2,000,000) 분산 → 취소 시 두 회차 각각 0 복원·총 6,000,000.
        """
        i1 = _InstPaid(amount=4_000_000, paid_amount=4_000_000)
        i2 = _InstPaid(amount=2_000_000, paid_amount=2_000_000)
        allocs = [{"installment_id": str(i1.id), "applied_amount": 4_000_000},
                  {"installment_id": str(i2.id), "applied_amount": 2_000_000}]
        p = _Payment(SITE, amount=6_000_000, matched=True, status="MATCHED",
                     installment_id=i1.id, allocations=allocs)
        db = _ReverseDB(p, [i1, i2])
        res = _run(reverse_payment(db, SITE, p.id))
        assert res["reverted_amount"] == 6_000_000
        assert i1.paid_amount == 0 and i2.paid_amount == 0  # 둘째 회차 미복원 유령잔존 0.
        assert i1.paid_at is None and i2.paid_at is None
        assert p.status == "REVERSED" and p.matched is False

    def test_reverse_partial_allocation_only_reverts_applied(self):
        """allocations 의 applied_amount 만큼만 되돌린다(회차 paid_amount 가 다른 입금분을 포함해도 안전)."""
        # 회차에 5,000,000 납입 중 이 입금이 충당한 건 2,000,000 뿐 → 2,000,000 만 되돌린다.
        i1 = _InstPaid(amount=10_000_000, paid_amount=5_000_000)
        allocs = [{"installment_id": str(i1.id), "applied_amount": 2_000_000}]
        p = _Payment(SITE, amount=2_000_000, matched=True, status="MATCHED",
                     installment_id=i1.id, allocations=allocs)
        db = _ReverseDB(p, [i1])
        res = _run(reverse_payment(db, SITE, p.id))
        assert res["reverted_amount"] == 2_000_000
        assert i1.paid_amount == 3_000_000  # 다른 입금분 3,000,000 은 보존.
        assert i1.paid_at is None  # 아직 미납(3M<10M) → 완납시각 비움.

    def test_reverse_legacy_single_installment_fallback(self):
        """allocations 없는 구행 → 단일 installment_id 에서 결제 전액 차감(무회귀 폴백)."""
        i1 = _InstPaid(amount=3_000_000, paid_amount=3_000_000)
        p = _Payment(SITE, amount=3_000_000, matched=True, status="MATCHED",
                     installment_id=i1.id, allocations=None)
        db = _ReverseDB(p, i1)  # 단일 객체 → 폴백 경로.
        res = _run(reverse_payment(db, SITE, p.id))
        assert res["reverted_amount"] == 3_000_000
        assert i1.paid_amount == 0

    def test_reverse_loan_payment_blocked_409(self):
        """대출 실행분(method=LOAN) 입금은 수납 취소로 되돌릴 수 없다(대출-수납 고아 방지·409)."""
        i1 = _InstPaid(amount=5_000_000, paid_amount=5_000_000)
        p = _Payment(SITE, amount=5_000_000, matched=True, status="MATCHED",
                     installment_id=i1.id, method="LOAN")
        db = _ReverseDB(p, i1)
        with pytest.raises(HTTPException) as ei:
            _run(reverse_payment(db, SITE, p.id))
        assert ei.value.status_code == 409
        assert i1.paid_amount == 5_000_000  # 회차는 손대지 않는다.

    def test_reverse_response_keys_uniform(self):
        """★응답계약: 멱등(REVERSED 재취소)·정상(매칭 취소) 두 분기가 같은 키집합을 반환."""
        expected = {"status", "reversed", "duplicate", "reverted_amount"}
        i1 = _InstPaid(amount=1_000_000, paid_amount=1_000_000)
        p1 = _Payment(SITE, amount=1_000_000, matched=True, status="MATCHED",
                      installment_id=i1.id, allocations=[{"installment_id": str(i1.id), "applied_amount": 1_000_000}])
        res1 = _run(reverse_payment(_ReverseDB(p1, [i1]), SITE, p1.id))
        p2 = _Payment(SITE, amount=1_000_000, matched=False, status="REVERSED")
        res2 = _run(reverse_payment(_ReverseDB(p2), SITE, p2.id))
        assert set(res1) == expected
        assert set(res2) == expected
        assert res1["duplicate"] is False and res2["duplicate"] is True


# ── overdue_calc/run_overdue_all_sites: 테이블 미존재 폴백 시 aborted txn rollback ──────
class _RaiseDB:
    """첫 execute 에서 지정 SQLSTATE 로 실패시키는 가짜 세션 — aborted txn 정리(rollback) 검증용."""

    def __init__(self, sqlstate):
        self._sqlstate = sqlstate
        self.rolled_back = False

    async def execute(self, *_a, **_k):
        raise _dbapi(self._sqlstate)

    async def rollback(self):
        self.rolled_back = True

    async def flush(self):
        pass

    async def commit(self):
        pass


class TestOverdueAbortedTxnRollback:
    def test_overdue_calc_missing_table_rolls_back(self):
        """★HIGH 회귀: 테이블 미존재(42P01)로 SELECT 실패 → rollback 호출 후 0 반환.

        rollback 이 없으면 호출부의 후속 commit 이 25P02(in_failed_sql_transaction)로 500 이 되고,
        일배치는 다음 현장 SELECT 까지 같은 에러가 전파돼 잔여 현장 처리가 통째로 막힌다(cascade).
        """
        db = _RaiseDB("42P01")
        n = _run(overdue_calc(db, SITE, datetime.now(UTC)))
        assert n == 0
        assert db.rolled_back is True  # aborted txn 을 비워 후속 commit·다음 현장 SELECT 정상화.

    def test_overdue_calc_real_error_propagates_without_rollback(self):
        """권한오류(42501) 같은 실오류는 0 으로 은폐하지 않고 전파(미존재만 폴백)."""
        db = _RaiseDB("42501")
        with pytest.raises(Exception):  # noqa: B017,PT011 — DBAPIError 전파 확인(은폐 금지).
            _run(overdue_calc(db, SITE, datetime.now(UTC)))
        assert db.rolled_back is False

    def test_run_overdue_all_sites_missing_table_rolls_back(self):
        """일배치 site-list SELECT 가 미존재면 rollback 후 정상 0(skipped=missing_table)."""
        db = _RaiseDB("42703")
        res = _run(run_overdue_all_sites(db))
        assert res["sites"] == 0 and res["rows"] == 0
        assert res["skipped"] == "missing_table"
        assert res["failed"] == []
        assert db.rolled_back is True


# ── run_overdue_all_sites: per-site 격리(한 현장 실패가 배치 전체를 끊지 않음) ──────────
class _RootDB:
    """begin_nested 가 '없는' 가짜 세션(CASE B·savepoint 미지원/루트 트랜잭션 경로).

    run_overdue_all_sites 가 savepoint 없이 try/except + db.rollback() 으로만 격리하는 경로를
    검증한다. full rollback/commit 호출 횟수를 센다.
    """

    def __init__(self, site_ids):
        self._site_ids = site_ids
        self.rolled_back = 0
        self.committed = 0

    async def execute(self, *_a, **_k):
        # run_overdue_all_sites 의 첫 execute = site_id DISTINCT 목록.
        return _FakeResult(items=self._site_ids)

    async def rollback(self):
        self.rolled_back += 1

    async def commit(self):
        self.committed += 1

    async def flush(self):
        pass


class _Savepoint:
    """db.begin_nested() 가 돌려주는 savepoint 컨텍스트의 충실한 모사.

    ★실 SQLAlchemy 거동: async with 안에서 예외가 나면 __aexit__ 가 'ROLLBACK TO SAVEPOINT'로
    그 savepoint 만 되돌리고(바깥 트랜잭션·이전 현장 작업 보존) 예외를 전파한다(suppress=False).
    정상 종료면 savepoint 를 RELEASE 한다. 여기선 그 호출을 카운터로만 기록한다(전파는 그대로).
    """

    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        self._db.savepoints_entered += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            # 그 savepoint 만 되돌린다(전체 트랜잭션 rollback 아님). 예외는 전파(suppress=False).
            self._db.savepoint_rollbacks += 1
            return False
        self._db.savepoint_releases += 1
        return False


class _SavepointDB:
    """begin_nested(실 savepoint)를 구현한 가짜 세션(CASE A·savepoint 경로).

    각 현장이 savepoint 안에서 overdue_calc 를 돌고, 실패하면 그 savepoint 만 되돌린다(_Savepoint).
    ★핵심 검증: 실패 현장이 있어도 outer except 가 full db.rollback() 을 '부르지 않아야' 한다
    (savepoint __aexit__ 가 이미 그 현장만 정리했으므로 — 부르면 성공한 이전 현장까지 날린다).
    full_rollbacks(전체 롤백)·savepoint_rollbacks(부분 롤백)·committed 를 따로 센다.
    """

    def __init__(self, site_ids):
        self._site_ids = site_ids
        self.full_rollbacks = 0
        self.committed = 0
        self.savepoints_entered = 0
        self.savepoint_rollbacks = 0
        self.savepoint_releases = 0

    async def execute(self, *_a, **_k):
        return _FakeResult(items=self._site_ids)

    def begin_nested(self):
        # 실 AsyncSession.begin_nested() 처럼 'async with' 가능한 savepoint 컨텍스트를 돌려준다.
        return _Savepoint(self)

    async def rollback(self):
        # ★full(전체) rollback — savepoint 경로에선 호출되면 안 된다(과잉 롤백).
        self.full_rollbacks += 1

    async def commit(self):
        self.committed += 1

    async def flush(self):
        pass


class TestRunOverduePerSiteIsolation:
    def test_caseB_root_one_site_failure_does_not_abort_batch(self, monkeypatch):
        """★HIGH 회귀(CASE B·savepoint 미지원 루트 경로): 한 현장 실패(42P10)해도 나머지는 계속 처리.

        per-site 격리가 없으면 한 현장의 42P10 이 루프를 깨고(예외 전파) 이미 처리한 현장
        작업까지 commit 못 한 채 배치가 통째로 중단됐다. 격리 후엔 실패 현장만 failed 에
        집계하고 나머지는 rows 로 합산·commit 된다. savepoint 가 없으니 full rollback 으로 정리.
        """
        s_ok1, s_bad, s_ok2 = uuid_mod.uuid4(), uuid_mod.uuid4(), uuid_mod.uuid4()
        db = _RootDB([s_ok1, s_bad, s_ok2])

        async def _fake_calc(_db, sid, _when):
            if sid == s_bad:
                # 미존재(42P01/42703) 가 아닌 실오류(42P10) → overdue_calc 라면 전파됐을 상황을 모사.
                raise _dbapi("42P10")
            return 2  # 정상 현장은 2건 산정.

        monkeypatch.setattr(payment_svc, "overdue_calc", _fake_calc)
        res = _run(run_overdue_all_sites(db))
        # 정상 2현장만 done, 각 2건 → rows=4. 실패 현장은 failed 에 사유와 함께 집계.
        assert res["sites"] == 2
        assert res["rows"] == 4
        assert len(res["failed"]) == 1
        assert res["failed"][0]["site_id"] == str(s_bad)
        assert res["failed"][0]["reason"] == "42P10"
        # CASE B: savepoint 없으니 실패 현장에서 full rollback 1회 + 마지막 commit 1회.
        assert db.rolled_back == 1
        assert db.committed == 1

    def test_caseA_savepoint_preserves_ok_sites_via_real_savepoint(self, monkeypatch):
        """★HIGH 회귀(CASE A·실 savepoint 경로): 'ok 현장 보존 + 실패 현장 failed 집계'를 실 savepoint 로 검증.

        예전 가짜테스트는 outer except 가 부른 full rollback 카운터만 세어 'savepoint 가 진짜
        성공분을 보존하는가'를 못 봤다(false-assurance). 여기선 begin_nested 가 실제 savepoint
        컨텍스트라, 실패 현장은 그 savepoint 만 부분 롤백(savepoint_rollbacks)되고, outer except 는
        full db.rollback() 을 '절대 부르지 않아야' 한다(부르면 성공한 이전 현장까지 날아간다).
        """
        s_ok1, s_bad, s_ok2 = uuid_mod.uuid4(), uuid_mod.uuid4(), uuid_mod.uuid4()
        db = _SavepointDB([s_ok1, s_bad, s_ok2])

        async def _fake_calc(_db, sid, _when):
            if sid == s_bad:
                raise _dbapi("42P10")
            return 2

        monkeypatch.setattr(payment_svc, "overdue_calc", _fake_calc)
        res = _run(run_overdue_all_sites(db))
        assert res["sites"] == 2 and res["rows"] == 4
        assert len(res["failed"]) == 1 and res["failed"][0]["site_id"] == str(s_bad)
        # 세 현장 모두 savepoint 진입. 실패 1현장만 부분 롤백, 성공 2현장은 release.
        assert db.savepoints_entered == 3
        assert db.savepoint_rollbacks == 1
        assert db.savepoint_releases == 2
        # ★핵심: savepoint 경로에선 full(전체) rollback 을 부르지 않는다(성공분 보존). commit 1회.
        assert db.full_rollbacks == 0
        assert db.committed == 1

    def test_caseA_savepoint_all_succeed_no_failed(self, monkeypatch):
        """CASE A 무회귀: 모든 현장 정상 → savepoint 전부 release, failed 비고, full rollback 0·commit 1회."""
        s1, s2 = uuid_mod.uuid4(), uuid_mod.uuid4()
        db = _SavepointDB([s1, s2])

        async def _fake_calc(_db, _sid, _when):
            return 3

        monkeypatch.setattr(payment_svc, "overdue_calc", _fake_calc)
        res = _run(run_overdue_all_sites(db))
        assert res["sites"] == 2 and res["rows"] == 6
        assert res["failed"] == [] and res["skipped"] is None
        assert db.savepoints_entered == 2 and db.savepoint_releases == 2
        assert db.savepoint_rollbacks == 0
        assert db.full_rollbacks == 0 and db.committed == 1

    def test_caseB_root_all_sites_succeed_no_failed(self, monkeypatch):
        """CASE B 무회귀: savepoint 미지원 세션에서 모든 현장 정상 → failed 비고, full rollback 0·commit 1회."""
        s1, s2 = uuid_mod.uuid4(), uuid_mod.uuid4()
        db = _RootDB([s1, s2])

        async def _fake_calc(_db, _sid, _when):
            return 3

        monkeypatch.setattr(payment_svc, "overdue_calc", _fake_calc)
        res = _run(run_overdue_all_sites(db))
        assert res["sites"] == 2 and res["rows"] == 6
        assert res["failed"] == []
        assert res["skipped"] is None
        assert db.rolled_back == 0 and db.committed == 1


# ── overdue_calc: ON CONFLICT 부분인덱스 술어 정합(42P10 회귀 차단) ──────────────────
class _CaptureSqlDB:
    """overdue_calc 의 SQL 을 가로채는 가짜 세션 — INSERT 의 ON CONFLICT 절 텍스트를 검증한다.

    호출 순서: 현장설정 조회 → 미납 회차 목록 조회 → 회차마다 INSERT(text). INSERT 문자열을 모은다.
    rate 설정·미납 회차 1건을 흉내내 INSERT 경로가 반드시 1회 실행되게 한다.
    """

    def __init__(self):
        self._call = 0
        self.sqls: list[str] = []

        class _Cfg:
            stage_def = {"overdue_rate": 0.12}

        class _Inst:
            id = uuid_mod.uuid4()
            amount = 10_000_000
            paid_amount = 0
            due_date = datetime(2026, 1, 1, tzinfo=UTC).date()

        self._cfg = _Cfg()
        self._inst = _Inst()

    async def execute(self, stmt, *_a, **_k):
        self._call += 1
        if self._call == 1:
            return _FakeResult(value=self._cfg)
        if self._call == 2:
            return _FakeResult(items=[self._inst])
        # 이후는 INSERT(text). 컴파일된 SQL 문자열을 보관한다.
        self.sqls.append(str(getattr(stmt, "text", stmt)))
        return _FakeResult()

    async def flush(self):
        pass

    async def rollback(self):
        pass


class TestOverdueConflictPredicate:
    def test_on_conflict_has_partial_index_predicate(self):
        """★CRITICAL 회귀: ON CONFLICT 절에 부분인덱스와 같은 술어(WHERE calc_date IS NOT NULL)가 있어야 한다.

        035 마이그가 만든 UNIQUE 인덱스는 'WHERE calc_date IS NOT NULL' 부분 인덱스다. ON CONFLICT
        술어가 없으면 Postgres 가 arbiter 를 추론 못 해 42P10 이 나고(미존재 폴백에 없어) 전파→500 이
        된다. 술어를 빼면 이 테스트가 깨져 회귀를 차단한다(실제 42P10/23505 거동은 deploy-pending).
        """
        db = _CaptureSqlDB()
        n = _run(overdue_calc(db, SITE, datetime(2026, 6, 1, tzinfo=UTC)))
        assert n == 1  # 미납 회차 1건 → INSERT 1회.
        assert db.sqls, "INSERT 가 실행되지 않았습니다."
        sql = db.sqls[0]
        assert "ON CONFLICT" in sql
        # 부분 인덱스 술어가 ON CONFLICT 절에 그대로 들어 있어야 arbiter 추론이 된다.
        assert "ON CONFLICT (site_id, installment_id, calc_date) WHERE calc_date IS NOT NULL" in sql


# ── ingest_payment: 응답계약 키집합 통일(미매칭 분기) + allocations 기록 ───────────────
class _VirtualAccount:
    def __init__(self, site_id, contract_ext_id):
        self.site_id = site_id
        self.contract_ext_id = contract_ext_id
        self.va_number_enc = None


class _IngestSavepoint:
    """ingest_payment 의 raw_ref INSERT savepoint 모사 — flush 가 IntegrityError 면 그대로 전파."""

    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self._db.savepoint_rollbacks += 1
            return False
        return False


class _IngestDB:
    """ingest_payment 의 execute 순서를 흉내내는 가짜 세션.

    호출 순서: (raw_ref 있으면)중복조회 → VA 조회 → (VA 있으면)회차 목록 조회 → (동시중복 폴백 시)중복재조회.
    va=None 이면 미매칭(UNMATCHED) 분기, va 주어지면 매칭/과오납 분기.

    flush_raises(예외)가 주어지면 첫 flush 에서 그 예외를 던져 동시 INSERT 충돌(IntegrityError)을
    모사한다. dup_after 가 주어지면 충돌 후 중복재조회에서 그 행을 돌려준다(중복 응답 검증).
    """

    def __init__(self, va=None, insts=None, dup=None, has_raw_ref=False,
                 flush_raises=None, dup_after=None):
        self._va = va
        self._insts = insts or []
        self._dup = dup
        self._has_raw_ref = has_raw_ref
        self._flush_raises = flush_raises
        self._dup_after = dup_after
        self._call = 0
        self._flush_n = 0
        self.added = []
        self.flushed = False
        self.savepoint_rollbacks = 0

    async def execute(self, *_a, **_k):
        self._call += 1
        # raw_ref 가 있으면 첫 execute 는 중복조회.
        if self._has_raw_ref and self._call == 1:
            return _FakeResult(value=self._dup)
        # 그 다음(또는 raw_ref 없으면 첫) execute 는 VA 조회.
        va_call = 2 if self._has_raw_ref else 1
        if self._call == va_call:
            return _FakeResult(value=self._va)
        # 충돌 후 중복재조회(savepoint rollback 직후 1회) → dup_after 반환.
        if self._flush_raises is not None and self._flush_n >= 1:
            return _FakeResult(value=self._dup_after)
        # 이후는 회차 목록(첫 충당 루프).
        return _FakeResult(items=self._insts)

    def begin_nested(self):
        return _IngestSavepoint(self)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self._flush_n += 1
        if self._flush_raises is not None and self._flush_n == 1:
            raise self._flush_raises
        self.flushed = True


_INGEST_KEYS = {"matched", "status", "duplicate", "contract", "allocated", "unapplied"}


class TestIngestPaymentContract:
    def test_zero_amount_rejected_400(self):
        db = _IngestDB(va=None)
        with pytest.raises(HTTPException) as ei:
            _run(ingest_payment(db, SITE, {"va_number": "1", "amount": 0}))
        assert ei.value.status_code == 400

    def test_unmatched_branch_uniform_keys(self):
        """★응답계약: VA 미발견(미매칭) 분기도 6개 공통 키집합을 반환한다."""
        db = _IngestDB(va=None)
        res = _run(ingest_payment(db, SITE, {"va_number": "404acct", "amount": 1_000_000}))
        assert set(res) == _INGEST_KEYS
        assert res["matched"] is False and res["status"] == "UNMATCHED"
        assert res["unapplied"] == 1_000_000 and res["allocated"] == 0

    def test_matched_branch_records_allocations(self):
        """매칭 분기: 입금이 2회차에 분산 충당되면 allocations 에 회차별 applied 가 기록된다."""
        cid = uuid_mod.uuid4()
        va = _VirtualAccount(SITE, cid)

        class _I:
            def __init__(self, seq, amount, paid):
                self.id = uuid_mod.uuid4()
                self.seq = seq
                self.amount = amount
                self.paid_amount = paid
                self.paid_at = None
        i1 = _I(1, 4_000_000, 0)
        i2 = _I(2, 3_000_000, 0)
        db = _IngestDB(va=va, insts=[i1, i2])
        res = _run(ingest_payment(db, SITE, {"va_number": "ok", "amount": 6_000_000}))
        assert set(res) == _INGEST_KEYS
        assert res["matched"] is True and res["allocated"] == 6_000_000
        # 1회차 4,000,000 완납 + 2회차 2,000,000 부분충당.
        assert i1.paid_amount == 4_000_000 and i2.paid_amount == 2_000_000
        # 새로 추가된 SalesPayment 의 allocations 에 회차별 충당액이 기록됐다.
        pay = db.added[-1]
        assert pay.allocations == [
            {"installment_id": str(i1.id), "applied_amount": 4_000_000},
            {"installment_id": str(i2.id), "applied_amount": 2_000_000},
        ]

    def test_surplus_branch_when_all_installments_paid(self):
        """★MEDIUM 회귀(과오납 silent 오표기 차단): VA 는 있으나 모든 회차 완납(due<=0)이면
        충당 0 → status='SURPLUS'/matched=False/unapplied=전액. 예전엔 allocations=[] 인데도
        matched=True/MATCHED 로 '회차 충당됨' 거짓 표기됐다. 금액(amount)은 보존(손실 0)."""
        cid = uuid_mod.uuid4()
        va = _VirtualAccount(SITE, cid)

        class _I:
            def __init__(self, seq, amount, paid):
                self.id = uuid_mod.uuid4()
                self.seq = seq
                self.amount = amount
                self.paid_amount = paid
                self.paid_at = datetime.now(UTC)
        # 두 회차 모두 완납(due=0).
        i1 = _I(1, 4_000_000, 4_000_000)
        i2 = _I(2, 3_000_000, 3_000_000)
        db = _IngestDB(va=va, insts=[i1, i2])
        res = _run(ingest_payment(db, SITE, {"va_number": "ok", "amount": 1_000_000}))
        assert set(res) == _INGEST_KEYS
        assert res["matched"] is False and res["status"] == "SURPLUS"
        assert res["allocated"] == 0 and res["unapplied"] == 1_000_000
        # 회차 paid_amount 는 건드리지 않는다(완납분 그대로).
        assert i1.paid_amount == 4_000_000 and i2.paid_amount == 3_000_000
        # 기록된 SalesPayment 도 SURPLUS·matched=False·금액 보존.
        pay = db.added[-1]
        assert pay.status == "SURPLUS" and pay.matched is False
        assert int(pay.amount) == 1_000_000  # 금액 손실 0(환급/재배정 근거).
        assert pay.allocations is None

    def test_concurrent_dup_integrity_error_returns_duplicate_and_reverts(self):
        """★MEDIUM 회귀(이중충당 DB게이트·TOCTOU): 선조회 통과 후 동시 콜백이 같은 raw_ref 를 먼저
        INSERT 하면 flush 가 IntegrityError(23505) → savepoint 만 롤백, 충당했던 회차를 정확히
        되돌리고(이중 충당 0) 기존 행을 재조회해 중복으로 반환한다."""
        cid = uuid_mod.uuid4()
        va = _VirtualAccount(SITE, cid)

        class _I:
            def __init__(self, seq, amount, paid):
                self.id = uuid_mod.uuid4()
                self.seq = seq
                self.amount = amount
                self.paid_amount = paid
                self.paid_at = None
        i1 = _I(1, 5_000_000, 0)
        # 동시 콜백이 먼저 넣은 기존 행(matched/MATCHED).
        existing = _Payment(SITE, amount=3_000_000, matched=True, status="MATCHED", raw_ref="dep-xyz")
        ierr = IntegrityError("INSERT", {}, _FakeOrigError("23505"))
        db = _IngestDB(va=va, insts=[i1], has_raw_ref=True, dup=None,
                       flush_raises=ierr, dup_after=existing)
        res = _run(ingest_payment(db, SITE, {"va_number": "ok", "amount": 3_000_000, "raw_ref": "dep-xyz"}))
        assert set(res) == _INGEST_KEYS
        assert res["duplicate"] is True and res["status"] == "MATCHED"
        assert res["matched"] is True and res["allocated"] == 3_000_000
        # savepoint 만 1회 롤백되고(전체 롤백 아님), 회차 가산은 정확히 되돌려진다(이중 충당 0).
        assert db.savepoint_rollbacks == 1
        assert i1.paid_amount == 0 and i1.paid_at is None

    def test_raw_ref_insert_uses_savepoint_flush(self):
        """raw_ref 가 있으면 INSERT 를 savepoint 안에서 flush 한다(동시 23505 캡처 경로 보장)."""
        cid = uuid_mod.uuid4()
        va = _VirtualAccount(SITE, cid)

        class _I:
            def __init__(self, seq, amount, paid):
                self.id = uuid_mod.uuid4()
                self.seq = seq
                self.amount = amount
                self.paid_amount = paid
                self.paid_at = None
        i1 = _I(1, 5_000_000, 0)
        db = _IngestDB(va=va, insts=[i1], has_raw_ref=True, dup=None)
        res = _run(ingest_payment(db, SITE, {"va_number": "ok", "amount": 3_000_000, "raw_ref": "dep-new"}))
        # 충돌 없으면 정상 매칭(중복 아님)·savepoint 롤백 0.
        assert res["matched"] is True and res["duplicate"] is False
        assert res["allocated"] == 3_000_000
        assert db.savepoint_rollbacks == 0
        assert db.flushed is True


def test_loan_service_importable():
    """배선 회귀 가드: 라우터가 import 하는 repay_loan 심볼이 실제 존재한다."""
    assert callable(loan_svc.repay_loan)


def test_payment_money_path_symbols_importable():
    """배선 회귀 가드: 라우터가 import 하는 머니패스 심볼(reverse_payment 등)이 실제 존재한다."""
    assert callable(payment_svc.reverse_payment)
    assert callable(payment_svc.overdue_calc)
    assert callable(payment_svc.run_overdue_all_sites)
