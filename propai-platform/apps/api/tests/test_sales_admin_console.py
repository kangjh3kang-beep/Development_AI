"""분양 관리자 콘솔(#10) 순수로직 회귀 안전망 — iter-5 correctness 게이트.

대상 순수함수(DB 무관)를 단위테스트로 고정해 다음 회귀를 영구 차단한다.
- _validate_ym: '$' 후행개행 우회('2026-06\\n' PASS) 회귀 차단(이제 \\Z=re.fullmatch).
- _reconcile: 반올림 잔차(±회차수)는 흡수(거짓경보 제거)·약정 비율결함/수납초과는 적발.
- _classify_error: int/str sqlstate 양쪽을 PERMISSION/DB_CONNECTION/DB_ERROR/INTERNAL 로 분류.
- _month_bounds: 'YYYY-MM' → (이달1일, 다음달1일) date. 12월 경계 연도 넘김.
- 모듈전역 게이트(_acct_ready/_wage_ready)는 fixture 로 매 테스트 reset(test isolation).
"""
from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

from app.api.endpoints.sales.views import _classify_error  # noqa: E402
from app.services.sales.admin import console  # noqa: E402
from app.services.sales.admin.console import (  # noqa: E402
    _month_bounds,
    _reconcile,
    _validate_ym,
)


@pytest.fixture(autouse=True)
def _reset_ddl_gates():
    """모듈전역 1회 게이트를 매 테스트 reset — 다른 테스트의 부작용이 새지 않게 격리."""
    console._acct_ready = False
    console._wage_ready = False
    yield
    console._acct_ready = False
    console._wage_ready = False


# ── _validate_ym: 후행개행 우회 회귀 차단 ──────────────────────────────────────
class TestValidateYm:
    def test_valid_passes(self):
        assert _validate_ym("2026-06") == "2026-06"
        assert _validate_ym("2026-01") == "2026-01"
        assert _validate_ym("2026-12") == "2026-12"

    def test_trailing_newline_rejected(self):
        """★핵심 회귀: '$'는 후행 개행을 허용했다 → '\\Z'(re.fullmatch)로 REJECT."""
        with pytest.raises(ValueError):
            _validate_ym("2026-06\n")

    def test_trailing_and_leading_space_rejected(self):
        with pytest.raises(ValueError):
            _validate_ym("2026-06 ")
        with pytest.raises(ValueError):
            _validate_ym(" 2026-06")

    def test_month_out_of_range_rejected(self):
        with pytest.raises(ValueError):
            _validate_ym("2026-13")
        with pytest.raises(ValueError):
            _validate_ym("2026-00")

    def test_single_digit_month_rejected(self):
        with pytest.raises(ValueError):
            _validate_ym("2026-6")

    def test_wrong_separator_rejected(self):
        with pytest.raises(ValueError):
            _validate_ym("2026/06")

    def test_non_string_rejected(self):
        with pytest.raises(ValueError):
            _validate_ym(None)  # type: ignore[arg-type]


# ── _reconcile: 반올림 흡수 vs 계약결함/수납초과 적발 ──────────────────────────
class TestReconcile:
    def test_no_schedule_is_none(self):
        """약정표 부재(scheduled_total=0) → balanced=None(판정보류, 거짓안심 금지)."""
        r = _reconcile(1_000_000, 0, 0, 0, 0)
        assert r["balanced"] is None
        assert r["discrepancies"] == []

    def test_rounding_residual_absorbed(self):
        """★핵심 회귀: round 잔차(회차4개, 약정합 2원 부족)는 ±tol(=4) 내 → 통과."""
        r = _reconcile(1_000_000, 999_998, 0, 4, 0)
        assert r["balanced"] is True
        assert r["discrepancies"] == []
        assert r["tolerance"] == 4

    def test_exact_match_passes(self):
        r = _reconcile(1_000_000, 1_000_000, 0, 4, 0)
        assert r["balanced"] is True

    def test_delta_beyond_tolerance_flags_schedule_vs_contract(self):
        """약정-계약 차이가 허용오차(회차수) 초과 → schedule_vs_contract 적발."""
        r = _reconcile(1_000_000, 1_200_000, 0, 4, 0)
        assert r["balanced"] is False
        assert "schedule_vs_contract" in {d["key"] for d in r["discrepancies"]}

    def test_ratio_invalid_flagged_separately(self):
        """약정 비율결함(ratio_invalid_count>0) → schedule_ratio_invalid 로 분리 적발."""
        r = _reconcile(1_000_000, 800_000, 0, 4, 1)
        keys = {d["key"] for d in r["discrepancies"]}
        assert r["balanced"] is False
        assert "schedule_ratio_invalid" in keys

    def test_paid_exceeds_schedule_flagged(self):
        """회차 실수납이 약정총액 초과 → paid_exceeds_schedule(반올림 무관, 엄격)."""
        r = _reconcile(1_000_000, 1_000_000, 1_000_005, 4, 0)
        assert r["balanced"] is False
        assert "paid_exceeds_schedule" in {d["key"] for d in r["discrepancies"]}

    def test_tolerance_floor_eps_when_no_installments(self):
        """회차수 0이어도 eps=1원 잔차는 흡수(정수 반올림 하한)."""
        r = _reconcile(1_000_000, 999_999, 0, 0, 0)
        assert r["tolerance"] == 1
        assert r["balanced"] is True


# ── _classify_error: int/str sqlstate 양쪽 정밀 분류 ──────────────────────────
class _FakeOrigError(Exception):
    def __init__(self, sqlstate):
        super().__init__("fake")
        self.sqlstate = sqlstate


def _dbapi(sqlstate):
    return DBAPIError("stmt", {}, _FakeOrigError(sqlstate))


class TestClassifyError:
    def test_permission_str(self):
        assert _classify_error(_dbapi("42501")) == "PERMISSION"

    def test_permission_int(self):
        """★int sqlstate 도 PERMISSION 으로 분류(과거엔 DB_ERROR 로 오분류)."""
        assert _classify_error(_dbapi(42501)) == "PERMISSION"

    def test_connection_str(self):
        assert _classify_error(_dbapi("08006")) == "DB_CONNECTION"
        assert _classify_error(_dbapi("08001")) == "DB_CONNECTION"

    def test_generic_db_error(self):
        assert _classify_error(_dbapi("42P01")) == "DB_ERROR"
        assert _classify_error(_dbapi("42703")) == "DB_ERROR"

    def test_non_db_is_internal(self):
        assert _classify_error(ValueError("x")) == "INTERNAL"
        assert _classify_error(RuntimeError("y")) == "INTERNAL"


# ── _month_bounds: 월 경계(연도 넘김) ─────────────────────────────────────────
class TestMonthBounds:
    def test_basic(self):
        start, end = _month_bounds("2026-06")
        assert start == date(2026, 6, 1)
        assert end == date(2026, 7, 1)

    def test_december_rolls_year(self):
        start, end = _month_bounds("2026-12")
        assert start == date(2026, 12, 1)
        assert end == date(2027, 1, 1)

    def test_invalid_ym_raises(self):
        """_month_bounds 도 _validate_ym 경유 — 비정규 ym 은 ValueError."""
        with pytest.raises(ValueError):
            _month_bounds("2026-13")
        with pytest.raises(ValueError):
            _month_bounds("2026-06\n")
