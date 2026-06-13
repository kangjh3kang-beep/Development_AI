"""SGIS 인구/가구 라이브 보조 로직 회귀 테스트(순수함수).

- 법정동→KOSTAT 시도코드 매핑(경기 41→31 등; 서울만 11로 동일).
- 실측 평균가구원수 기반 가구원수 분포 추정(합≈100·단조: 평균↑→1인↓·4인+↑).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apps.api.integrations.sgis_client import SgisClient  # noqa: E402


class TestSidoMap:
    def test_법정동_KOSTAT_매핑(self):
        m = SgisClient._LAWD_TO_KOSTAT_SIDO
        assert m["11"] == "11"      # 서울(동일)
        assert m["41"] == "31"      # 경기
        assert m["48"] == "38"      # 경남
        assert m["51"] == "32"      # 강원특별자치도→강원
        assert m["52"] == "35"      # 전북특별자치도→전북


class TestHouseholdEstimate:
    def test_합계_약100(self):
        d = SgisClient._estimate_household_sizes(2.3)
        assert abs(sum(d.values()) - 100.0) < 0.5

    def test_단조성_평균클수록_1인감소_4인증가(self):
        small = SgisClient._estimate_household_sizes(1.8)
        large = SgisClient._estimate_household_sizes(2.9)
        assert small["1_person"] > large["1_person"]
        assert large["4_over"] > small["4_over"]

    def test_경계값_안정(self):
        for avg in (0.0, 1.0, 2.3, 3.5, 99.0):
            d = SgisClient._estimate_household_sizes(avg)
            assert all(v >= 0 for v in d.values())
            assert abs(sum(d.values()) - 100.0) < 0.6


class TestAgeTypeLabels:
    def test_10세단위_10구간(self):
        labels = SgisClient._AGE_TYPE_LABELS
        assert len(labels) == 10
        assert labels["30"] == "0-9" and labels["34"] == "40-49" and labels["39"] == "90+"
        # 코드 30~39 연속
        assert sorted(labels.keys()) == [str(i) for i in range(30, 40)]
