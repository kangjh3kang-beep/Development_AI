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
import uuid as uuid_mod
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
    """모듈전역 1회 DDL 게이트를 매 테스트 reset — 다른 테스트의 부작용이 새지 않게 격리.

    engine._TAXPREF_READY 와 extension._PAYOUT_COLS_READY 둘 다 리셋한다(테스트 격리).
    단, settle_summary/get_node_tax_type 단위테스트가 별도 세션(async_session_factory)으로
    실제 DDL 을 열지 않도록, '이미 보장됨'(True)으로 두고 시작한다 — DB 없는 순수로직 테스트라
    DDL 경로를 타지 않게 막는다(필요한 테스트는 개별적으로 False 로 내려 검증).
    """
    from app.services.sales.commission import extension
    engine._TAXPREF_READY = True
    extension._PAYOUT_COLS_READY = True
    yield
    engine._TAXPREF_READY = False
    extension._PAYOUT_COLS_READY = False


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
        # 4번째 이후: get_node_tax_type 의 SELECT tax_type(ensure_tax_pref 는 _TAXPREF_READY=True 라
        # 별도 DDL 세션을 열지 않고 즉시 반환). tax_type 조회는 .first() 를 쓰므로 None(→ WITHHOLDING).
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


# ── payout_net 음수 gross 가드(silent-fail 차단) ────────────────────────────────
class TestPayoutNetNegativeGuard:
    def test_negative_gross_raises_withholding(self):
        """★음수 gross 는 0 으로 흡수하지 않고 ValueError 로 거부(역분개·음수세액 방지)."""
        with pytest.raises(ValueError, match="음수"):
            payout_net(Decimal(-1))

    def test_negative_gross_raises_vat(self):
        with pytest.raises(ValueError, match="음수"):
            payout_net(Decimal(-100), tax_type="VAT")

    def test_zero_gross_is_allowed(self):
        """0 은 정상(미지급 0). 가드는 음수만 막는다."""
        assert payout_net(Decimal(0))["net"] == Decimal(0)


# ── set_node_tax_type: 교차현장 덮어쓰기 차단(현장 격리) ─────────────────────────
class _TaxPrefDB:
    """set_node_tax_type 의 (소유 site_id SELECT → INSERT…ON CONFLICT) 2회 execute 를 흉내낸다.

    owner_site 가 주어지면 기존 행 소유 현장으로 반환(.first() → (owner_site,)). None 이면 행 없음.
    _TAXPREF_READY=True 라 ensure_tax_pref 는 DB 를 건드리지 않으므로 execute 는 위 2회만 온다.
    """
    def __init__(self, owner_site=None):
        self._owner_site = owner_site
        self._call = 0
        self.insert_called = False

    async def execute(self, *_a, **_k):
        self._call += 1
        if self._call == 1:  # SELECT site_id WHERE node_id
            return _FakeFirst((self._owner_site,) if self._owner_site is not None else None)
        self.insert_called = True  # INSERT … ON CONFLICT
        return _FakeFirst(None)


class TestSetNodeTaxTypeIsolation:
    async def test_cross_site_overwrite_rejected(self):
        """★타 현장(site-A) 소유 노드를 site-B 가 덮어쓰려 하면 거부(교차현장 무단변경 차단)."""
        db = _TaxPrefDB(owner_site="site-A")
        with pytest.raises(ValueError, match="다른 현장"):
            await engine.set_node_tax_type(db, "site-B", "node-1", "VAT")
        assert db.insert_called is False  # 거부 → INSERT 미수행

    async def test_same_site_overwrite_ok(self):
        """동일 현장 소유면 갱신 허용."""
        db = _TaxPrefDB(owner_site="site-A")
        tt = await engine.set_node_tax_type(db, "site-A", "node-1", "VAT")
        assert tt == "VAT"
        assert db.insert_called is True

    async def test_new_node_inserts(self):
        """기존 행 없으면(신규 노드) 정상 삽입."""
        db = _TaxPrefDB(owner_site=None)
        tt = await engine.set_node_tax_type(db, "site-A", "node-1", "WITHHOLDING")
        assert tt == "WITHHOLDING"
        assert db.insert_called is True

    async def test_invalid_tax_type_rejected(self):
        db = _TaxPrefDB(owner_site=None)
        with pytest.raises(ValueError, match="WITHHOLDING"):
            await engine.set_node_tax_type(db, "site-A", "node-1", "FOO")

    async def test_on_conflict_carries_site_id_guard(self):
        """★TOCTOU 회귀가드: ON CONFLICT DO UPDATE 에 'site_id=' WHERE 조건이 박혀 있어야
        경합으로 타 현장 행이 끼어들어도 무단 덮어쓰기가 차단된다(SELECT 선검사 의존 제거)."""
        captured = {}

        class _CaptureDB:
            def __init__(self):
                self._call = 0

            async def execute(self, stmt, *_a, **_k):
                self._call += 1
                if self._call == 1:  # SELECT site_id WHERE node_id (기존 행 없음)
                    return _FakeFirst(None)
                captured["sql"] = str(getattr(stmt, "text", stmt))  # INSERT … ON CONFLICT
                return _FakeFirst(None)

        db = _CaptureDB()
        await engine.set_node_tax_type(db, "site-A", "node-1", "VAT")
        sql = captured["sql"].upper()
        assert "ON CONFLICT" in sql
        # DO UPDATE 절 뒤에 site_id 가드(WHERE …SITE_ID=) 가 있어야 한다.
        assert "DO UPDATE" in sql
        assert "WHERE SALES_COMMISSION_TAX_PREF.SITE_ID=:S" in sql


