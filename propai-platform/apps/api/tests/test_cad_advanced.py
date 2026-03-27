"""CAD 자동 보정 확장 테스트 (Phase 15 강화).

check_setback_compliance, optimize_floor_height 메서드와 BuildingModel 신규 필드 테스트.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.cad_auto_correction_service import (
    BuildingModel,
    CadAutoCorrectionService,
)


# ── BuildingModel 신규 필드 테스트 ──


class TestBuildingModelNewFields:
    """BuildingModel의 신규 필드 기본값 테스트."""

    def test_default_setback_distances(self):
        """setback_distances 기본값은 None."""
        model = BuildingModel(
            site_area_sqm=500,
            building_area_sqm=300,
            num_floors=5,
            floor_height_m=3.0,
        )
        assert model.setback_distances is None

    def test_default_min_floor_height(self):
        """min_floor_height_m 기본값은 2.7."""
        model = BuildingModel(
            site_area_sqm=500,
            building_area_sqm=300,
            num_floors=5,
            floor_height_m=3.0,
        )
        assert model.min_floor_height_m == 2.7

    def test_custom_setback_distances(self):
        """setback_distances 커스텀 값."""
        model = BuildingModel(
            site_area_sqm=500,
            building_area_sqm=300,
            num_floors=5,
            floor_height_m=3.0,
            setback_distances={"north": 3.0, "south": 2.0},
        )
        assert model.setback_distances["north"] == 3.0


# ── check_setback_compliance 테스트 ──


class TestCheckSetbackCompliance:
    """세트백 준수 검증 테스트."""

    def test_all_compliant(self):
        """모든 면 준수."""
        model = BuildingModel(
            site_area_sqm=500,
            building_area_sqm=300,
            num_floors=5,
            floor_height_m=3.0,
            setback_distances={"north": 3.0, "south": 2.0, "east": 1.5, "west": 1.5},
        )
        results = CadAutoCorrectionService.check_setback_compliance(model, {}, 1.0)
        assert len(results) == 4
        assert all(r["compliant"] for r in results)

    def test_partial_violation(self):
        """일부 면 미달."""
        model = BuildingModel(
            site_area_sqm=500,
            building_area_sqm=300,
            num_floors=5,
            floor_height_m=3.0,
            setback_distances={"north": 0.5, "south": 2.0},
        )
        results = CadAutoCorrectionService.check_setback_compliance(model, {}, 1.0)
        assert len(results) == 2
        non_compliant = [r for r in results if not r["compliant"]]
        assert len(non_compliant) == 1
        assert non_compliant[0]["side"] == "north"

    def test_no_setback_data(self):
        """setback_distances가 None이면 빈 리스트."""
        model = BuildingModel(
            site_area_sqm=500,
            building_area_sqm=300,
            num_floors=5,
            floor_height_m=3.0,
        )
        results = CadAutoCorrectionService.check_setback_compliance(model, {}, 1.0)
        assert results == []


# ── optimize_floor_height 테스트 ──


class TestOptimizeFloorHeight:
    """층고 최적화 테스트."""

    def test_standard_case(self):
        """표준 높이 제한 (35m, 최소 층고 2.7m)."""
        model = BuildingModel(
            site_area_sqm=500,
            building_area_sqm=300,
            num_floors=10,
            floor_height_m=3.5,
        )
        result = CadAutoCorrectionService.optimize_floor_height(model, 35.0)
        assert result["max_floors"] >= 1
        assert result["total_height_m"] <= 35.0
        assert result["optimized_floor_height_m"] >= 2.7

    def test_low_height_limit(self):
        """매우 낮은 높이 제한 (5m)."""
        model = BuildingModel(
            site_area_sqm=500,
            building_area_sqm=300,
            num_floors=10,
            floor_height_m=3.0,
        )
        result = CadAutoCorrectionService.optimize_floor_height(model, 5.0)
        assert result["max_floors"] == 1
        assert result["total_height_m"] <= 5.0

    def test_exact_division(self):
        """높이 제한이 최소 층고의 정수배."""
        model = BuildingModel(
            site_area_sqm=500,
            building_area_sqm=300,
            num_floors=10,
            floor_height_m=3.0,
        )
        result = CadAutoCorrectionService.optimize_floor_height(model, 27.0)
        # 27.0 / 2.7 = 10
        assert result["max_floors"] == 10
        assert result["total_height_m"] == pytest.approx(27.0, abs=0.01)

    def test_zero_height(self):
        """높이 제한 0m → 층수 0."""
        model = BuildingModel(
            site_area_sqm=500,
            building_area_sqm=300,
            num_floors=1,
            floor_height_m=3.0,
        )
        result = CadAutoCorrectionService.optimize_floor_height(model, 0.0)
        assert result["max_floors"] == 0
        assert result["total_height_m"] == 0.0
