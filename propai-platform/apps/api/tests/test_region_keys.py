"""주소→provider별 시군구명 추출 회귀 테스트.

통합시(수원/성남 등)는 KOSIS(시 단위 '수원시')와 SGIS(시+구 '수원시 장안구')가 다르게
표기하므로 provider별로 키를 다르게 산출해야 한다. 광역/특별시 자치구는 양쪽 동일('강남구').
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apps.api.app.services.market.market_report_service import _extract_region_keys  # noqa: E402


class TestRegionKeys:
    def test_광역시_자치구_양쪽동일(self):
        assert _extract_region_keys("서울 강남구 역삼동") == ("강남구", "강남구")
        assert _extract_region_keys("부산광역시 해운대구 우동") == ("해운대구", "해운대구")
        assert _extract_region_keys("서울특별시 강남구 역삼동") == ("강남구", "강남구")

    def test_일반시(self):
        assert _extract_region_keys("경기 파주시 운정동") == ("파주시", "파주시")

    def test_군(self):
        assert _extract_region_keys("강원 평창군 대관령면") == ("평창군", "평창군")

    def test_통합시_자치구_KOSIS시_SGIS시구(self):
        assert _extract_region_keys("경기 수원시 장안구 율전동") == ("수원시", "수원시 장안구")
        assert _extract_region_keys("경기 성남시 분당구 정자동") == ("성남시", "성남시 분당구")

    def test_빈입력(self):
        assert _extract_region_keys(None) == (None, None)
        assert _extract_region_keys("좌표만있음") == (None, None)
