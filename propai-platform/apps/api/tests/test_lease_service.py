"""LeaseService 단위 테스트.

임대차 기간 계산, IFRS16 상환 스케줄 생성 등 정적 메서드를 검증한다.
"""

import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.lease_service import LeaseService


class TestLeaseTermMonths:
    """_lease_term_months 정적 메서드 테스트."""

    def test_1년_12개월(self):
        start = datetime(2025, 1, 1)
        end = datetime(2026, 1, 1)
        assert LeaseService._lease_term_months(start, end) == 12

    def test_2년_24개월(self):
        start = datetime(2025, 1, 1)
        end = datetime(2027, 1, 1)
        assert LeaseService._lease_term_months(start, end) == 24

    def test_6개월(self):
        start = datetime(2025, 1, 1)
        end = datetime(2025, 7, 1)
        months = LeaseService._lease_term_months(start, end)
        assert months == 6

    def test_최소_1개월(self):
        """같은 날이라도 최소 1개월."""
        start = datetime(2025, 1, 1)
        end = datetime(2025, 1, 2)
        assert LeaseService._lease_term_months(start, end) >= 1

    def test_5년_60개월(self):
        start = datetime(2025, 1, 1)
        end = datetime(2030, 1, 1)
        months = LeaseService._lease_term_months(start, end)
        assert months == pytest.approx(60, abs=1)


class TestBuildPaymentSchedule:
    """_build_payment_schedule 정적 메서드 테스트."""

    def test_스케줄_길이_기간_일치(self):
        schedule, _ = LeaseService._build_payment_schedule(
            monthly_rent_krw=1_000_000,
            lease_term_months=12,
            annual_discount_rate=0.05,
        )
        assert len(schedule) == 12

    def test_개시부채_양수(self):
        _, opening = LeaseService._build_payment_schedule(
            monthly_rent_krw=1_000_000,
            lease_term_months=12,
            annual_discount_rate=0.05,
        )
        assert opening > 0

    def test_개시부채_단순합계_미만(self):
        """할인으로 인해 개시부채 < 단순 임대료 합계."""
        monthly = 1_000_000
        term = 24
        _, opening = LeaseService._build_payment_schedule(
            monthly_rent_krw=monthly,
            lease_term_months=term,
            annual_discount_rate=0.05,
        )
        assert opening < monthly * term

    def test_할인율_0이면_단순합계_근사(self):
        """할인율 0%에 가까우면 개시부채 ≈ 단순합계."""
        monthly = 1_000_000
        term = 12
        _, opening = LeaseService._build_payment_schedule(
            monthly_rent_krw=monthly,
            lease_term_months=term,
            annual_discount_rate=0.001,
        )
        assert opening == pytest.approx(monthly * term, rel=0.01)

    def test_기간별_payment_일정(self):
        schedule, _ = LeaseService._build_payment_schedule(
            monthly_rent_krw=2_000_000,
            lease_term_months=6,
            annual_discount_rate=0.06,
        )
        for entry in schedule:
            assert entry["payment_krw"] == 2_000_000
            assert entry["interest_krw"] >= 0
            assert entry["principal_krw"] >= 0
            assert entry["opening_liability_krw"] >= 0
            assert entry["closing_liability_krw"] >= 0

    def test_마지막_기간_closing_0근사(self):
        schedule, _ = LeaseService._build_payment_schedule(
            monthly_rent_krw=1_000_000,
            lease_term_months=12,
            annual_discount_rate=0.05,
        )
        assert schedule[-1]["closing_liability_krw"] == pytest.approx(0, abs=100)

    def test_이자_감소_추세(self):
        """이자는 시간에 따라 감소해야 한다."""
        schedule, _ = LeaseService._build_payment_schedule(
            monthly_rent_krw=1_000_000,
            lease_term_months=12,
            annual_discount_rate=0.08,
        )
        first_interest = schedule[0]["interest_krw"]
        last_interest = schedule[-1]["interest_krw"]
        assert first_interest >= last_interest


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
