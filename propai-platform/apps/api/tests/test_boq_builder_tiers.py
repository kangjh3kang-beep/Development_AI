"""W3-3(P9) — boq_builder.build_boq 의 Q1~Q4 등급 분포(tier_distribution) 배선 테스트.

build_boq 는 이미 항목마다 qto_source(bim/derived)를 부착하고 있었다(기존 동작).
이 테스트는 그 신호가 Q1/Q2 로 정직하게 재-표기되고, OriginCostCalculator 12단계
요율 항목(간접노무비·보험료·일반관리비·이윤·부가세 등)이 Q3 로 합산되는지 검증한다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from app.services.cost.boq_builder import build_boq  # noqa: E402


@pytest.mark.asyncio
class TestBuildBoqTierDistribution:
    async def test_derived_소스_항목은_Q2(self):
        boq = await build_boq(
            building_type="apartment", total_gfa_sqm=10000,
            floor_count_above=15, floor_count_below=2, structure_type="RC",
            qto_source="derived",
        )
        assert all(it["tier"] == "Q2_PARAMETRIC" for it in boq["items"])

    async def test_bim_소스_항목은_Q1(self):
        boq = await build_boq(
            building_type="apartment", total_gfa_sqm=10000,
            floor_count_above=15, floor_count_below=2, structure_type="RC",
            qto_source="bim",
        )
        assert all(it["tier"] == "Q1_MEASURED" for it in boq["items"])

    async def test_summary에_tier_distribution_부착(self):
        boq = await build_boq(
            building_type="apartment", total_gfa_sqm=10000,
            floor_count_above=15, floor_count_below=2, structure_type="RC",
            qto_source="derived",
        )
        td = boq["summary"]["tier_distribution"]
        by_tier = td["by_tier"]
        # 원가계산서 12단계 요율 항목(indirect_labor~vat, 보험료 소계 포함 13개)이 Q3 로 집계.
        assert by_tier["Q3_FACTORED"]["count"] == 13
        assert by_tier["Q2_PARAMETRIC"]["count"] == len(boq["items"])
        assert by_tier["Q3_FACTORED"]["amount_won"] > 0

    async def test_직접비_파라메트릭_간접비_계수_비중_합리적(self):
        """직접비(Q2, 표준물량)와 간접비(Q3, 법정요율)의 비중이 합리적 범위(직접비 우세)."""
        boq = await build_boq(
            building_type="apartment", total_gfa_sqm=10000,
            floor_count_above=15, floor_count_below=2, structure_type="RC",
            qto_source="derived",
        )
        by_tier = boq["summary"]["tier_distribution"]["by_tier"]
        # 직접공사비(콘크리트·철근 등)가 법정 제비율(보험·이윤·부가세 등)보다 커야 정상.
        assert by_tier["Q2_PARAMETRIC"]["amount_won"] > by_tier["Q3_FACTORED"]["amount_won"]

    async def test_items_에_tier_basis_설명_포함(self):
        boq = await build_boq(
            building_type="apartment", total_gfa_sqm=10000,
            floor_count_above=15, floor_count_below=2, structure_type="RC",
            qto_source="derived",
        )
        assert "qto_source" in boq["items"][0]["tier_basis"]