# ── get_node_tax_type: 현장 격리 조회(타 현장 노드 세금유형 미열람) ─────────────────
class _NodeTaxDB:
    """get_node_tax_type 의 SELECT tax_type 1회 execute 를 흉내낸다. 격리된 SELECT 가
    site_id 와 node_id 를 함께 걸면(매칭되는 본 현장 행이 없으면) row=None → WITHHOLDING 폴백.

    captured["sql"] 에 실제 SELECT 문을 담아 'WHERE 에 site_id 조건이 함께 걸렸는지' 검증한다.
    _TAXPREF_READY=True 라 ensure_tax_pref 는 별도 DDL 세션을 열지 않는다."""
    def __init__(self, row=None):
        self._row = row
        self.captured = {}

    async def execute(self, stmt, *_a, **_k):
        self.captured["sql"] = str(getattr(stmt, "text", stmt))
        return _FakeFirst(self._row)


class TestGetNodeTaxTypeIsolation:
    async def test_site_id_added_to_where(self):
        """★현장 격리: site_id 를 주면 SELECT WHERE 에 node_id 와 site_id 가 함께 걸린다."""
        db = _NodeTaxDB(row=None)
        await engine.get_node_tax_type(db, "node-1", site_id="site-A")
        sql = db.captured["sql"].upper()
        assert "WHERE NODE_ID=:N AND SITE_ID=:S" in sql

    async def test_other_site_row_not_read(self):
        """★타 현장 노드 세금유형 미열람: 본 현장 행이 없으면(타 현장 소유) row=None → 기본 WITHHOLDING.
        (격리 SELECT 가 site_id 로 걸러 타 현장 VAT 설정을 잘못 적용하지 않음.)"""
        db = _NodeTaxDB(row=None)  # site-A 로 조회했으나 매칭 행 없음(행은 site-B 소유라 가정)
        tt = await engine.get_node_tax_type(db, "node-1", site_id="site-A")
        assert tt == "WITHHOLDING"  # 타 현장 VAT 가 새지 않음

    async def test_same_site_row_read(self):
        """본 현장 소유 행이면 정상 열람(VAT)."""
        db = _NodeTaxDB(row=("VAT",))
        tt = await engine.get_node_tax_type(db, "node-1", site_id="site-A")
        assert tt == "VAT"

    async def test_none_node_short_circuits(self):
        """node_id 가 None 이면 DB 조회 없이 WITHHOLDING(방어)."""
        class _NeverDB:
            async def execute(self, *_a, **_k):
                raise AssertionError("node_id=None 이면 DB 를 건드리면 안 됨")

        assert await engine.get_node_tax_type(_NeverDB(), None, site_id="site-A") == "WITHHOLDING"


# ── run_due_payouts: 도래분 지급 스케줄 현장 격리(교차현장 과처리 차단) ──────────────
class TestRunDuePayoutsIsolation:
    async def test_schedule_query_filters_by_site(self):
        """★교차현장 과처리 회귀가드: 도래분 스케줄 조회가 schedule→split→event 를 조인해
        event.site_id 로 격리한다. 행이 없으면(타 현장 due) 지급 0 — 타 현장 due 미처리."""
        from datetime import date

        from app.services.sales.commission import extension

        captured = {}

        class _NoDueDB:
            """현장 격리 SELECT 가 본 현장 due 0건을 돌려주는 세션(타 현장 due 는 안 잡힘)."""
            async def execute(self, stmt, *_a, **_k):
                captured["sql"] = str(getattr(stmt, "statement", stmt))
                return _ScalarsResult([])

            async def flush(self):
                pass

        extension._PAYOUT_COLS_READY = True  # 컬럼보장 DDL 세션 미진입(순수로직)
        db = _NoDueDB()
        paid = await extension.run_due_payouts(db, "site-A", date(2026, 1, 1))
        assert paid == 0  # 본 현장 due 0건 → 지급 0 (타 현장 due 일괄지급 안 함)
        sql = captured["sql"].upper()
        # 조인+격리 회귀가드: events 조인과 site_id 격리 조건이 쿼리에 박혀 있어야 한다.
        assert "SALES_COMMISSION_EVENTS" in sql
        assert "SITE_ID" in sql


class _ScalarsResult:
    """ORM select 결과의 .scalars() 만 쓰는 run_due_payouts 용 가짜 결과."""
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self._rows


