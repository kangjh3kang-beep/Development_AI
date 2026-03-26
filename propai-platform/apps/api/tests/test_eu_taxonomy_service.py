"""EuTaxonomyChecker 단위 테스트.

EU Taxonomy 기술 심사 기준(TSC), DNSH, MSS 검증 로직을 테스트한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.eu_taxonomy_service import (
    NZEB_BASELINE_KWH_M2,
    TSC_GREEN_RATIO_THRESHOLD,
    TSC_PED_THRESHOLD,
    TSC_RE_THRESHOLD,
    TSC_WASTE_RECYCLING_THRESHOLD,
    TSC_WATER_USAGE_THRESHOLD,
    BuildingData,
    EuTaxonomyChecker,
)


def _make_building(**overrides) -> BuildingData:
    """모든 기준을 통과하는 기본 건축물 데이터 생성 헬퍼."""
    defaults = {
        "primary_energy_demand_kwh_m2": 100.0,  # TSC_PED_THRESHOLD=108 이하
        "renewable_energy_ratio": 0.25,  # 20% 이상
        "embodied_carbon_kgco2e_m2": 350.0,  # 0보다 큼 (공개)
        "water_usage_liters_per_day": 400.0,  # 500 이하
        "waste_recycling_rate": 0.80,  # 70% 이상
        "green_ratio": 0.35,  # 30% 이상
        "has_climate_risk_assessment": True,
        "has_social_safeguards": True,
        "gross_floor_area_sqm": 10_000.0,
    }
    defaults.update(overrides)
    return BuildingData(**defaults)


class TestAlignment:
    """적합성 판정 테스트."""

    def test_전체_pass_Aligned(self):
        """모든 기준 충족 시 'Aligned' 판정."""
        building = _make_building()
        result = EuTaxonomyChecker.check(building)
        assert result.alignment == "Aligned"
        assert result.passed_count == result.total_count

    def test_ped_fail_Partially(self):
        """PED만 초과 시 'Partially Aligned' (다른 TSC는 통과)."""
        building = _make_building(primary_energy_demand_kwh_m2=150.0)
        result = EuTaxonomyChecker.check(building)
        assert result.alignment == "Partially Aligned"

    def test_전체_fail_Not_Aligned(self):
        """모든 TSC 실패 시 'Not Aligned'."""
        building = _make_building(
            primary_energy_demand_kwh_m2=200.0,
            renewable_energy_ratio=0.05,
            embodied_carbon_kgco2e_m2=0.0,
        )
        result = EuTaxonomyChecker.check(building)
        assert result.alignment == "Not Aligned"


class TestTSC:
    """기술 심사 기준(TSC) 개별 테스트."""

    def test_re_미달_fail(self):
        """재생에너지 비율 20% 미만 → 해당 기준 실패."""
        building = _make_building(renewable_energy_ratio=0.15)
        result = EuTaxonomyChecker.check(building)
        re_criterion = next(c for c in result.criteria if "재생에너지" in c.name)
        assert not re_criterion.passed

    def test_nzeb_기준_108(self):
        """TSC_PED_THRESHOLD = 120 * 0.9 = 108."""
        assert TSC_PED_THRESHOLD == NZEB_BASELINE_KWH_M2 * 0.90
        assert TSC_PED_THRESHOLD == 108.0


class TestDNSH:
    """DNSH (Do No Significant Harm) 테스트."""

    def test_waste_70_경계값(self):
        """정확히 0.70 재활용률 → 통과."""
        building = _make_building(waste_recycling_rate=0.70)
        result = EuTaxonomyChecker.check(building)
        waste_criterion = next(c for c in result.criteria if "폐기물" in c.name)
        assert waste_criterion.passed

    def test_dnsh_위반_Not_Aligned(self):
        """기후변화 적응(DNSH) 미충족 → 'Aligned'가 아님."""
        building = _make_building(has_climate_risk_assessment=False)
        result = EuTaxonomyChecker.check(building)
        # TSC 전체 통과, DNSH 미통과 → Partially Aligned
        assert result.alignment != "Aligned"


class TestMSS:
    """최소 사회적 안전장치(MSS) 테스트."""

    def test_mss_위반(self):
        """사회적 안전장치 미충족 → 'Aligned'가 아님."""
        building = _make_building(has_social_safeguards=False)
        result = EuTaxonomyChecker.check(building)
        mss_criterion = next(c for c in result.criteria if "MSS" in c.name)
        assert not mss_criterion.passed
        assert result.alignment != "Aligned"


class TestRecommendations:
    """권고사항 생성 테스트."""

    def test_recommendations_생성(self):
        """실패한 항목 수만큼 권고사항이 생성된다."""
        building = _make_building(
            primary_energy_demand_kwh_m2=150.0,
            renewable_energy_ratio=0.10,
            has_climate_risk_assessment=False,
        )
        result = EuTaxonomyChecker.check(building)
        failed_count = sum(1 for c in result.criteria if not c.passed)
        assert len(result.recommendations) == failed_count
        assert len(result.recommendations) > 0


class TestCounts:
    """통과/전체 카운트 테스트."""

    def test_passed_count_total_count(self):
        """passed_count + failed_count == total_count."""
        building = _make_building(
            primary_energy_demand_kwh_m2=150.0,
            renewable_energy_ratio=0.10,
        )
        result = EuTaxonomyChecker.check(building)
        failed_count = result.total_count - result.passed_count
        assert result.passed_count + failed_count == result.total_count
        assert result.total_count == 8  # 8개 기준
        # PED, RE 실패 → passed_count == 6
        assert result.passed_count == 6


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
