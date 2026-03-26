"""AssetIntelligenceService 단위 테스트.

자산 등급 판정, CAPEX 최적화 플랜 등 정적 메서드를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.asset_intelligence_service import AssetIntelligenceService


class TestGrade:
    """_grade 정적 메서드 테스트."""

    def test_85이상_A(self):
        assert AssetIntelligenceService._grade(85) == "A"

    def test_90_A(self):
        assert AssetIntelligenceService._grade(90) == "A"

    def test_72_B(self):
        assert AssetIntelligenceService._grade(72) == "B"

    def test_84_B(self):
        assert AssetIntelligenceService._grade(84) == "B"

    def test_60_C(self):
        assert AssetIntelligenceService._grade(60) == "C"

    def test_71_C(self):
        assert AssetIntelligenceService._grade(71) == "C"

    def test_45_D(self):
        assert AssetIntelligenceService._grade(45) == "D"

    def test_59_D(self):
        assert AssetIntelligenceService._grade(59) == "D"

    def test_44_E(self):
        assert AssetIntelligenceService._grade(44) == "E"

    def test_0_E(self):
        assert AssetIntelligenceService._grade(0) == "E"


class TestCapexPlan:
    """_capex_plan 정적 메서드 테스트."""

    def test_모두_양호_기본_전략(self):
        """모든 점수 ≥ 70 → 기본 reserve optimization."""
        plan = AssetIntelligenceService._capex_plan({
            "maintenance": 80,
            "tenant": 75,
            "market": 85,
            "climate": 78,
        })
        assert len(plan) == 1
        assert "Deferred capex" in plan[0]["strategy"]

    def test_유지보수_낮으면_HVAC_전략(self):
        plan = AssetIntelligenceService._capex_plan({
            "maintenance": 50,
            "tenant": 80,
            "market": 80,
            "climate": 80,
        })
        strategies = [item["strategy"] for item in plan]
        assert any("HVAC" in s for s in strategies)

    def test_테넌트_낮으면_서비스_전략(self):
        plan = AssetIntelligenceService._capex_plan({
            "maintenance": 80,
            "tenant": 60,
            "market": 80,
            "climate": 80,
        })
        strategies = [item["strategy"] for item in plan]
        assert any("Tenant" in s for s in strategies)

    def test_기후_낮으면_복원력_전략(self):
        plan = AssetIntelligenceService._capex_plan({
            "maintenance": 80,
            "tenant": 80,
            "market": 80,
            "climate": 50,
        })
        strategies = [item["strategy"] for item in plan]
        assert any("resilience" in s.lower() for s in strategies)

    def test_모두_낮으면_3개_전략(self):
        plan = AssetIntelligenceService._capex_plan({
            "maintenance": 50,
            "tenant": 50,
            "market": 80,
            "climate": 50,
        })
        assert len(plan) == 3

    def test_각_전략_ROI_포함(self):
        plan = AssetIntelligenceService._capex_plan({
            "maintenance": 50,
            "tenant": 50,
            "market": 80,
            "climate": 50,
        })
        for item in plan:
            assert "expected_roi" in item
            assert "payback_months" in item
            assert item["expected_roi"] > 0
            assert item["payback_months"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
