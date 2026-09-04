"""W3-3(P9) — geometry_qto.geometry_takeoff 항목의 Q1~Q4 등급 표기 테스트.

geometry_takeoff 는 매스치수×표준 부재두께 산식이라(BIM 요소 1:1 실측 집계가 아님)
형상 입력의 출처(실치수 매스 vs GFA 역산)와 무관하게 물량 자체는 항상 Q2(파라메트릭)다
— 억지로 Q1 승격하지 않는다(정직 원칙).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.cost.geometry_qto import geometry_takeoff  # noqa: E402


class TestGeometryTakeoffTier:
    def test_모든_항목이_Q2(self):
        g = geometry_takeoff(width_m=20, depth_m=15, floors_above=10, floors_below=1)
        assert len(g["items"]) == 3
        assert all(it["tier"] == "Q2_PARAMETRIC" for it in g["items"])

    def test_tier_basis_설명_포함(self):
        g = geometry_takeoff(width_m=20, depth_m=15, floors_above=10)
        assert "파라메트릭" in g["items"][0]["tier_basis"]

    def test_기존_키_무변경_회귀0(self):
        g = geometry_takeoff(width_m=20, depth_m=15, floors_above=10, floors_below=1)
        it = g["items"][0]
        # 기존 키(name/spec/unit/quantity/cost_won)가 그대로 보존됨(additive만 추가).
        assert set(["name", "spec", "unit", "quantity", "cost_won"]).issubset(it.keys())
