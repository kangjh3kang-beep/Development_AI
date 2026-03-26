"""EnergyService 단위 테스트.

에너지 등급 판정, KEPCO 기본 요율 상수를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.energy_service import (
    _DEFAULT_BASE_CHARGE_PER_KW,
    _DEFAULT_ENERGY_RATES_KRW,
    EnergyService,
)


class TestEnergyGrade:
    """energy_grade 정적 메서드 테스트."""

    def test_60이하_Aplus(self):
        assert EnergyService.energy_grade(60) == "A+"

    def test_30_Aplus(self):
        assert EnergyService.energy_grade(30) == "A+"

    def test_61_A(self):
        assert EnergyService.energy_grade(61) == "A"

    def test_90_A(self):
        assert EnergyService.energy_grade(90) == "A"

    def test_91_B(self):
        assert EnergyService.energy_grade(91) == "B"

    def test_130_B(self):
        assert EnergyService.energy_grade(130) == "B"

    def test_131_C(self):
        assert EnergyService.energy_grade(131) == "C"

    def test_170_C(self):
        assert EnergyService.energy_grade(170) == "C"

    def test_171_D(self):
        assert EnergyService.energy_grade(171) == "D"

    def test_300_D(self):
        assert EnergyService.energy_grade(300) == "D"

    def test_0_Aplus(self):
        assert EnergyService.energy_grade(0) == "A+"

    def test_경계값_연속성(self):
        """60→A+, 61→A, 90→A, 91→B 등 경계가 올바른지."""
        grades = [EnergyService.energy_grade(d) for d in [59, 60, 61, 89, 90, 91, 129, 130, 131, 169, 170, 171]]
        assert grades == ["A+", "A+", "A", "A", "A", "B", "B", "B", "C", "C", "C", "D"]


class TestDefaultEnergyRates:
    """KEPCO 기본 요율 상수 테스트."""

    def test_3개_계약유형(self):
        assert len(_DEFAULT_ENERGY_RATES_KRW) == 3

    def test_general_요율(self):
        assert _DEFAULT_ENERGY_RATES_KRW["general"] == 132.4

    def test_industrial_요율(self):
        assert _DEFAULT_ENERGY_RATES_KRW["industrial"] == 119.2

    def test_education_요율(self):
        assert _DEFAULT_ENERGY_RATES_KRW["education"] == 108.1

    def test_기본부하요금_존재(self):
        assert len(_DEFAULT_BASE_CHARGE_PER_KW) == 3
        assert _DEFAULT_BASE_CHARGE_PER_KW["general"] == 8320.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