# ── ensure_tax_pref: 호출자 세션을 건드리지 않음(부분커밋 차단) ───────────────────
class TestEnsureTaxPrefIsolation:
    async def test_ready_gate_skips_caller_session(self):
        """게이트가 닫혀(_TAXPREF_READY=True) 있으면 호출자 세션에 어떤 execute/commit 도 하지 않는다."""
        class _SpyDB:
            def __init__(self):
                self.calls = 0
                self.commits = 0

            async def execute(self, *_a, **_k):
                self.calls += 1
                return _FakeFirst(None)

            async def commit(self):
                self.commits += 1

        engine._TAXPREF_READY = True
        db = _SpyDB()
        await engine.ensure_tax_pref(db)
        assert db.calls == 0 and db.commits == 0  # 호출자 세션 무접촉


# ── _ledger 봉인 실패: audit ok:False 도 최종 WARN 으로 강등(은폐의 재은폐 차단) ──
class TestLedgerSealFailure:
    async def test_audit_ok_false_degrades_to_warning(self, monkeypatch):
        """★원장 봉인 실패 + audit 승격도 {ok:False}(쿼터초과) → 무음소실 없이 최종 WARN 1줄 보존.

        기존 테스트는 '예외없이 완주'만 봤는데, 그것만으로는 '무음 소실(silent drop)'을 못 잡는다
        (강등 로그를 통째로 지워도 통과). 그래서 structlog.testing.capture_logs 로 로그를 봉인해
        '봉인+audit 동시 실패 → WARN 1줄(ledger_event/seal_reason/audit_reason 키 포함) 방출'을
        명시적으로 단언한다(무음소실 회귀가드)."""
        from structlog.testing import capture_logs

        from app.api.endpoints.sales import commission_agreement as ca

        # analysis_ledger_service.append_analysis 가 {ok:False}(봉인 실패) 반환하도록 패치.
        class _LedgerStub:
            async def append_analysis(self, **_k):
                return {"ok": False, "quota_exceeded": True, "message": "quota_exceeded"}

        # audit_ledger.append_audit 도 {ok:False} 반환(같은 쿼터에 걸림) → 재은폐 위험 지점.
        class _AuditStub:
            async def append_audit(self, **_k):
                return {"ok": False, "quota_exceeded": True}

        import app.services.ledger as ledger_pkg
        monkeypatch.setattr(ledger_pkg, "analysis_ledger_service", _LedgerStub(), raising=False)
        monkeypatch.setattr(ledger_pkg, "audit_ledger", _AuditStub(), raising=False)

        class _Ctx:
            class _U:
                id = "user-1"
                tenant_id = "tenant-1"
            user = _U()
            site_id = "site-1"

        with capture_logs() as logs:
            await ca._ledger(_Ctx(), uuid_mod.uuid4(), "confirmed", {"x": 1})
        # ① 봉인 실패 → audit 승격 시도 WARN, ② audit 도 실패 → 최종 강등 WARN. 둘 다 봉인 보존.
        warns = [e for e in logs if e.get("log_level") == "warning"]
        assert warns, "봉인+audit 동시 실패인데 WARN 로그가 한 줄도 없음(무음 소실)"
        # 최종 강등 줄(sealed_failed_and_audit_skipped): 봉인사유·audit사유·도메인이벤트 키 보존 검증.
        final = [w for w in warns if "sealed_failed_and_audit_skipped" in w.get("event", "")]
        assert len(final) == 1, "최종 강등 WARN(sealed_failed_and_audit_skipped)이 정확히 1줄이어야 함"
        w = final[0]
        assert w.get("ledger_event") == "confirmed"  # 도메인 이벤트(event= 키 충돌 회피)
        assert w.get("seal_reason") == "quota_exceeded"  # 봉인 실패 사유 보존
        assert w.get("audit_reason") == "quota_exceeded"  # audit 재은폐 사유 보존

    async def test_audit_ok_true_no_degrade(self, monkeypatch):
        """봉인 실패하더라도 audit 승격이 정상(ok 미반환 dict)이면 추가 강등 로그 없이 통과."""
        from app.api.endpoints.sales import commission_agreement as ca

        class _LedgerStub:
            async def append_analysis(self, **_k):
                return {"ok": False, "message": "append_failed"}

        class _AuditStub:
            def __init__(self):
                self.called = False

            async def append_audit(self, **_k):
                self.called = True
                return {"ok": True}

        audit = _AuditStub()
        import app.services.ledger as ledger_pkg
        monkeypatch.setattr(ledger_pkg, "analysis_ledger_service", _LedgerStub(), raising=False)
        monkeypatch.setattr(ledger_pkg, "audit_ledger", audit, raising=False)

        class _Ctx:
            class _U:
                id = "user-1"
                tenant_id = "tenant-1"
            user = _U()
            site_id = "site-1"

        await ca._ledger(_Ctx(), uuid_mod.uuid4(), "created", {"x": 1})
        assert audit.called is True  # 봉인 실패 → audit 승격 호출됨
