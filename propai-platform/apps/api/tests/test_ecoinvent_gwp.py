"""Ecoinvent GWP DB, 탄소 등급, 저탄소 대안 추천 단위 테스트.

T3-1: ECOINVENT_GWP_DB 30종 자재 GWP 계수 및 탄소 등급 검증
T3-2: LOW_CARBON_ALTERNATIVES 저탄소 자재 자동 추천 검증
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.carbon_calculation_service import (
    CARBON_GRADE_THRESHOLDS,
    ECOINVENT_GWP_DB,
    LOW_CARBON_ALTERNATIVES,
    CarbonCalculationService,
)


# ──────────────────────────────────────────────
# T3-1: Ecoinvent GWP DB 검증
# ──────────────────────────────────────────────


class TestEcoinventGwpDB:
    """ECOINVENT_GWP_DB 상수의 구조와 값을 검증한다."""

    def test_ecoinvent_db_30종(self):
        """최소 30종의 건축자재가 등록되어 있어야 한다."""
        assert len(ECOINVENT_GWP_DB) >= 30

    def test_콘크리트_c30_gwp(self):
        """레미콘 C30의 GWP 계수는 0.130이다."""
        entry = ECOINVENT_GWP_DB["concrete_c30"]
        assert entry["gwp"] == pytest.approx(0.130)

    def test_목재_음수_gwp(self):
        """침엽수 목재는 탄소 흡수로 음수 GWP를 가진다."""
        entry = ECOINVENT_GWP_DB["timber_softwood"]
        assert entry["gwp"] < 0

    def test_모든_자재_필수_필드(self):
        """모든 자재 항목에 gwp, unit, category, name 필드가 존재해야 한다."""
        required_fields = {"gwp", "unit", "category", "name"}
        for key, entry in ECOINVENT_GWP_DB.items():
            for field in required_fields:
                assert field in entry, f"{key}에 {field} 필드 누락"


# ──────────────────────────────────────────────
# T3-1: 탄소 등급 검증
# ──────────────────────────────────────────────


class TestCarbonGrade:
    """탄소 등급 산출을 검증한다."""

    def test_탄소등급_A_plus(self):
        """intensity 200 kgCO2eq/m2 → A+ 등급."""
        result = CarbonCalculationService.grade_carbon(200_000, 1000)
        assert result["intensity_kgco2e_m2"] == pytest.approx(200.0)
        assert result["grade"] == "A+"

    def test_탄소등급_B(self):
        """intensity 600 kgCO2eq/m2 → B 등급."""
        result = CarbonCalculationService.grade_carbon(600_000, 1000)
        assert result["intensity_kgco2e_m2"] == pytest.approx(600.0)
        assert result["grade"] == "B"

    def test_탄소등급_D(self):
        """intensity 1500 kgCO2eq/m2 → D 등급."""
        result = CarbonCalculationService.grade_carbon(1_500_000, 1000)
        assert result["intensity_kgco2e_m2"] == pytest.approx(1500.0)
        assert result["grade"] == "D"

    def test_면적_0_등급_NA(self):
        """연면적이 0이면 N/A 등급."""
        result = CarbonCalculationService.grade_carbon(100_000, 0)
        assert result["grade"] == "N/A"

    def test_탄소등급_A(self):
        """intensity 400 kgCO2eq/m2 → A 등급."""
        result = CarbonCalculationService.grade_carbon(400_000, 1000)
        assert result["grade"] == "A"

    def test_탄소등급_C(self):
        """intensity 800 kgCO2eq/m2 → C 등급."""
        result = CarbonCalculationService.grade_carbon(800_000, 1000)
        assert result["grade"] == "C"


# ──────────────────────────────────────────────
# T3-1: GWP 조회 및 자재별 탄소 계산
# ──────────────────────────────────────────────


class TestLookupGwp:
    """GWP 조회 및 자재별 탄소 배출량 계산을 검증한다."""

    def test_lookup_gwp_존재(self):
        """steel_rebar 검색 성공."""
        result = CarbonCalculationService.lookup_gwp("steel_rebar")
        assert result is not None
        assert result["gwp"] == pytest.approx(1.800)

    def test_lookup_gwp_미존재(self):
        """존재하지 않는 자재는 None을 반환한다."""
        result = CarbonCalculationService.lookup_gwp("없는자재")
        assert result is None

    def test_calculate_material_carbon(self):
        """철근 1000kg x 1.8 gwp = 1800 kgCO2eq."""
        result = CarbonCalculationService.calculate_material_carbon("steel_rebar", 1000)
        assert result == pytest.approx(1800.0)

    def test_calculate_material_carbon_미존재(self):
        """존재하지 않는 자재는 0.0을 반환한다."""
        result = CarbonCalculationService.calculate_material_carbon("없는자재", 1000)
        assert result == 0.0


# ──────────────────────────────────────────────
# T3-2: 저탄소 자재 자동 추천
# ──────────────────────────────────────────────


class TestLowCarbonAlternatives:
    """저탄소 대안 추천을 검증한다."""

    def test_대안_매핑_존재(self):
        """최소 10개 이상의 대안 매핑이 존재해야 한다."""
        assert len(LOW_CARBON_ALTERNATIVES) >= 10

    def test_콘크리트_대안_저탄소(self):
        """concrete_c30의 대안은 concrete_low_carbon이다."""
        alts = LOW_CARBON_ALTERNATIVES["concrete_c30"]
        assert "concrete_low_carbon" in alts

    def test_대안_gwp_감소율(self):
        """추천된 대안의 GWP 감소율은 양수여야 한다."""
        recs = CarbonCalculationService.recommend_low_carbon_alternatives(["concrete_c30"])
        assert len(recs) > 0
        for rec in recs:
            assert rec["gwp_reduction_percent"] > 0

    def test_대안_없는_자재(self):
        """대안 매핑이 없는 자재는 추천이 비어 있다."""
        recs = CarbonCalculationService.recommend_low_carbon_alternatives(["timber_softwood"])
        assert len(recs) == 0

    def test_대안_정렬_감소율_내림차순(self):
        """추천 목록은 GWP 감소율 내림차순으로 정렬된다."""
        keys = list(LOW_CARBON_ALTERNATIVES.keys())
        recs = CarbonCalculationService.recommend_low_carbon_alternatives(keys)
        if len(recs) >= 2:
            for i in range(len(recs) - 1):
                assert recs[i]["gwp_reduction_percent"] >= recs[i + 1]["gwp_reduction_percent"]

    def test_대안_결과_필드(self):
        """추천 결과에 필수 필드가 포함되어야 한다."""
        recs = CarbonCalculationService.recommend_low_carbon_alternatives(["steel_rebar"])
        assert len(recs) > 0
        required_fields = {
            "original_material", "original_name", "original_gwp",
            "alternative_material", "alternative_name", "alternative_gwp",
            "gwp_reduction_percent",
        }
        for rec in recs:
            for field in required_fields:
                assert field in rec, f"필수 필드 {field} 누락"
