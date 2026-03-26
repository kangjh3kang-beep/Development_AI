"""ConstructionAIService 단위 테스트.

BIM4D 시공 일정, ZEB 에너지 시뮬레이션, 탄소 배출량 산정 등
순수 계산 로직을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.construction_ai_service import ConstructionAIService


class TestGenerateConstructionSchedule:
    """BIM4D 시공 일정 생성 테스트."""

    def _make_svc(self) -> ConstructionAIService:
        svc = object.__new__(ConstructionAIService)
        return svc

    def test_기본_일정_13공정_포함(self):
        svc = self._make_svc()
        result = svc.generate_construction_schedule(total_area_sqm=5000)
        assert len(result["schedule"]) == 13

    def test_총_소요일_양수(self):
        svc = self._make_svc()
        result = svc.generate_construction_schedule(total_area_sqm=5000)
        assert result["total_duration_days"] > 0

    def test_면적_증가시_일정_증가(self):
        svc = self._make_svc()
        small = svc.generate_construction_schedule(total_area_sqm=1000)
        large = svc.generate_construction_schedule(total_area_sqm=10000)
        assert large["total_duration_days"] > small["total_duration_days"]

    def test_크리티컬_패스_존재(self):
        svc = self._make_svc()
        result = svc.generate_construction_schedule(total_area_sqm=5000)
        assert len(result["critical_path"]) > 0

    def test_마일스톤_4개(self):
        """착공, 골조 완료, 설비/전기 완료, 준공."""
        svc = self._make_svc()
        result = svc.generate_construction_schedule(total_area_sqm=5000)
        assert len(result["milestones"]) == 4
        assert result["milestones"][0]["name"] == "착공"
        assert result["milestones"][-1]["name"] == "준공"

    def test_SRC_구조_RC보다_길어짐(self):
        """SRC(1.15배) > RC(1.0배) 보정 계수."""
        svc = self._make_svc()
        rc = svc.generate_construction_schedule(total_area_sqm=5000, structure_type="RC")
        src = svc.generate_construction_schedule(total_area_sqm=5000, structure_type="SRC")
        assert src["total_duration_days"] >= rc["total_duration_days"]

    def test_SC_구조_RC보다_짧아짐(self):
        """SC(0.85배) < RC(1.0배) 보정 계수."""
        svc = self._make_svc()
        rc = svc.generate_construction_schedule(total_area_sqm=5000, structure_type="RC")
        sc = svc.generate_construction_schedule(total_area_sqm=5000, structure_type="SC")
        assert sc["total_duration_days"] <= rc["total_duration_days"]

    def test_각_공정_최소_3일(self):
        svc = self._make_svc()
        result = svc.generate_construction_schedule(total_area_sqm=100)
        for phase in result["schedule"]:
            assert phase["duration_days"] >= 3


class TestEstimateZebEnergy:
    """ZEB 에너지 시뮬레이션 테스트."""

    def _make_svc(self) -> ConstructionAIService:
        svc = object.__new__(ConstructionAIService)
        return svc

    def test_기본_에너지_수요_양수(self):
        svc = self._make_svc()
        result = svc.estimate_zeb_energy(total_area_sqm=5000)
        assert result["annual_energy_demand_kwh"] > 0

    def test_재생에너지_발전량_양수(self):
        svc = self._make_svc()
        result = svc.estimate_zeb_energy(total_area_sqm=5000)
        assert result["annual_renewable_generation_kwh"] > 0

    def test_ZEB_등급_판정(self):
        svc = self._make_svc()
        result = svc.estimate_zeb_energy(total_area_sqm=5000)
        valid_grades = {"1등급", "2등급", "3등급", "4등급", "5등급", "미달"}
        assert result["zeb_grade"] in valid_grades

    def test_에너지_자립률_0_이상(self):
        svc = self._make_svc()
        result = svc.estimate_zeb_energy(total_area_sqm=5000)
        assert result["energy_independence_rate"] >= 0

    def test_1등급_단열_높은_자립률(self):
        svc = self._make_svc()
        g1 = svc.estimate_zeb_energy(total_area_sqm=1000, insulation_grade="1등급")
        g4 = svc.estimate_zeb_energy(total_area_sqm=1000, insulation_grade="4등급")
        assert g1["energy_independence_rate"] > g4["energy_independence_rate"]

    def test_권장사항_포함(self):
        svc = self._make_svc()
        result = svc.estimate_zeb_energy(total_area_sqm=5000)
        assert len(result["recommendations"]) > 0


class TestCalculateCarbonEmission:
    """탄소 배출량 산정 테스트."""

    def test_기본_배출량_계산(self):
        result = ConstructionAIService.calculate_carbon_emission(
            material={"concrete": 500, "steel": 100},
            equipment={"excavator": 200, "crane": 100},
            power={"electricity_kwh": 50000, "diesel_liter": 5000},
        )
        assert result["total_emission_tco2e"] > 0
        assert result["material_emission_tco2e"] > 0
        assert result["equipment_emission_tco2e"] > 0
        assert result["power_emission_tco2e"] > 0

    def test_자재_배출_계수_적용(self):
        """콘크리트 100톤 × 130 kgCO₂e/톤 = 13,000 kg = 13.0 tCO₂e."""
        result = ConstructionAIService.calculate_carbon_emission(
            material={"concrete": 100},
            equipment={},
            power={},
        )
        assert result["material_detail"]["concrete"] == pytest.approx(13.0, rel=0.01)

    def test_철강_배출_높은_계수(self):
        """철강 10톤 × 2300 = 23,000 kg = 23.0 tCO₂e."""
        result = ConstructionAIService.calculate_carbon_emission(
            material={"steel": 10},
            equipment={},
            power={},
        )
        assert result["material_detail"]["steel"] == pytest.approx(23.0, rel=0.01)

    def test_빈_입력_배출량_0(self):
        result = ConstructionAIService.calculate_carbon_emission(
            material={}, equipment={}, power={},
        )
        assert result["total_emission_tco2e"] == 0.0

    def test_총배출량_합산_정확(self):
        result = ConstructionAIService.calculate_carbon_emission(
            material={"concrete": 100},
            equipment={"crane": 50},
            power={"electricity_kwh": 10000},
        )
        total = (
            result["material_emission_tco2e"]
            + result["equipment_emission_tco2e"]
            + result["power_emission_tco2e"]
        )
        assert result["total_emission_tco2e"] == pytest.approx(total, rel=0.01)

    def test_감축_권장사항_포함(self):
        result = ConstructionAIService.calculate_carbon_emission(
            material={"concrete": 500, "steel": 200},
            equipment={"excavator": 500},
            power={"electricity_kwh": 100000},
        )
        assert len(result["recommendations"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
