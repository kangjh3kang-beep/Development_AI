"""AICostsService 단위 테스트.

월 시작일 계산, 월 라벨 형식 등 정적 메서드를 검증한다.
"""

import os
import sys
from datetime import datetime, timezone
UTC = timezone.utc

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.ai_costs_service import AICostsService


class TestMonthStart:
    """month_start 정적 메서드 테스트."""

    def test_일자_1일(self):
        result = AICostsService.month_start()
        assert result.day == 1

    def test_시분초_0(self):
        result = AICostsService.month_start()
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0
        assert result.microsecond == 0

    def test_UTC_타임존(self):
        result = AICostsService.month_start()
        assert result.tzinfo == UTC

    def test_현재월_기준(self):
        now = datetime.now(UTC)
        result = AICostsService.month_start()
        assert result.year == now.year
        assert result.month == now.month


class TestCurrentMonthLabel:
    """current_month_label 정적 메서드 테스트."""

    def test_YYYY_MM_형식(self):
        label = AICostsService.current_month_label()
        # "YYYY-MM" 형식 검증
        parts = label.split("-")
        assert len(parts) == 2
        assert len(parts[0]) == 4
        assert len(parts[1]) == 2

    def test_현재월_일치(self):
        now = datetime.now(UTC)
        expected = now.strftime("%Y-%m")
        assert AICostsService.current_month_label() == expected

    def test_month_start_기반(self):
        """current_month_label은 month_start를 사용한다."""
        start = AICostsService.month_start()
        label = AICostsService.current_month_label()
        assert label == start.strftime("%Y-%m")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
