"""Re100TrackerService 단위 테스트.

RE100 이행률, 배출량, K-ETS 비용, 조달 수단 비교, 로드맵 생성을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.re100_tracker_service import (
    DEFAULT_KTS_PRICE,
    Re100TrackerService,
)


class TestRe100이행률:
    """RE100 이행률 계산 테스트."""

    def test_re100_이행률_50퍼센트(self):
        """50/100 MWh = 50% 이행률."""
        result = Re100TrackerService._calc_re100_rate(50, 100)
        assert result == 0.5

    def test_re100_이행률_100퍼센트(self):
        """100/100 MWh = 100% 이행률."""
        result = Re100TrackerService._calc_re100_rate(100, 100)
        assert result == 1.0

    def test_re100_이행률_0(self):
        """0/100 MWh = 0% 이행률."""
        result = Re100TrackerService._calc_re100_rate(0, 100)
        assert result == 0.0

    def test_re100_총전력_0(self):
        """총 전력 사용량 0이면 이행률 0.0 반환."""
        result = Re100TrackerService._calc_re100_rate(50, 0)
        assert result == 0.0


class TestEmissions:
    """배출량 계산 테스트."""

    def test_배출량_계산(self):
        """비재생 50 MWh x 0.4629 = 23.145 tCO2eq."""
        total, baseline, excess = Re100TrackerService._calc_emissions(100, 50)
        assert total == pytest.approx(23.145, abs=0.001)
        assert baseline == 0.0
        assert excess == total

    def test_배출량_re100_100(self):
        """RE100 100% 달성 시 초과 배출량 0."""
        total, baseline, excess = Re100TrackerService._calc_emissions(100, 100)
        assert total == 0.0
        assert baseline == 0.0
        assert excess == 0.0


class TestKtsCost:
    """K-ETS 비용 산출 테스트."""

    def test_kts_비용_계산(self):
        """100 tCO2eq x 18,000원 = 1,800,000원."""
        result = Re100TrackerService._calc_kts_cost(100, DEFAULT_KTS_PRICE)
        assert result == 1_800_000

    def test_kts_비용_0_초과배출없음(self):
        """초과 배출량 0이면 K-ETS 비용 0."""
        result = Re100TrackerService._calc_kts_cost(0)
        assert result == 0.0


class TestProcurement:
    """조달 수단 비용 비교 테스트."""

    def test_조달수단_비용비교_정렬(self):
        """비용 오름차순: 녹색프리미엄 < REC구매 < PPA < 자가발전 < 지분투자."""
        results = Re100TrackerService._compare_procurement(100)
        methods = [r["method"] for r in results]
        assert methods == ["녹색프리미엄", "REC구매", "PPA", "자가발전", "지분투자"]

    def test_조달수단_5가지(self):
        """조달 수단은 정확히 5개."""
        results = Re100TrackerService._compare_procurement(100)
        assert len(results) == 5


class TestRoadmap:
    """RE100 이행 로드맵 테스트."""

    def test_로드맵_2030_목표(self):
        """현재 30% → 2030 목표 60%, gap = 30%."""
        roadmap = Re100TrackerService._generate_roadmap(0.3, 1000, 2025)
        # 2030 목표 항목 찾기
        target_2030 = next(r for r in roadmap if r["target_year"] == 2030)
        assert target_2030["target_rate"] == 0.60
        assert target_2030["current_gap"] == pytest.approx(0.3, abs=0.001)
        assert target_2030["additional_renewable_mwh"] == pytest.approx(300.0, abs=0.1)
        # 5년간 연 60 MWh 증가 필요
        assert target_2030["annual_increase_mwh"] == pytest.approx(60.0, abs=0.1)

    def test_로드맵_이미_달성(self):
        """현재 70% > 2030 목표 60% → gap = 0."""
        roadmap = Re100TrackerService._generate_roadmap(0.7, 1000, 2025)
        target_2030 = next(r for r in roadmap if r["target_year"] == 2030)
        assert target_2030["current_gap"] == 0.0
        assert target_2030["additional_renewable_mwh"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
