"""#3 수수료·더치페이·원천징수 — 순수로직 회귀 안전망(Wave1 P0).

DB 무관(또는 가짜세션) 단위테스트로 다음 회귀를 영구 차단한다.
- payout_net: 원천징수 3.3%/부가세 10% 산식 + '원 미만 절사'(ROUND_DOWN) 회귀.
- _missing_object_sqlstate: 42P01/42703 만 미존재(정상0)로 분류, 그 외는 None(전파신호).
- settle_summary: 지급집계 실패를 '미지급 0'으로 은폐하지 않음 —
    테이블 미존재(42P01)만 paid=0 폴백, 그 외 실오류는 전파(silent-fail 차단).
- _assert_pool_not_exceeded: 정산 풀(pool_total) 초과 시 ValueError(과지급 차단), 이내면 통과.
- _validate_participants(더치페이): 비율합 100%/금액합=총액 검증 + 비율·금액 혼용 차단.
- 모듈전역 1회 게이트(_TAXPREF_READY 등)는 fixture 로 매 테스트 reset(test isolation).
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

from app.api.endpoints.sales.commission_agreement import (  # noqa: E402
    Participant,
    _validate_participants,
)
from app.services.sales.commission import engine  # noqa: E402
from app.services.sales.commission.engine import (  # noqa: E402
    _amount,
    _assert_pool_not_exceeded,
    _missing_object_sqlstate,
    payout_net,
    settle_summary,
)


@pytest.fixture(autouse=True)
def _reset_ddl_gates():
    """모듈전역 1회 DDL 게이트를 매 테스트 reset — 다른 테스트의 부작용이 새지 않게 격리."""
    engine._TAXPREF_READY = False
    yield
    engine._TAXPREF_READY = False


# ── payout_net: 원천징수/부가세 산식 + 원 미만 절사 ──────────────────────────────
class TestPayoutNet:
    def test_withholding_basic_3_3(self):
        """3.3% 원천징수: gross 1,000,000 → 원천 33,000, 실수령 967,000."""
        r = payout_net(Decimal(1_000_000))
        assert r["tax_type"] == "WITHHOLDING"
        assert r["withholding"] == Decimal(33_000)
        assert r["net"] == Decimal(967_000)
        assert r["total_paid"] == Decimal(1_000_000)
        assert r["vat"] == Decimal(0)

    def test_withholding_truncates_won(self):
        """★핵심 회귀: 원천징수는 '원 미만 절사'(ROUND_DOWN). 반올림(HALF_EVEN)이면 1원 과대.
        gross 1,000,015 × 3.3% = 33,000.495 → 절사 33,000(반올림이면 33,000 동일하지만
        gross 1,000,016 × 3.3% = 33,000.528 → 절사 33,000, 반올림이면 33,001)."""
        assert payout_net(Decimal(1_000_016))["withholding"] == Decimal(33_000)
        # 절사이므로 .9 라도 버린다.
        assert payout_net(Decimal(1_000_030))["withholding"] == Decimal(33_000)  # 33,000.99→33,000

    def test_vat_adds_10pct_and_truncates(self):
        """VAT: 공급가 gross 에 10% 가산. 원천징수 없음. net=공급가, total_paid=공급가+vat."""
        r = payout_net(Decimal(1_000_005), tax_type="VAT")
        assert r["tax_type"] == "VAT"
        assert r["vat"] == Decimal(100_000)  # 100,000.5 → 절사 100,000
        assert r["withholding"] == Decimal(0)
        assert r["net"] == Decimal(1_000_005)
        assert r["total_paid"] == Decimal(1_100_005)

    def test_zero_gross(self):
        r = payout_net(Decimal(0))
        assert r["withholding"] == Decimal(0)
        assert r["net"] == Decimal(0)


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


# ── settle_summary: silent-fail 차단(미존재만 0, 그 외 전파) ────────────────────
class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _SettleDB:
    """settle_summary 의 execute 호출 순서를 흉내내는 가짜 세션.

    호출 순서: ①earned ②contracts ③paid(여기서 raise 가능) ④(폴백 시) get_node_tax_type 경로.
    paid_exc 가 주어지면 3번째 execute 에서 그 예외를 던진다(테이블 미존재/실오류 시나리오).
    """
    def __init__(self, earned, contracts, paid, paid_exc=None):
        self._seq = [_FakeResult(earned), _FakeResult(contracts)]
        self._paid = _FakeResult(paid)
        self._paid_exc = paid_exc
        self._call = 0
        self.rolled_back = False

    async def execute(self, *_a, **_k):
        self._call += 1
        if self._call <= 2:
            return self._seq[self._call - 1]
        if self._call == 3:
            if self._paid_exc is not None:
                raise self._paid_exc
            return self._paid
        # 4번째 이후: get_node_tax_type 의 ensure_tax_pref(DDL/commit) + SELECT tax_type.
        # tax_type 조회는 .first() 를 쓰므로 None 반환(→ 기본 WITHHOLDING).
        return _FakeFirst(None)

    async def commit(self):
        pass

    async def rollback(self):
        self.rolled_back = True


class _FakeFirst:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class TestSettleSummaryFallback:
    async def test_missing_payout_table_falls_back_to_zero(self):
        """지급 테이블 미존재(42P01) → paid=0 폴백(정상 0). outstanding=earned."""
        db = _SettleDB(earned=500_000, contracts=2, paid=0, paid_exc=_dbapi("42P01"))
        out = await settle_summary(db, "site-x", "node-y")
        assert out["paid_gross"] == 0
        assert out["earned_gross"] == 500_000
        assert out["outstanding_gross"] == 500_000
        assert db.rolled_back is True  # 트랜잭션 오염 방지 롤백 수행

    async def test_real_error_propagates_not_silenced(self):
        """★silent-fail 회귀: 권한오류(42501) 등 실오류는 '미지급 0'으로 은폐하지 않고 전파."""
        db = _SettleDB(earned=500_000, contracts=2, paid=0, paid_exc=_dbapi("42501"))
        with pytest.raises(DBAPIError):
            await settle_summary(db, "site-x", "node-y")
        assert db.rolled_back is True

    async def test_normal_paid_subtracts(self):
        """정상 경로: 기발생 500,000 − 기지급 200,000 = 미지급 300,000."""
        db = _SettleDB(earned=500_000, contracts=2, paid=200_000)
        out = await settle_summary(db, "site-x", "node-y")
        assert out["paid_gross"] == 200_000
        assert out["outstanding_gross"] == 300_000
        # 미지급 300,000 에 3.3% 원천 → 정산 분개에 반영(절사).
        assert out["settlement"]["withholding"] == 9_900


# ── _assert_pool_not_exceeded: 정산 풀 초과 차단(과지급 방지) ────────────────────
class _Master:
    def __init__(self, mid, pool_total):
        self.id = mid
        self.pool_total = pool_total


class _PoolDB:
    """_assert_pool_not_exceeded 의 (FOR UPDATE 락 → 누적합 SELECT) 2회 execute 를 흉내낸다."""
    def __init__(self, used_sum):
        self._used = used_sum
        self._call = 0

    async def execute(self, *_a, **_k):
        self._call += 1
        if self._call == 1:
            return _FakeResult(None)  # FOR UPDATE (반환 무시)
        return _FakeResult(self._used)  # 누적 발생액 합계


class TestPoolGuard:
    async def test_no_pool_total_skips(self):
        """pool_total 미설정(RATE/FIXED 단가 모델) → 검사 없이 통과."""
        db = _PoolDB(used_sum=999)
        await _assert_pool_not_exceeded(db, _Master("m1", None), "site-x", Decimal(10_000))
        assert db._call == 0  # 쿼리 자체를 안 함

    async def test_within_pool_passes(self):
        """누적 600,000 + 신규 300,000 = 900,000 ≤ 풀 1,000,000 → 통과."""
        db = _PoolDB(used_sum=600_000)
        await _assert_pool_not_exceeded(db, _Master("m1", 1_000_000), "site-x", Decimal(300_000))

    async def test_exceeds_pool_raises(self):
        """★과지급 차단 회귀: 누적 800,000 + 신규 300,000 = 1,100,000 > 풀 1,000,000 → ValueError."""
        db = _PoolDB(used_sum=800_000)
        with pytest.raises(ValueError, match="정산 풀"):
            await _assert_pool_not_exceeded(db, _Master("m1", 1_000_000), "site-x", Decimal(300_000))

    async def test_exact_pool_boundary_passes(self):
        """경계: 누적 700,000 + 신규 300,000 = 1,000,000 = 풀 → 통과(초과 아님)."""
        db = _PoolDB(used_sum=700_000)
        await _assert_pool_not_exceeded(db, _Master("m1", 1_000_000), "site-x", Decimal(300_000))


# ── _amount: 배분 규칙(FIXED 고정액 / RATE 비율) ───────────────────────────────
class _Rule:
    def __init__(self, basis, value):
        self.basis = basis
        self.value = value


class TestAmount:
    def test_none_rule_is_zero(self):
        assert _amount(None, Decimal(1_000_000)) == Decimal(0)

    def test_fixed(self):
        assert _amount(_Rule("FIXED", 50_000), Decimal(1_000_000)) == Decimal(50_000)

    def test_rate(self):
        """RATE 0.1 × 총액 1,000,000 = 100,000."""
        assert _amount(_Rule("RATE", 0.1), Decimal(1_000_000)) == Decimal(100_000)


# ── _validate_participants(더치페이): 비율합 100%/금액합=총액 검증 ───────────────
def _p(node_id="n1", ratio=None, amount=None):
    import uuid
    return Participant(node_id=uuid.uuid4() if node_id else None, ratio=ratio, amount=amount)


class TestDutchPayValidation:
    def test_ratio_sums_to_100_passes(self):
        parts = [_p(ratio=40), _p(ratio=60)]
        assert _validate_participants(parts, 1_000_000) == "RATIO"

    def test_ratio_not_100_rejected(self):
        """비율 합 100% 아니면 400(분배합 검증)."""
        with pytest.raises(HTTPException) as ei:
            _validate_participants([_p(ratio=40), _p(ratio=50)], 1_000_000)
        assert ei.value.status_code == 400

    def test_amount_sum_equals_total_passes(self):
        parts = [_p(amount=600_000), _p(amount=400_000)]
        assert _validate_participants(parts, 1_000_000) == "AMOUNT"

    def test_amount_sum_mismatch_rejected(self):
        """금액 합이 총액과 다르면 400(총액 초과/미달 차단)."""
        with pytest.raises(HTTPException):
            _validate_participants([_p(amount=600_000), _p(amount=300_000)], 1_000_000)

    def test_ratio_and_amount_mixed_rejected(self):
        """비율·금액 혼용 차단(분배 기준 단일화)."""
        with pytest.raises(HTTPException):
            _validate_participants([_p(ratio=50), _p(amount=500_000)], 1_000_000)

    def test_empty_participants_rejected(self):
        with pytest.raises(HTTPException):
            _validate_participants([], 1_000_000)

    def test_negative_ratio_rejected(self):
        with pytest.raises(HTTPException):
            _validate_participants([_p(ratio=120), _p(ratio=-20)], 1_000_000)
