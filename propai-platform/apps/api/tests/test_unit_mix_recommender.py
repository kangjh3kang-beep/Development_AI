"""I6 수요기반 평형 MD 추천(unit_mix_recommender) 결정론 회귀 테스트."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.market.unit_mix_recommender import BANDS, recommend_unit_mix  # noqa: E402


class TestRecommend:
    def test_1인가구_우세시_소형_주력(self):
        r = recommend_unit_mix({"1_person": 60, "2_person": 20, "3_person": 15, "4_over": 5})
        assert r["dominant_band"] == "소형(~49㎡)"
        # 비중 합 100% 근사
        assert abs(sum(r["recommended_mix"].values()) - 100.0) < 0.5

    def test_4인이상_우세시_대형_포함(self):
        r = recommend_unit_mix({"1_person": 5, "2_person": 10, "3_person": 25, "4_over": 60})
        assert r["dominant_band"] in ("84㎡", "99㎡+")
        assert "99㎡+" in r["recommended_mix"]

    def test_가구데이터_없으면_정직_unavailable(self):
        r = recommend_unit_mix(None)
        assert r["data_source"] == "unavailable"
        assert "recommended_mix" not in r  # 가짜 추천 금지
        r2 = recommend_unit_mix({"1_person": 0, "2_person": 0})
        assert r2["data_source"] == "unavailable"

    def test_출처_전파(self):
        r = recommend_unit_mix({"2_person": 50, "3_person": 50}, data_source="fallback")
        assert r["data_source"] == "fallback"

    def test_밴드_정의_일관(self):
        assert "84㎡" in BANDS and "소형(~49㎡)" in BANDS

    def test_rationale_근거문장(self):
        r = recommend_unit_mix({"1_person": 70, "2_person": 30})
        assert "가구" in r["rationale"] and "%" in r["rationale"]
