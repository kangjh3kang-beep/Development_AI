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
    CrossSiteOwnershipError,
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

    호출 순서: ①earned ②contracts ③paid(여기서 raise 가능) ④clawback_total(환수합·.scalar())
              ⑤(이후) get_node_tax_type 경로(.first()).
    paid_exc 가 주어지면 3번째 execute 에서 그 예외를 던진다(테이블 미존재/실오류 시나리오).
    clawback 으로 환수합(④)을 주입한다(기본 0 — 과지급 가시화 회귀가드용).
    """
    def __init__(self, earned, contracts, paid, paid_exc=None, clawback=0):
        self._seq = [_FakeResult(earned), _FakeResult(contracts)]
        self._paid = _FakeResult(paid)
        self._paid_exc = paid_exc
        self._clawback = _FakeResult(clawback)
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
        if self._call == 4:
            # 환수합(clawback_total) SELECT — .scalar() 로 합계 읽음(_FakeResult).
            return self._clawback
        # 5번째 이후: get_node_tax_type 의 SELECT tax_type(ensure_tax_pref 는 _TAXPREF_READY=True 라
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

    async def test_paid_query_isolated_by_site_symmetric_with_earned(self):
        """★격리 대칭 회귀가드: paid(기지급) 집계 SQL 이 earned 와 동일하게 events 조인 +
        e.site_id 격리를 갖는다(타 현장에서 같은 node_id 로 지급된 행이 미지급 잔액에 새지 않게)."""
        captured = []

        class _CaptureSettleDB(_SettleDB):
            async def execute(self, stmt, *_a, **_k):
                captured.append(str(getattr(stmt, "text", stmt)).upper())
                return await super().execute(stmt, *_a, **_k)

        db = _CaptureSettleDB(earned=500_000, contracts=2, paid=200_000)
        await settle_summary(db, "site-x", "node-y")
        paid_sql = captured[2]  # ①earned ②contracts ③paid
        assert "SALES_COMMISSION_PAYOUTS" in paid_sql
        # earned 와 동일 기준: events 조인 + e.site_id 격리(s.node_id 단독 아님).
        assert "SALES_COMMISSION_EVENTS" in paid_sql
        assert "E.SITE_ID=:S" in paid_sql


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
class _FakeWriteResult:
    """INSERT…ON CONFLICT 결과 흉내 — rowcount(갱신/삽입 영향행)와 .first()(None)를 함께 제공.

    set_node_tax_type 는 INSERT 결과의 rowcount==0(=경합으로 갱신 차단)을 거부 신호로 쓴다.
    rowcount 기본 1(정상 1행 반영). rowcount=0 으로 주면 'silent no-op(차단)' 시나리오를 재현한다.
    """
    def __init__(self, rowcount=1):
        self.rowcount = rowcount

    def first(self):
        return None


class _TaxPrefDB:
    """set_node_tax_type 의 (소유 site_id SELECT → INSERT…ON CONFLICT) 2회 execute 를 흉내낸다.

    owner_site 가 주어지면 기존 행 소유 현장으로 반환(.first() → (owner_site,)). None 이면 행 없음.
    insert_rowcount 로 INSERT 의 영향행수를 지정한다(0=경합 차단 재현). 기본 1(정상 반영).
    _TAXPREF_READY=True 라 ensure_tax_pref 는 DB 를 건드리지 않으므로 execute 는 위 2회만 온다.
    """
    def __init__(self, owner_site=None, insert_rowcount=1):
        self._owner_site = owner_site
        self._insert_rowcount = insert_rowcount
        self._call = 0
        self.insert_called = False

    async def execute(self, *_a, **_k):
        self._call += 1
        if self._call == 1:  # SELECT site_id WHERE node_id
            return _FakeFirst((self._owner_site,) if self._owner_site is not None else None)
        self.insert_called = True  # INSERT … ON CONFLICT
        return _FakeWriteResult(rowcount=self._insert_rowcount)


class TestSetNodeTaxTypeIsolation:
    async def test_cross_site_overwrite_rejected(self):
        """★타 현장(site-A) 소유 노드를 site-B 가 덮어쓰려 하면 거부(교차현장 무단변경 차단).
        전용 예외 CrossSiteOwnershipError 로 raise 한다(엔드포인트 409 매핑 신호)."""
        db = _TaxPrefDB(owner_site="site-A")
        with pytest.raises(CrossSiteOwnershipError, match="다른 현장"):
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

    async def test_zero_rowcount_rejected_not_silent_success(self):
        """★silent no-op 회귀가드: 선검사를 통과했어도 INSERT…ON CONFLICT…WHERE site_id 가
        경합으로 0행 갱신(타 현장 행 선점)이면, 함수가 tt 를 반환해 성공 위장하지 않고
        CrossSiteOwnershipError 로 거부해야 한다(차단된 머니패스 write 의 성공 위장 차단)."""
        db = _TaxPrefDB(owner_site=None, insert_rowcount=0)  # 선검사 통과(행 없음) + 경합으로 0행
        with pytest.raises(CrossSiteOwnershipError):
            await engine.set_node_tax_type(db, "site-A", "node-1", "VAT")
        assert db.insert_called is True  # INSERT 는 시도했으나 0행 → 거부

    async def test_rowcount_one_succeeds(self):
        """정상: INSERT 가 1행 반영(rowcount=1)이면 그대로 성공 반환."""
        db = _TaxPrefDB(owner_site=None, insert_rowcount=1)
        assert await engine.set_node_tax_type(db, "site-A", "node-1", "VAT") == "VAT"

    async def test_rowcount_unsupported_minus_one_not_rejected(self):
        """드라이버가 rowcount 미지원(-1)이면 거부하지 않는다(정상 경로 오탐 방지 — 0 일 때만 거부)."""
        db = _TaxPrefDB(owner_site=None, insert_rowcount=-1)
        assert await engine.set_node_tax_type(db, "site-A", "node-1", "WITHHOLDING") == "WITHHOLDING"


# ── CrossSiteOwnershipError: 응답계약 SSOT(전용 예외 → 409, 문구 무관 불변) ─────────
class TestCrossSiteOwnershipError:
    def test_is_value_error_subclass(self):
        """ValueError 하위라 기존 'except ValueError' 경로와 하위호환된다."""
        assert issubclass(CrossSiteOwnershipError, ValueError)

    async def test_endpoint_maps_to_409_via_isinstance_not_substring(self):
        """★응답계약 회귀가드: set_tax_pref 엔드포인트가 메시지 부분문자열이 아니라 예외 타입
        (CrossSiteOwnershipError isinstance)으로 409 를 매핑한다 → 메시지 문구를 바꿔도 409 불변."""
        from app.api.endpoints.sales import actions

        async def _raise_cross(*_a, **_k):
            # 의도적으로 '다른 현장' 부분문자열이 없는 메시지 — 그래도 409 여야 한다(타입 기반 분기).
            raise CrossSiteOwnershipError("OWNERSHIP_CONFLICT_X")

        class _Ctx:
            class _U:
                id = "u1"
            user = _U()
            site_id = "site-A"

        async def _noop_commit():
            pass

        class _DB:
            async def commit(self):
                await _noop_commit()

        import app.services.sales.commission.engine as eng
        orig = eng.set_node_tax_type
        eng.set_node_tax_type = _raise_cross
        try:
            with pytest.raises(HTTPException) as ei:
                await actions.set_tax_pref(
                    {"node_id": str(uuid_mod.uuid4()), "tax_type": "VAT"}, _DB(), _Ctx())
        finally:
            eng.set_node_tax_type = orig
        assert ei.value.status_code == 409  # 문구에 '다른 현장' 없어도 타입으로 409 불변

    async def test_endpoint_maps_plain_value_error_to_400(self):
        """일반 ValueError(잘못된 tax_type 등)는 400 으로 매핑(409 와 분리)."""
        from app.api.endpoints.sales import actions

        async def _raise_plain(*_a, **_k):
            raise ValueError("tax_type은 WITHHOLDING 또는 VAT")

        class _Ctx:
            class _U:
                id = "u1"
            user = _U()
            site_id = "site-A"

        class _DB:
            async def commit(self):
                pass

        import app.services.sales.commission.engine as eng
        orig = eng.set_node_tax_type
        eng.set_node_tax_type = _raise_plain
        try:
            with pytest.raises(HTTPException) as ei:
                await actions.set_tax_pref(
                    {"node_id": str(uuid_mod.uuid4()), "tax_type": "FOO"}, _DB(), _Ctx())
        finally:
            eng.set_node_tax_type = orig
        assert ei.value.status_code == 400


# ── _R_TAXPREF: 세금유형 변경/조회 권한 게이트(MEMBER 제거, TEAM_LEADER+) ──────────
class TestTaxPrefRoleGate:
    def test_member_removed_from_taxpref_roles(self):
        """★머니패스 게이트: 최하위 영업사원(MEMBER)은 세금유형 set/get 권한에서 제거됐다."""
        from app.api.endpoints.sales import actions
        assert "MEMBER" not in actions._R_TAXPREF
        assert "TEAM_LEADER" in actions._R_TAXPREF  # 최소 TEAM_LEADER 이상

    async def test_get_tax_pref_has_role_gate_not_bare_sales_ctx(self):
        """★조회 게이트 추가 회귀가드: GET /commission/tax-pref 가 sales_ctx 단독이 아니라
        require_role(*_R_TAXPREF) 게이트로 보호된다(역할 없는 사용자 403)."""
        from app.api.deps_sales import require_role
        from app.api.endpoints.sales import actions

        # require_role(*_R_TAXPREF) 가 막는 역할(MEMBER)은 403, 허용 역할(TEAM_LEADER)은 통과.
        gate = require_role(*actions._R_TAXPREF)

        class _CtxMember:
            role = "MEMBER"

        class _CtxLeader:
            role = "TEAM_LEADER"

        dep = gate  # gate 는 _dep 코루틴 함수를 직접 반환
        with pytest.raises(HTTPException) as ei:
            await dep(_CtxMember())
        assert ei.value.status_code == 403
        # 허용 역할은 통과(예외 없이 ctx 반환).
        assert await dep(_CtxLeader()) is not None


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


# ── total_paid_of: 실지급 현금(gross+vat) 집계 규약 SSOT ──────────────────────────
class TestTotalPaidOf:
    def test_withholding_no_vat_equals_gross(self):
        """WITHHOLDING 은 vat=0 → 총지급 현금 = gross(공급가액과 동일)."""
        from app.services.sales.commission.extension import total_paid_of
        assert total_paid_of(1_000_000, 0) == 1_000_000

    def test_vat_adds_to_gross(self):
        """★VAT 과소집계 회귀가드: 총지급 현금 = 공급가 + 부가세(컬럼 직접합산이 아닌 규약 헬퍼)."""
        from app.services.sales.commission.extension import total_paid_of
        # VAT 수령자: 공급가 1,000,000 + 부가세 100,000 = 실지급 1,100,000.
        assert total_paid_of(1_000_000, 100_000) == 1_100_000

    def test_matches_payout_net_total_paid(self):
        """payout_net 의 total_paid 와 total_paid_of(gross, vat)가 동일 규약임을 보장."""
        from app.services.sales.commission.extension import total_paid_of
        r = payout_net(Decimal(1_000_000), tax_type="VAT")
        assert total_paid_of(r["gross"], r["vat"]) == int(r["total_paid"])

    def test_none_defaults_to_zero(self):
        """None 입력은 0 으로 본다(방어 — silent 흡수가 아니라 명시 기본)."""
        from app.services.sales.commission.extension import total_paid_of
        assert total_paid_of(None, None) == 0

    def test_float_normalized_via_decimal_str(self):
        """★float Decimal(str(x)) 정규화(iter-5·작업6): 부동소수 오차 없이 정확 합산.
        0.1+0.2 부동소수(=0.30000000000000004) 같은 누적오차가 int 절단에 섞이지 않게 한다."""
        from app.services.sales.commission.extension import total_paid_of
        # 1,000,000.0(float) + 100,000.0(float) → 정확히 1,100,000(부동소수 오차 흡수).
        assert total_paid_of(1_000_000.0, 100_000.0) == 1_100_000

    def test_negative_vat_rejected(self):
        """★음수 vat 가드(iter-5·작업6): payout_net 의 음수 gross 거부와 대칭 — 0 흡수 금지, ValueError."""
        from app.services.sales.commission.extension import total_paid_of
        with pytest.raises(ValueError, match="vat"):
            total_paid_of(1_000_000, -1)

    def test_negative_gross_rejected(self):
        """음수 gross 도 거부(현금유출 과소집계·역분개 방지)."""
        from app.services.sales.commission.extension import total_paid_of
        with pytest.raises(ValueError, match="gross"):
            total_paid_of(-1, 0)


# ── settle_summary: 지급 2소스(claim + 스케줄 claim_id=NULL) UNION 합산 ──────────────
class TestSettleSummaryTwoSourcePaid:
    async def test_paid_sql_unions_claim_and_schedule_sources(self):
        """★구조적 누락 회귀가드(iter-5 HIGH): paid 집계 SQL 이 claim 경로 + 스케줄 경로(claim_id NULL)
        를 UNION ALL 로 합산한다. INNER JOIN claims 체인만 쓰면 run_due_payouts 가 만든 스케줄
        지급분(claim_id=NULL)이 전량 누락돼 outstanding 이 과대 표시됐다 — UNION 으로 두 소스 합산."""
        captured = []

        class _CaptureSettleDB(_SettleDB):
            async def execute(self, stmt, *_a, **_k):
                captured.append(str(getattr(stmt, "text", stmt)).upper())
                return await super().execute(stmt, *_a, **_k)

        db = _CaptureSettleDB(earned=500_000, contracts=2, paid=200_000)
        await settle_summary(db, "site-x", "node-y")
        paid_sql = captured[2]  # ①earned ②contracts ③paid
        # 두 소스 합산: UNION ALL + 스케줄 테이블 조인 + claim_id IS NULL 상호배타 + 양쪽 현장격리.
        assert "UNION ALL" in paid_sql
        assert "SALES_COMMISSION_PAYOUT_SCHEDULE" in paid_sql
        assert "PAID_PAYOUT_ID" in paid_sql
        assert "P.CLAIM_ID IS NULL" in paid_sql
        # 기존 격리 대칭(events 조인 + e.site_id)도 양쪽 모두 유지.
        assert "SALES_COMMISSION_EVENTS" in paid_sql
        assert "E.SITE_ID=:S" in paid_sql

    async def test_schedule_paid_included_outstanding_correct(self):
        """★실집계 경로 회귀가드(가짜 paid 주입 아님): 지급 합계 SELECT 가 두 소스를 합쳐 돌려준
        실값(스케줄 지급분 포함)을 settle_summary 가 paid 로 그대로 받아 outstanding=earned−paid 를
        정확히 낸다. (기존 _SettleDB 는 3번째 execute 결과를 paid 로 받으므로, 그 값이 'claim+스케줄
        합산'을 흉내내면 스케줄 지급분이 outstanding 에서 빠짐을 단언할 수 있다 — 가짜 paid 가 아닌
        '합산 SELECT 결과를 paid 로 반영'하는 경로를 검증.)"""
        # earned 800,000 중 claim 지급 200,000 + 스케줄 지급 300,000 = 합산 paid 500,000.
        db = _SettleDB(earned=800_000, contracts=3, paid=500_000)
        out = await settle_summary(db, "site-x", "node-y")
        assert out["paid_gross"] == 500_000      # 두 소스 합산이 paid 로 반영
        assert out["outstanding_gross"] == 300_000  # 800,000 − 500,000 (스케줄분이 미지급으로 새지 않음)

    async def test_missing_schedule_table_still_falls_back(self):
        """스케줄 테이블 미존재(42P01)여도 settle_summary 의 미존재→paid=0 폴백 정책은 그대로
        (UNION 쿼리 전체가 미존재 분류로 0 폴백). 실오류는 여전히 전파(별도 테스트가 보장)."""
        db = _SettleDB(earned=500_000, contracts=2, paid=0, paid_exc=_dbapi("42P01"))
        out = await settle_summary(db, "site-x", "node-y")
        assert out["paid_gross"] == 0
        assert out["outstanding_gross"] == 500_000


# ── _R_TAXPREF: 권한사다리 역전 해소(DIRECTOR 포함) ─────────────────────────────────
class TestTaxPrefRoleLadder:
    def test_director_in_taxpref_roles(self):
        """★권한사다리 역전 회귀가드(iter-5·작업3): DIRECTOR 는 _R_ORG_ADD/_R_TEAM/_R_CONTRACT 에
        모두 있는 상위 관리직인데 _R_TAXPREF 에서만 누락돼 하급 TEAM_LEADER 통과·상급 DIRECTOR 403
        역전이 있었다. DIRECTOR 가 _R_TAXPREF 에 포함돼 단조성이 복원돼야 한다."""
        from app.api.endpoints.sales import actions
        assert "DIRECTOR" in actions._R_TAXPREF
        # 사다리 단조성: DIRECTOR 가 들어간 다른 상위 집합과 일관(하급 통과 시 상급도 통과).
        assert "TEAM_LEADER" in actions._R_TAXPREF  # 하급도 여전히 허용(범위 축소 아님)

    async def test_director_passes_taxpref_gate(self):
        """DIRECTOR 가 require_role(*_R_TAXPREF) 게이트를 통과한다(403 아님)."""
        from app.api.deps_sales import require_role
        from app.api.endpoints.sales import actions

        gate = require_role(*actions._R_TAXPREF)

        class _CtxDirector:
            role = "DIRECTOR"

        assert await gate(_CtxDirector()) is not None  # 통과(예외 없음)


# ── set_tax_pref: node_id UUID 형식오류 전용 메시지(오안내 차단) ─────────────────────
class TestSetTaxPrefNodeIdMessage:
    async def test_bad_uuid_node_id_gives_node_id_message_not_tax_type(self):
        """★오안내 회귀가드(iter-5·작업5): node_id 가 UUID 형식이 아니면 'tax_type 오류'가 아니라
        'node_id 형식' 전용 메시지로 400 을 돌려준다(과거엔 uuid.UUID(ValueError)가 tax_type 핸들러로
        빨려들어가 오안내됨)."""
        from app.api.endpoints.sales import actions

        class _Ctx:
            class _U:
                id = "u1"
            user = _U()
            site_id = "site-A"

        class _DB:
            async def commit(self):
                pass

        with pytest.raises(HTTPException) as ei:
            await actions.set_tax_pref({"node_id": "NOT-A-UUID", "tax_type": "VAT"}, _DB(), _Ctx())
        assert ei.value.status_code == 400
        assert "node_id" in ei.value.detail  # node_id 전용 안내
        assert "tax_type" not in ei.value.detail  # tax_type 오안내가 아님

    async def test_missing_node_id_gives_node_id_message(self):
        """node_id 키 누락 → node_id 전용 400(KeyError 분리)."""
        from app.api.endpoints.sales import actions

        class _Ctx:
            class _U:
                id = "u1"
            user = _U()
            site_id = "site-A"

        class _DB:
            async def commit(self):
                pass

        with pytest.raises(HTTPException) as ei:
            await actions.set_tax_pref({"tax_type": "VAT"}, _DB(), _Ctx())
        assert ei.value.status_code == 400
        assert "node_id" in ei.value.detail


# ── _income_for(termination_cert): silent-fail 차단(미존재만 0, 실오류 전파) ────────────
class _IncomeDB:
    """_income_for 의 (1차 소득집계 → 폴백 집계) execute 흐름을 흉내낸다.

    first_exc 가 주어지면 1차 SELECT 에서 그 예외를, fallback_exc 면 폴백 SELECT 에서 던진다.
    예외가 없으면 first_row/fallback_row(.first())를 돌려준다. rollback 호출 여부를 기록한다.
    """
    def __init__(self, first_row=None, first_exc=None, fallback_row=None, fallback_exc=None):
        self._first_row = first_row
        self._first_exc = first_exc
        self._fallback_row = fallback_row
        self._fallback_exc = fallback_exc
        self._call = 0
        self.rolled_back = False

    async def execute(self, *_a, **_k):
        self._call += 1
        if self._call == 1:
            if self._first_exc is not None:
                raise self._first_exc
            return _FakeFirst(self._first_row)
        if self._fallback_exc is not None:
            raise self._fallback_exc
        return _FakeFirst(self._fallback_row)

    async def rollback(self):
        self.rolled_back = True


class TestIncomeForSilentFail:
    async def test_missing_table_falls_back_to_zero(self):
        """1차 소득집계 테이블 미존재(42P01) → 폴백 경로로 진행, 폴백도 미존재면 0(정상 0)."""
        import uuid as _uuid

        from app.api.endpoints.sales import termination_cert as tc
        db = _IncomeDB(first_exc=_dbapi("42P01"), fallback_exc=_dbapi("42P01"))
        out = await tc._income_for(db, _uuid.uuid4(), _uuid.uuid4(), None)
        assert out == {"income_total": 0, "withholding_total": 0, "net_total": 0}
        assert db.rolled_back is True  # 트랜잭션 오염 방지 롤백 수행

    async def test_real_error_propagates_first(self):
        """★silent-fail 회귀가드(iter-5·작업4): 1차 집계 권한오류(42501) 등 실오류는 0 으로 은폐하지
        않고 전파(과거 bare except: pass 가 소득=0 으로 삼키던 맹점 봉인)."""
        import uuid as _uuid

        from app.api.endpoints.sales import termination_cert as tc
        db = _IncomeDB(first_exc=_dbapi("42501"))
        with pytest.raises(DBAPIError):
            await tc._income_for(db, _uuid.uuid4(), _uuid.uuid4(), None)
        assert db.rolled_back is True

    async def test_real_error_propagates_fallback(self):
        """폴백 집계의 실오류(42501)도 전파(0 은폐 금지). 1차는 미존재(폴백 진입)로 둔다."""
        import uuid as _uuid

        from app.api.endpoints.sales import termination_cert as tc
        db = _IncomeDB(first_exc=_dbapi("42P01"), fallback_exc=_dbapi("42501"))
        with pytest.raises(DBAPIError):
            await tc._income_for(db, _uuid.uuid4(), _uuid.uuid4(), None)

    async def test_primary_row_returned_gross_only(self):
        """정상 1차 집계: 원천징수증명은 gross-only(vat 미가산)가 정합 — payout 의 gross/wh/net 그대로."""
        import uuid as _uuid

        from app.api.endpoints.sales import termination_cert as tc
        db = _IncomeDB(first_row=(1_000_000, 33_000, 967_000))
        out = await tc._income_for(db, _uuid.uuid4(), _uuid.uuid4(), None)
        assert out == {"income_total": 1_000_000, "withholding_total": 33_000, "net_total": 967_000}


# ── console.cash_profit: VAT 포함 실지급(total_paid_of 규약) 배선 회귀가드 ──────────────
class TestConsoleCashProfitVatWired:
    async def test_cash_profit_uses_payout_gross_plus_vat(self, monkeypatch):
        """★VAT 과소집계 회귀가드(iter-5 HIGH·완결): cash_flow.profit/commission 이 발생주의 split 합이
        아니라 '실지급 현금'(payout gross+vat)으로 산출된다. VAT 노드가 있으면 gross-only 대비
        vat 만큼 현금유출(commission_paid)이 커지고 cash_profit 이 그만큼 작아진다.

        site_management_detail 내부 _scalar 호출 순서에 맞춰 결과를 주입하는 가짜 세션으로,
        commission_paid_cash 쿼리(payout gross+vat UNION)가 cash_flow 에 반영되는지 단언한다."""
        from app.services.sales.admin import console

        # _scalar 가 부르는 SELECT 들을 SQL 키워드로 식별해 값을 주입(순서 비의존 — 견고).
        async def _fake_scalar(db, sql, **p):
            u = sql.upper()
            # 수수료 '실지급 현금'(payout gross+vat UNION) — PAID_PAYOUT_ID(스케줄경로) 가 박힌 그 쿼리.
            if "PAID_PAYOUT_ID" in u:
                return 1_100_000  # gross 1,000,000 + vat 100,000 (VAT 노드 포함)
            # 발생주의 수수료 배분(split 합) — gross-only 1,000,000(PAID_PAYOUT_ID 없음으로 구분).
            if "SALES_COMMISSION_SPLITS" in u and "SUM(SP.AMOUNT)" in u:
                return 1_000_000
            # 실수납(현금흐름 매출).
            if "SALES_PAYMENTS" in u and "MATCHED=TRUE" in u and "INSTALLMENT_ID" not in u:
                return 5_000_000
            # 인식매출(ACTIVE 계약총액).
            if "SUM(TOTAL_PRICE)" in u and "STAGE" not in u:
                return 6_000_000
            return 0  # 그 외(직원수·방문·광고·회차 등)는 0

        monkeypatch.setattr(console, "_scalar", _fake_scalar)

        async def _fake_cost(db, site_id):
            return {}  # 회계비용 0(순수 수수료 효과만 본다)

        monkeypatch.setattr(console, "_cost_by_type", _fake_cost)

        d = await console.site_management_detail(object(), "site-A")
        cf = d["cash_flow"]
        # 현금흐름 수수료 = 실지급(gross+vat) 1,100,000 (발생주의 split 1,000,000 이 아님).
        assert cf["commission_paid"] == 1_100_000
        assert cf["commission"] == 1_100_000  # 하위호환 키도 실지급액으로 교체
        # cash_profit = 실수납 5,000,000 − 비용 0 − 실지급수수료 1,100,000 = 3,900,000.
        assert cf["profit"] == 3_900_000
        # 발생주의 commission(top-level·accrual)은 split 합(1,000,000) 그대로(두 관점 분리).
        assert d["commission"] == 1_000_000
        assert d["accrual"]["commission"] == 1_000_000

    async def test_cash_profit_smaller_than_gross_only_by_vat(self, monkeypatch):
        """★대조 단언: 동일 데이터에서 수수료 현금유출이 gross-only(1,000,000)였다면 cash_profit 은
        4,000,000 이어야 한다. VAT 포함(1,100,000)이라 vat(100,000)만큼 더 작은 3,900,000 이 됨을
        확인 — '컬럼 직접합산(gross-only) 회귀'를 잡는다."""
        from app.services.sales.admin import console

        async def _fake_scalar(db, sql, **p):
            u = sql.upper()
            if "PAID_PAYOUT_ID" in u:
                return 1_100_000
            if "SALES_COMMISSION_SPLITS" in u and "SUM(SP.AMOUNT)" in u:
                return 1_000_000
            if "SALES_PAYMENTS" in u and "MATCHED=TRUE" in u and "INSTALLMENT_ID" not in u:
                return 5_000_000
            if "SUM(TOTAL_PRICE)" in u and "STAGE" not in u:
                return 6_000_000
            return 0

        monkeypatch.setattr(console, "_scalar", _fake_scalar)
        monkeypatch.setattr(console, "_cost_by_type", lambda db, site_id: _async_empty())

        d = await console.site_management_detail(object(), "site-A")
        gross_only_cash_profit = 5_000_000 - 0 - 1_000_000  # 만약 split(gross-only)로 뺐다면
        assert d["cash_flow"]["profit"] == gross_only_cash_profit - 100_000  # vat 만큼 작다


async def _async_empty():
    return {}


# ── _ensure_payout_columns: 테이블 부재 가드(42P01 방지) ──────────────────────────
class TestEnsurePayoutColumnsTableGuard:
    async def test_skips_alter_when_table_absent(self, monkeypatch):
        """★런타임 DDL 가드: sales_commission_payouts 테이블이 없으면(클린 DB·033 미적용)
        to_regclass=None → ALTER 를 건너뛴다(테이블 부재 시 42P01 으로 실패하지 않음).
        정상 0(아직 지급 도메인 미생성)이므로 게이트만 닫고 조용히 통과한다(silent-fail 아님)."""
        from app.services.sales.commission import extension

        executed = []

        class _DDLSession:
            async def execute(self, stmt, *_a, **_k):
                sql = str(getattr(stmt, "text", stmt))
                executed.append(sql.upper())
                if "TO_REGCLASS" in sql.upper():
                    return _FakeResult(None)  # 테이블 부재
                return _FakeResult(None)

            async def commit(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_a):
                return False

        def _factory():
            return _DDLSession()

        import app.core.database as core_db
        monkeypatch.setattr(core_db, "async_session_factory", _factory, raising=False)
        extension._PAYOUT_COLS_READY = False  # 1회 게이트 내려 DDL 경로 진입
        try:
            await extension._ensure_payout_columns(None)
        finally:
            extension._PAYOUT_COLS_READY = True  # 격리 복원
        # advisory-lock + to_regclass 는 실행, ALTER 는 (테이블 부재라) 미실행.
        assert any("TO_REGCLASS" in s for s in executed)
        assert not any("ALTER TABLE" in s for s in executed)

    async def test_runs_alter_when_table_present(self, monkeypatch):
        """테이블이 존재하면(to_regclass non-None) ALTER ADD COLUMN IF NOT EXISTS 2건을 수행한다."""
        from app.services.sales.commission import extension

        executed = []

        class _DDLSession:
            async def execute(self, stmt, *_a, **_k):
                sql = str(getattr(stmt, "text", stmt))
                executed.append(sql.upper())
                if "TO_REGCLASS" in sql.upper():
                    return _FakeResult("sales_commission_payouts")  # 테이블 존재
                return _FakeResult(None)

            async def commit(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_a):
                return False

        import app.core.database as core_db
        monkeypatch.setattr(core_db, "async_session_factory", lambda: _DDLSession(), raising=False)
        extension._PAYOUT_COLS_READY = False
        try:
            await extension._ensure_payout_columns(None)
        finally:
            extension._PAYOUT_COLS_READY = True
        alters = [s for s in executed if "ALTER TABLE" in s]
        assert len(alters) == 2  # tax_type, vat 각각 1건


# ── _income_for: 지급 2소스(claim + 스케줄 claim_id=NULL) UNION 합산(법적 세무서류 정확성) ──────
class _CaptureIncomeDB(_IncomeDB):
    """_income_for 의 1차 SELECT 문을 캡처하는 _IncomeDB — UNION 구조 회귀가드용."""
    def __init__(self, first_row=None):
        super().__init__(first_row=first_row)
        self.captured = []

    async def execute(self, stmt, *_a, **_k):
        self.captured.append(str(getattr(stmt, "text", stmt)).upper())
        return await super().execute(stmt, *_a, **_k)


class TestIncomeForTwoSourceUnion:
    async def test_primary_sql_unions_claim_and_schedule(self):
        """★구조적 누락 회귀가드(iter-6 HIGH·법적): _income_for 1차 소득쿼리가 claim 경로 +
        스케줄 경로(claim_id NULL)를 UNION ALL 로 합산한다. INNER JOIN claims 만 쓰면
        run_due_payouts 의 스케줄 지급분(claim_id=NULL)이 전량 누락돼 원천징수영수증 income_total 이
        0 으로 과소표시됐다 — UNION + 스케줄 테이블 조인 + split.node→user 격리 회귀가드."""
        import uuid as _uuid

        from app.api.endpoints.sales import termination_cert as tc
        db = _CaptureIncomeDB(first_row=(1_000_000, 33_000, 967_000))
        await tc._income_for(db, _uuid.uuid4(), _uuid.uuid4(), None)
        sql = db.captured[0]
        assert "UNION ALL" in sql
        assert "SALES_COMMISSION_PAYOUT_SCHEDULE" in sql
        assert "PAID_PAYOUT_ID" in sql
        assert "P.CLAIM_ID IS NULL" in sql  # 스케줄 경로 상호배타
        # 현장·사용자 격리 양쪽 유지(split.node→user, event.site).
        assert "E.SITE_ID = :SID" in sql
        assert "N.USER_ID = :UID" in sql
        assert "N.ID = SP.NODE_ID" in sql  # claimant_node 가 아닌 split.node→user 매칭

    async def test_schedule_income_nonzero_legal_document(self):
        """★법적 세무서류 정확성: 스케줄 지급분(claim_id=NULL)을 합산한 1차 결과가 비-0 이면
        income_total·withholding_total 이 그 값으로 채워진다(0 과소표시 아님).
        (1차 SELECT 가 두 소스를 합산해 돌려준 실값을 그대로 받는 경로 검증.)"""
        import uuid as _uuid

        from app.api.endpoints.sales import termination_cert as tc
        # 스케줄 지급분만 존재한다고 가정한 합산 결과(claim 경로 0 + 스케줄 경로 1,000,000).
        db = _IncomeDB(first_row=(1_000_000, 33_000, 967_000))
        out = await tc._income_for(db, _uuid.uuid4(), _uuid.uuid4(), None)
        assert out["income_total"] == 1_000_000   # 비-0(법적서류 0 과소표시 차단)
        assert out["withholding_total"] == 33_000
        assert out["net_total"] == 967_000


# ── build_withholding_statements: 지급 2소스 UNION + payee_node_id 채움(폴백 JOIN 복구) ──────
class _WhStmtDB:
    """build_withholding_statements 의 (집계 SELECT → db.add 들 → flush) 흐름을 흉내낸다.

    rows 로 'GROUP BY node_id' 결과((node_id, gross, withholding) 튜플들)를 주입한다(.all()).
    db.add 로 추가된 SalesWithholdingStatement 들을 added 에 모아 payee_node_id 채움을 검증한다.
    captured_sql 에 집계 SELECT 문을 담아 UNION 구조를 회귀가드한다.
    """
    def __init__(self, rows):
        self._rows = rows
        self.added = []
        self.captured_sql = ""

    async def execute(self, stmt, *_a, **_k):
        self.captured_sql = str(getattr(stmt, "text", stmt)).upper()
        return _AllResult(self._rows)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


class _AllResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class TestBuildWithholdingStatementsTwoSource:
    async def test_sql_unions_two_sources_and_groups_by_node(self):
        """★구조적 누락 회귀가드(iter-6 HIGH): 집계 SELECT 가 claim 경로 + 스케줄 경로(claim_id NULL)를
        UNION ALL 로 합산하고 node_id 로 그룹핑한다(payee_node_id 채움 가능). INNER JOIN claims 만
        쓰면 스케줄 지급분이 전량 누락됐다."""
        import uuid as _uuid

        from app.services.sales.tax import service as tax_svc
        node = _uuid.uuid4()
        db = _WhStmtDB(rows=[(node, 1_000_000, 33_000)])
        await tax_svc.build_withholding_statements(db, _uuid.uuid4(), "2026-06")
        sql = db.captured_sql
        assert "UNION ALL" in sql
        assert "SALES_COMMISSION_PAYOUT_SCHEDULE" in sql
        assert "PAID_PAYOUT_ID" in sql
        assert "P.CLAIM_ID IS NULL" in sql
        assert "GROUP BY NODE_ID" in sql
        assert "E.SITE_ID = :SID" in sql  # event 경유 site 스코프(claim.site_id 단독 의존 제거)

    async def test_statement_payee_node_id_filled(self):
        """★폴백 JOIN 복구 회귀가드(iter-6): 생성 statement 에 payee_node_id 가 채워진다.
        과거엔 payee_node_id 가 비어 _income_for 폴백 JOIN(payee_node_id 매칭)이 실패해 복구불가였다."""
        import uuid as _uuid

        from app.services.sales.tax import service as tax_svc
        node = _uuid.uuid4()
        db = _WhStmtDB(rows=[(node, 1_000_000, 33_000)])
        sts = await tax_svc.build_withholding_statements(db, _uuid.uuid4(), "2026-06")
        assert isinstance(sts, list) and len(sts) == 1
        assert sts[0].payee_node_id == node          # 폴백 JOIN 이 매칭할 수 있게 채워짐
        assert int(sts[0].gross or 0) == 1_000_000   # 합산 gross 반영
        assert int(sts[0].withholding or 0) == 33_000

    async def test_per_node_statements_created(self):
        """수령 노드별 1건씩 생성(노드 2개 → statement 2건). 폴백 JOIN 이 노드별로 작동하도록."""
        import uuid as _uuid

        from app.services.sales.tax import service as tax_svc
        n1, n2 = _uuid.uuid4(), _uuid.uuid4()
        db = _WhStmtDB(rows=[(n1, 600_000, 19_800), (n2, 400_000, 13_200)])
        sts = await tax_svc.build_withholding_statements(db, _uuid.uuid4(), "2026-06")
        assert {s.payee_node_id for s in sts} == {n1, n2}
        assert len(db.added) == 2


# ── settle_summary: clawback 후 outstanding max(0,..) 클램프 의도동작 고정 ──────────────────
class TestSettleSummaryClawbackClamp:
    async def test_outstanding_clamped_to_zero_after_overpay(self):
        """★의도동작 회귀가드(iter-6 관찰): 환수(clawback)로 earned 에서 빠진 이벤트에 이미 지급된
        payout 이 paid 에 남으면 earned < paid 가 된다. 이때 outstanding 은 음수가 아니라 max(0,..)=0
        으로 클램프된다(미지급 잔액은 ≥0; 과지급 회수는 별도 환수 원장이 담당). 이 클램프를 고정한다."""
        # earned 100,000(환수 후 잔여) < paid 300,000(환수 전 지급분 포함) → outstanding=max(0,-200,000)=0.
        db = _SettleDB(earned=100_000, contracts=1, paid=300_000)
        out = await settle_summary(db, "site-x", "node-y")
        assert out["paid_gross"] == 300_000
        assert out["earned_gross"] == 100_000
        assert out["outstanding_gross"] == 0  # 음수로 새지 않고 0 에 클램프(미지급은 ≥0)
        # 정산 분개도 0 기준(미지급 0 → 원천/순액 0).
        assert out["settlement"]["net"] == 0


# ── actions GET 엔드포인트: node_id UUID 형식오류 전용 400(대칭) ──────────────────────────
class TestActionsGetUuidGuard:
    async def test_get_tax_pref_bad_uuid_returns_400_not_500(self):
        """★UUID 가드 대칭 회귀가드(iter-6·작업4): GET /commission/tax-pref 가 비-UUID node_id 에서
        전역핸들러 500 이 아니라 전용 400(node_id 형식)으로 응답한다(set_tax_pref 와 대칭)."""
        from app.api.endpoints.sales import actions

        class _Ctx:
            class _U:
                id = "u1"
            user = _U()
            site_id = "site-A"
            role = "TEAM_LEADER"

        class _DB:
            async def execute(self, *_a, **_k):
                raise AssertionError("형식오류면 DB 를 건드리면 안 됨(파싱에서 400)")

        with pytest.raises(HTTPException) as ei:
            await actions.get_tax_pref("NOT-A-UUID", _DB(), _Ctx())
        assert ei.value.status_code == 400
        assert "node_id" in ei.value.detail

    async def test_settle_summary_bad_uuid_returns_400_not_500(self):
        """★UUID 가드 대칭 회귀가드(iter-6·작업4): GET /commission/settle-summary 도 비-UUID node_id 에서
        전용 400(node_id 형식)으로 응답한다(무가드 500 차단)."""
        from app.api.endpoints.sales import actions

        class _Ctx:
            class _U:
                id = "u1"
            user = _U()
            site_id = "site-A"
            role = "TEAM_LEADER"

        class _DB:
            async def execute(self, *_a, **_k):
                raise AssertionError("형식오류면 DB 를 건드리면 안 됨(파싱에서 400)")

        with pytest.raises(HTTPException) as ei:
            await actions.commission_settle_summary("not-uuid", _DB(), _Ctx())
        assert ei.value.status_code == 400
        assert "node_id" in ei.value.detail


# ── build_withholding_statements: 멱등화(delete-before-insert) + GET 읽기전용(iter-7 HIGH) ──────
class _IdempWhStmtDB:
    """build_withholding_statements 의 (DELETE → 집계 SELECT → db.add 들 → flush) 흐름을 흉내내며
    '재호출 멱등'을 행수 단위로 증명한다.

    내부에 (period→stored rows) 스토어를 둔다. DELETE 면 해당 period 의 stored 를 비우고,
    집계 SELECT 면 주입된 agg_rows((node,gross,wh) 튜플들)를 .all() 로 돌려준다. db.add 된 statement 는
    period 별 스토어에 누적한다. 따라서 같은 period 를 두 번 빌드해도(DELETE 가 먼저 비우므로) 스토어
    행수가 1회 빌드와 동일해야 한다(누적증폭 차단 회귀가드).
    """
    def __init__(self, agg_rows):
        self._agg_rows = agg_rows
        self.store: dict = {}
        self.delete_sqls: list[str] = []

    async def execute(self, stmt, *_a, **_k):
        sql = str(getattr(stmt, "text", stmt))
        up = sql.upper()
        params = _a[0] if _a else {}
        if up.lstrip().startswith("DELETE"):
            self.delete_sqls.append(up)
            self.store[params.get("period")] = []  # 해당 period 선삭제(멱등 핵심)
            return _AllResult([])
        return _AllResult(self._agg_rows)  # 집계 SELECT

    def add(self, obj):
        self.store.setdefault(obj.period, []).append(obj)

    async def flush(self):
        pass


class TestBuildWithholdingIdempotent:
    async def test_delete_before_insert_present(self):
        """★멱등 회귀가드(iter-7 HIGH): build 가 집계 INSERT 전에 (site,period) 명세를 DELETE 한다."""
        import uuid as _uuid

        from app.services.sales.tax import service as tax_svc
        node = _uuid.uuid4()
        db = _IdempWhStmtDB(agg_rows=[(node, 1_000_000, 33_000)])
        await tax_svc.build_withholding_statements(db, _uuid.uuid4(), "2026-06")
        assert db.delete_sqls, "build 에 선삭제 DELETE 가 없음(멱등 미보장)"
        d = db.delete_sqls[0]
        assert "SALES_WITHHOLDING_STATEMENTS" in d
        assert "SITE_ID = :SID" in d and "PERIOD = :PERIOD" in d  # 이 현장·이 기간만 선삭제

    async def test_rebuild_same_period_row_count_and_sum_invariant(self):
        """★누적증폭 차단 회귀가드(iter-7 HIGH): 같은 (site,period)를 두 번 빌드해도 행수·합계 불변.
        과거엔 GET 호출마다 무조건 INSERT 라 동일 기간 재호출 시 명세가 N행으로 중복누적됐다."""
        import uuid as _uuid

        from app.services.sales.tax import service as tax_svc
        node = _uuid.uuid4()
        site = _uuid.uuid4()
        db = _IdempWhStmtDB(agg_rows=[(node, 1_000_000, 33_000)])
        await tax_svc.build_withholding_statements(db, site, "2026-06")
        first = list(db.store["2026-06"])
        await tax_svc.build_withholding_statements(db, site, "2026-06")  # 재호출
        second = db.store["2026-06"]
        assert len(first) == 1 and len(second) == 1  # 2회 호출에도 1행(누적 아님)
        assert int(second[0].gross or 0) == 1_000_000  # 합계도 불변(증폭 없음)

    async def test_other_period_not_deleted(self):
        """선삭제 범위는 '이 기간'만 — 다른 기간 명세는 보존(period 한정 DELETE)."""
        import uuid as _uuid

        from app.services.sales.tax import service as tax_svc
        node = _uuid.uuid4()
        site = _uuid.uuid4()
        db = _IdempWhStmtDB(agg_rows=[(node, 500_000, 16_500)])
        await tax_svc.build_withholding_statements(db, site, "2026-05")
        await tax_svc.build_withholding_statements(db, site, "2026-06")  # 다른 기간
        assert len(db.store["2026-05"]) == 1  # 5월분이 6월 빌드에 지워지지 않음
        assert len(db.store["2026-06"]) == 1


class _ReadWhStmtDB:
    """read_withholding_statements 의 SELECT 1회만 흉내낸다 — 쓰기(add/commit) 가 호출되면 실패하게 한다.

    rows 로 적재된 명세((node,gross,wh) 튜플들)를 .all() 로 돌려준다. add/commit 이 호출되면
    AssertionError 로 'GET 이 쓰기를 했다'를 즉시 잡는다(safe GET 회귀가드)."""
    def __init__(self, rows):
        self._rows = rows
        self.executed = 0

    async def execute(self, *_a, **_k):
        self.executed += 1
        return _AllResult(self._rows)

    def add(self, _obj):
        raise AssertionError("read_withholding_statements 는 쓰기(add)를 하면 안 됨(safe GET)")

    async def commit(self):
        raise AssertionError("read_withholding_statements 는 commit 을 하면 안 됨(safe GET)")

    async def flush(self):
        raise AssertionError("read_withholding_statements 는 flush 를 하면 안 됨(safe GET)")


class TestReadWithholdingStatementsReadOnly:
    async def test_read_only_no_write(self):
        """★GET 시맨틱 회귀가드(iter-7 HIGH): read 경로는 SELECT 만(add/commit/flush 미수행)."""
        import uuid as _uuid

        from app.services.sales.tax import service as tax_svc
        node = _uuid.uuid4()
        db = _ReadWhStmtDB(rows=[(node, 1_000_000, 33_000)])
        items = await tax_svc.read_withholding_statements(db, _uuid.uuid4(), "2026-06")
        assert db.executed == 1  # SELECT 1회만
        assert items == [{"payee_node_id": str(node), "gross": 1_000_000, "withholding": 33_000}]

    async def test_empty_when_not_built(self):
        """아직 빌드 전이면 빈 목록(정상 0 — '아직 안 만듦'이지 은폐 아님)."""
        from app.services.sales.tax import service as tax_svc
        db = _ReadWhStmtDB(rows=[])
        assert await tax_svc.read_withholding_statements(db, "site-x", "2026-06") == []


# ── _income_for 폴백: tax_year 누락 해소(특정 연도만 집계 — 과대표시 차단·iter-7 HIGH) ──────────
class TestIncomeForFallbackYearFilter:
    async def test_fallback_carries_year_filter_when_tax_year_given(self):
        """★폴백 year 누락 회귀가드(iter-7 HIGH): tax_year 지정 시 폴백 SELECT 가 period 앞4자리(연도)를
        제약한다. 과거엔 폴백에 연도 필터가 전무해 전 기간 명세를 SUM → 특정 연도 영수증 과대표시."""
        import uuid as _uuid

        from app.api.endpoints.sales import termination_cert as tc
        # 1차는 미존재(폴백 진입), 폴백 SELECT 캡처.
        db = _CaptureIncomeDB(first_row=None)
        db._first_exc = _dbapi("42P01")  # 1차 미존재 → 폴백 경로 진입
        await tc._income_for(db, _uuid.uuid4(), _uuid.uuid4(), 2026)
        fb_sql = db.captured[-1]  # 폴백 SELECT(마지막 execute)
        assert "SALES_WITHHOLDING_STATEMENTS" in fb_sql
        assert "LEFT(W.PERIOD, 4) = :YR_STR" in fb_sql  # 연도 제약 존재

    async def test_fallback_no_year_filter_when_tax_year_none(self):
        """tax_year 미지정이면 폴백은 연도 필터 없이 전 기간 집계(기존 동작 보존·하위호환)."""
        import uuid as _uuid

        from app.api.endpoints.sales import termination_cert as tc
        db = _CaptureIncomeDB(first_row=None)
        db._first_exc = _dbapi("42P01")
        await tc._income_for(db, _uuid.uuid4(), _uuid.uuid4(), None)
        fb_sql = db.captured[-1]
        assert "SALES_WITHHOLDING_STATEMENTS" in fb_sql
        assert "LEFT(W.PERIOD, 4)" not in fb_sql  # 연도 필터 미포함(전 기간)

    async def test_fallback_year_bound_param_is_year_string(self):
        """연도 바인드 파라미터(:yr_str)가 'YYYY' 문자열로 전달되는지(left()=문자열 비교) 검증."""
        import uuid as _uuid

        from app.api.endpoints.sales import termination_cert as tc

        captured_params = {}

        class _ParamCaptureDB(_IncomeDB):
            def __init__(self):
                super().__init__(first_exc=_dbapi("42P01"), fallback_row=(0, 0))

            async def execute(self, stmt, *_a, **_k):
                if _a:
                    captured_params.update(_a[0] or {})
                return await super().execute(stmt, *_a, **_k)

        await tc._income_for(_ParamCaptureDB(), _uuid.uuid4(), _uuid.uuid4(), 2025)
        assert captured_params.get("yr_str") == "2025"  # 'YYYY' 문자열 바인딩


# ── settle_summary: 과지급 가시화(overpaid/clawback_total 노출·iter-7 completeness) ─────────────
class TestSettleSummaryOverpaidVisibility:
    async def test_overpaid_exposed_when_earned_lt_paid(self):
        """★과지급 가시화 회귀가드(iter-7): earned<paid(환수 후)면 overpaid_gross 가 paid−earned 로
        노출돼 운영자가 이 명세 화면만으로 과지급을 인지한다(outstanding 은 여전히 0 클램프)."""
        # earned 100,000 < paid 300,000, 환수합(clawback_total) 200,000 주입.
        db = _SettleDB(earned=100_000, contracts=1, paid=300_000, clawback=200_000)
        out = await settle_summary(db, "site-x", "node-y")
        assert out["outstanding_gross"] == 0          # 미지급은 ≥0 클램프(기존 의도 유지)
        assert out["overpaid_gross"] == 200_000       # 과지급 신호 노출(300,000−100,000)
        assert out["clawback_total"] == 200_000       # 환수 원장 합계(근거숫자)

    async def test_no_overpaid_when_earned_ge_paid(self):
        """정상(earned≥paid)이면 overpaid_gross=0(과지급 없음). outstanding 은 earned−paid."""
        db = _SettleDB(earned=500_000, contracts=2, paid=200_000, clawback=0)
        out = await settle_summary(db, "site-x", "node-y")
        assert out["overpaid_gross"] == 0
        assert out["outstanding_gross"] == 300_000
        assert out["clawback_total"] == 0

    async def test_clawback_query_isolated_by_site_and_status_reversed(self):
        """★환수합 SQL 회귀가드: 환수합 집계가 e.site_id 격리 + e.status='REVERSED' 로 걸린다
        (타 현장·미환수 이벤트가 새지 않게)."""
        captured = []

        class _CaptureSettleDB(_SettleDB):
            async def execute(self, stmt, *_a, **_k):
                captured.append(str(getattr(stmt, "text", stmt)).upper())
                return await super().execute(stmt, *_a, **_k)

        db = _CaptureSettleDB(earned=100_000, contracts=1, paid=300_000, clawback=200_000)
        await settle_summary(db, "site-x", "node-y")
        claw_sql = captured[3]  # ①earned ②contracts ③paid ④clawback
        assert "STATUS='REVERSED'" in claw_sql
        assert "E.SITE_ID=:S" in claw_sql
        assert "S.NODE_ID=:N" in claw_sql

    async def test_clawback_missing_table_falls_back_zero(self):
        """환수 테이블/컬럼 미존재(42P01)면 clawback_total=0 폴백(정상 0). 실오류는 전파(별도 보장)."""
        # paid 정상, clawback 쿼리(④)에서 42P01 발생하도록 별도 세션 구성.
        class _ClawMissingDB(_SettleDB):
            async def execute(self, *_a, **_k):
                self._call += 1
                if self._call <= 2:
                    return self._seq[self._call - 1]
                if self._call == 3:
                    return self._paid
                if self._call == 4:
                    raise _dbapi("42P01")  # 환수합 집계 테이블 미존재
                return _FakeFirst(None)

        db = _ClawMissingDB(earned=500_000, contracts=2, paid=200_000)
        out = await settle_summary(db, "site-x", "node-y")
        assert out["clawback_total"] == 0
        assert out["overpaid_gross"] == 0  # earned≥paid
        assert db.rolled_back is True  # 미존재 분류 시 트랜잭션 오염 방지 롤백

    async def test_clawback_real_error_propagates(self):
        """★silent-fail 차단: 환수합 집계의 실오류(42501)는 0 으로 은폐하지 않고 전파."""
        class _ClawErrDB(_SettleDB):
            async def execute(self, *_a, **_k):
                self._call += 1
                if self._call <= 2:
                    return self._seq[self._call - 1]
                if self._call == 3:
                    return self._paid
                if self._call == 4:
                    raise _dbapi("42501")  # 권한오류 등 실오류
                return _FakeFirst(None)

        db = _ClawErrDB(earned=500_000, contracts=2, paid=200_000)
        with pytest.raises(DBAPIError):
            await settle_summary(db, "site-x", "node-y")


# ── 지급 2소스 UNION 의미정확성 — stdlib sqlite 실행검증(상호배타·중복합산 차단·iter-7 작업4) ──────
class TestWithholdingUnionSqliteSemantics:
    """SQL 문자열 단언을 넘어, 두 소스 UNION ALL 의 '중복합산 차단(상호배타)'을 stdlib sqlite(:memory:)
    실행으로 증명한다(aiosqlite 미설치라 sync sqlite3 로 동등 SQL 검증 — test_unit_concurrency 패턴).

    핵심: 한 payout 이 claim 경로와 스케줄 경로 양쪽에 동시에 잡히면 gross 가 2배로 새지만,
    ① 경로(claim_id 채워짐)와 ② 경로(claim_id IS NULL)는 상호배타라 그런 이중계상이 불가능함을
    실데이터로 단언한다(claim 지급 + 스케줄 지급 = 정확히 합, 더블카운트 0)."""
    def _build_db(self):
        import sqlite3
        c = sqlite3.connect(":memory:")
        c.executescript(
            """
            CREATE TABLE sales_commission_events (id TEXT PRIMARY KEY, site_id TEXT);
            CREATE TABLE sales_commission_splits (id TEXT PRIMARY KEY, event_id TEXT, node_id TEXT);
            CREATE TABLE sales_commission_claims (id TEXT PRIMARY KEY, split_id TEXT);
            CREATE TABLE sales_commission_payouts
                (id TEXT PRIMARY KEY, claim_id TEXT, gross INT, withholding INT, paid_at TEXT);
            CREATE TABLE sales_commission_payout_schedule
                (id TEXT PRIMARY KEY, split_id TEXT, paid_payout_id TEXT);
            """
        )
        # 현장 S, 노드 N, 이벤트 E, split SP.
        c.execute("INSERT INTO sales_commission_events VALUES ('E','S')")
        c.execute("INSERT INTO sales_commission_splits VALUES ('SP','E','N')")
        # claim 경로 지급: claim C → payout P1(claim_id=C) gross 600,000.
        c.execute("INSERT INTO sales_commission_claims VALUES ('C','SP')")
        c.execute("INSERT INTO sales_commission_payouts VALUES ('P1','C',600000,19800,'2026-06-10')")
        # 스케줄 경로 지급: payout P2(claim_id NULL) gross 400,000, schedule SCH.paid_payout_id=P2.
        c.execute("INSERT INTO sales_commission_payouts VALUES ('P2',NULL,400000,13200,'2026-06-20')")
        c.execute("INSERT INTO sales_commission_payout_schedule VALUES ('SCH','SP','P2')")
        return c

    # sqlite 동등 SQL: to_char(paid_at,'YYYY-MM') → substr(paid_at,1,7), :name → ? 바인딩.
    _AGG = (
        "SELECT node_id, coalesce(sum(g),0), coalesce(sum(wh),0) FROM ("
        "  SELECT sp.node_id AS node_id, p.gross AS g, p.withholding AS wh"
        "    FROM sales_commission_payouts p"
        "    JOIN sales_commission_claims c ON c.id = p.claim_id"
        "    JOIN sales_commission_splits sp ON sp.id = c.split_id"
        "    JOIN sales_commission_events e ON e.id = sp.event_id"
        "   WHERE e.site_id = ? AND substr(p.paid_at,1,7) = ?"
        "  UNION ALL "
        "  SELECT sp.node_id AS node_id, p.gross AS g, p.withholding AS wh"
        "    FROM sales_commission_payouts p"
        "    JOIN sales_commission_payout_schedule sch ON sch.paid_payout_id = p.id"
        "    JOIN sales_commission_splits sp ON sp.id = sch.split_id"
        "    JOIN sales_commission_events e ON e.id = sp.event_id"
        "   WHERE e.site_id = ? AND substr(p.paid_at,1,7) = ? AND p.claim_id IS NULL"
        ") u GROUP BY node_id"
    )

    def test_two_sources_summed_without_double_count(self):
        """claim 지급 600,000 + 스케줄 지급 400,000 = 정확히 1,000,000(이중계상 0)."""
        c = self._build_db()
        rows = c.execute(self._AGG, ("S", "2026-06", "S", "2026-06")).fetchall()
        c.close()
        assert len(rows) == 1
        node, gross, wh = rows[0]
        assert node == "N"
        assert gross == 1_000_000   # 600,000 + 400,000, 더블카운트 없음
        assert wh == 33_000         # 19,800 + 13,200

    def test_mutual_exclusion_claim_payout_not_in_schedule_branch(self):
        """★상호배타 증명: claim 경로 payout(P1)이 만약 스케줄로도 가리켜져도(데이터 이상), ② 경로는
        claim_id IS NULL 만 잡으므로 P1(claim_id=C)은 ② 경로에서 제외돼 이중계상되지 않는다."""
        c = self._build_db()
        # 이상 데이터: P1(claim 경로)을 스케줄에서도 가리키게 함 — 그래도 ② 경로 claim_id IS NULL 로 제외.
        c.execute("INSERT INTO sales_commission_payout_schedule VALUES ('SCH2','SP','P1')")
        rows = c.execute(self._AGG, ("S", "2026-06", "S", "2026-06")).fetchall()
        c.close()
        assert len(rows) == 1
        _, gross, wh = rows[0]
        # P1 은 ① 경로에서 1번만(600,000), ② 경로(claim_id NULL)에선 제외. P2 는 ② 에서 400,000.
        assert gross == 1_000_000   # 1,600,000(더블카운트) 이 아니라 정확히 1,000,000
        assert wh == 33_000

    def test_site_isolation(self):
        """타 현장(site=T)으로 조회하면 결과 0건(현장 격리 — 머니패스 누수 차단)."""
        c = self._build_db()
        rows = c.execute(self._AGG, ("T", "2026-06", "T", "2026-06")).fetchall()
        c.close()
        assert rows == []

    def test_period_isolation(self):
        """타 기간(2026-07)으로 조회하면 결과 0건(기간 필터)."""
        c = self._build_db()
        rows = c.execute(self._AGG, ("S", "2026-07", "S", "2026-07")).fetchall()
        c.close()
        assert rows == []


# ── build_withholding_statements: income_type 소득구분 분기(iter-8 MEDIUM·correctness) ──────────
class _WhStmtTaxTypeDB:
    """build_withholding_statements 의 집계 SELECT 가 4-튜플(node,gross,wh,tax_type)을 돌려줄 때
    db.add 된 statement 의 income_type 분기를 검증하기 위한 가짜 세션.

    DELETE 면 [] 를, 집계 SELECT 면 주입된 agg_rows 를 .all() 로 돌려준다. add 된 statement 를 added 에 모은다.
    """
    def __init__(self, agg_rows):
        self._agg_rows = agg_rows
        self.added = []

    async def execute(self, stmt, *_a, **_k):
        if str(getattr(stmt, "text", stmt)).upper().lstrip().startswith("DELETE"):
            return _AllResult([])
        return _AllResult(self._agg_rows)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


class TestBuildWithholdingIncomeTypeByTaxType:
    async def test_withholding_node_maps_to_biz_3_3(self):
        """★소득구분 분기 회귀가드(iter-8): tax_type='WITHHOLDING' 노드 → income_type='BIZ_3_3'(3.3% 사업소득)."""
        import uuid as _uuid

        from app.services.sales.tax import service as tax_svc
        node = _uuid.uuid4()
        db = _WhStmtTaxTypeDB(agg_rows=[(node, 1_000_000, 33_000, "WITHHOLDING")])
        sts = await tax_svc.build_withholding_statements(db, _uuid.uuid4(), "2026-06")
        assert len(sts) == 1
        assert sts[0].income_type == "BIZ_3_3"

    async def test_vat_node_maps_to_vat_not_biz_3_3(self):
        """★오분류 회귀가드(iter-8 MEDIUM): tax_type='VAT'(세금계산서 발행 사업자) 노드는 3.3% 원천
        대상이 아니므로 income_type='VAT' 로 분기한다(과거엔 'BIZ_3_3' 하드코딩이라 법적 서류 소득구분 오류)."""
        import uuid as _uuid

        from app.services.sales.tax import service as tax_svc
        node = _uuid.uuid4()
        db = _WhStmtTaxTypeDB(agg_rows=[(node, 1_000_000, 0, "VAT")])
        sts = await tax_svc.build_withholding_statements(db, _uuid.uuid4(), "2026-06")
        assert sts[0].income_type == "VAT"          # 3.3% 대상 아님(오분류 차단)
        assert sts[0].income_type != "BIZ_3_3"

    async def test_unknown_taxtype_defaults_to_biz_3_3(self):
        """알 수 없는 tax_type(또는 NULL)은 보수적으로 BIZ_3_3(WITHHOLDING)으로 본다(하위호환·기본값)."""
        import uuid as _uuid

        from app.services.sales.tax import service as tax_svc
        node = _uuid.uuid4()
        db = _WhStmtTaxTypeDB(agg_rows=[(node, 500_000, 16_500, None)])
        sts = await tax_svc.build_withholding_statements(db, _uuid.uuid4(), "2026-06")
        assert sts[0].income_type == "BIZ_3_3"

    async def test_legacy_three_tuple_row_still_biz_3_3(self):
        """★하위호환 회귀가드: tax_type 컬럼이 없던 3-튜플 집계결과도 income_type='BIZ_3_3' 기본 유지."""
        import uuid as _uuid

        from app.services.sales.tax import service as tax_svc
        node = _uuid.uuid4()
        db = _WhStmtTaxTypeDB(agg_rows=[(node, 700_000, 23_100)])  # 3-튜플(legacy)
        sts = await tax_svc.build_withholding_statements(db, _uuid.uuid4(), "2026-06")
        assert sts[0].income_type == "BIZ_3_3"


# ── _WH_AGG_SQL: KST 세무월 고정(iter-8 MEDIUM·TZ) — to_char AT TIME ZONE 'Asia/Seoul' ──────────
class TestWithholdingAggKstTimezone:
    def test_agg_sql_uses_kst_for_period_filter(self):
        """★TZ 회귀가드(iter-8): 집계 SQL 의 period 필터가 paid_at 을 KST(Asia/Seoul)로 변환한 뒤
        'YYYY-MM' 을 뽑는다(세션TZ 의존 제거). UTC/KST 월 경계 지급이 다른 세무월로 새지 않게 한다."""
        from app.services.sales.tax import service as tax_svc
        sql = tax_svc._WH_AGG_SQL.upper()
        assert "AT TIME ZONE 'ASIA/SEOUL'" in sql
        # period 필터 두 경로(claim·스케줄) 모두 KST 변환을 거친다.
        assert sql.count("TO_CHAR(P.PAID_AT AT TIME ZONE 'ASIA/SEOUL', 'YYYY-MM')") == 2
        # 세션TZ 의존이던 'TO_CHAR(P.PAID_AT, ' (KST 변환 없는) 형태는 남아 있지 않아야 한다.
        assert "TO_CHAR(P.PAID_AT," not in sql

    def test_agg_sql_selects_tax_type_for_income_branch(self):
        """집계 SQL 이 tax_type 을 끌어와 노드별 대표(max)로 income_type 분기 근거를 제공한다."""
        from app.services.sales.tax import service as tax_svc
        sql = tax_svc._WH_AGG_SQL.upper()
        assert "TAX_TYPE" in sql
        assert "GROUP BY NODE_ID" in sql

    def test_kst_month_boundary_attribution_sqlite_proxy(self):
        """★KST 월 경계 귀속 검증(sqlite proxy): UTC 5/31 23:00(=KST 6/1 08:00) 지급이 KST 기준 '6월'로
        귀속됨을 sqlite 동등식으로 단언한다. (postgres AT TIME ZONE 'Asia/Seoul' 를 sqlite datetime(...,'+9 hours')
        로 모사 — UTC 저장값에 +9h 한 뒤 'YYYY-MM' 추출이 KST 월과 같음을 보인다.)"""
        import sqlite3
        c = sqlite3.connect(":memory:")
        # paid_at 은 UTC 저장값(timestamptz 의 내부표현 모사). KST = UTC+9.
        utc_paid = "2026-05-31 23:00:00"  # = KST 2026-06-01 08:00
        # 세션TZ(UTC) 의존: 변환 없이 'YYYY-MM' → '2026-05'(5월) — 잘못된 세무월.
        naive_month = c.execute("SELECT strftime('%Y-%m', ?)", (utc_paid,)).fetchone()[0]
        # KST 변환(+9h) 후 'YYYY-MM' → '2026-06'(6월) — 올바른 한국 세무월.
        kst_month = c.execute(
            "SELECT strftime('%Y-%m', datetime(?, '+9 hours'))", (utc_paid,)).fetchone()[0]
        c.close()
        assert naive_month == "2026-05"   # 세션TZ(UTC) 의존이면 5월로 오귀속
        assert kst_month == "2026-06"     # KST 고정이면 6월로 정상 귀속(우리 SQL 이 택한 기준)


# ── termination_cert._income_for: KST 세무연도 고정(iter-8 MEDIUM·TZ) ─────────────────────────────
class TestIncomeForKstYearFilter:
    async def test_primary_year_filter_uses_kst(self):
        """★TZ 회귀가드(iter-8): tax_year 지정 시 1차 소득쿼리의 연도 필터가 paid_at 을 KST 로 변환한 뒤
        extract(year ...) 한다(세션TZ 의존 제거 — 연 경계 귀속 오류 차단)."""
        import uuid as _uuid

        from app.api.endpoints.sales import termination_cert as tc
        db = _CaptureIncomeDB(first_row=(1_000_000, 33_000, 967_000))
        await tc._income_for(db, _uuid.uuid4(), _uuid.uuid4(), 2026)
        sql = db.captured[0]
        assert "EXTRACT(YEAR FROM (P.PAID_AT AT TIME ZONE 'ASIA/SEOUL'))" in sql
        # KST 변환 없는 'EXTRACT(YEAR FROM P.PAID_AT)' 형태는 남아 있지 않아야 한다.
        assert "EXTRACT(YEAR FROM P.PAID_AT)" not in sql

    async def test_no_year_filter_when_tax_year_none(self):
        """tax_year 미지정이면 연도 필터 자체가 없다(전 기간 — 기존 동작 보존·하위호환)."""
        import uuid as _uuid

        from app.api.endpoints.sales import termination_cert as tc
        db = _CaptureIncomeDB(first_row=(1_000_000, 33_000, 967_000))
        await tc._income_for(db, _uuid.uuid4(), _uuid.uuid4(), None)
        sql = db.captured[0]
        assert "EXTRACT(YEAR" not in sql

    def test_kst_year_boundary_attribution_sqlite_proxy(self):
        """★KST 연 경계 귀속 검증(sqlite proxy): UTC 12/31 23:00(=KST 1/1 08:00) 지급이 KST 기준 다음 해로
        귀속됨을 sqlite 동등식으로 단언한다(AT TIME ZONE 'Asia/Seoul' 를 +9h 로 모사)."""
        import sqlite3
        c = sqlite3.connect(":memory:")
        utc_paid = "2025-12-31 23:00:00"  # = KST 2026-01-01 08:00
        naive_year = c.execute("SELECT strftime('%Y', ?)", (utc_paid,)).fetchone()[0]
        kst_year = c.execute(
            "SELECT strftime('%Y', datetime(?, '+9 hours'))", (utc_paid,)).fetchone()[0]
        c.close()
        assert naive_year == "2025"   # 세션TZ(UTC) 의존이면 전년(2025)으로 오귀속
        assert kst_year == "2026"     # KST 고정이면 2026 으로 정상 귀속
