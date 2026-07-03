"""건축 법규 검증 확장 테스트 (Phase 7 강화).

세트백, 일조권, 용도지역별 법규 조회, 복합 위반 검증.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.building_compliance_service import (
    ZONE_LIMITS,
    BuildingComplianceService,
    DesignData,
    DesignPoint,
    DesignSurface,
    LegalLimits,
    LegalRegulationVerifier,
    _calculate_north_setback,
)

# ── 세트백 검증 테스트 ──


class TestSetbackVerification:
    """세트백 이격거리 검증 테스트."""

    def _make_design(self, setback_distances=None, north_setback_m=0.0):
        return DesignData(
            points=[],
            lines=[],
            surfaces=[],
            floor_count=1,
            building_height_m=10.0,
            scale=10.0,
            setback_distances=setback_distances,
            north_setback_m=north_setback_m,
        )

    def test_setback_pass(self):
        """모든 면의 세트백이 최소값 이상이면 위반 없음."""
        design = self._make_design(setback_distances={"north": 2.0, "south": 1.5, "east": 1.0, "west": 1.0})
        limits = LegalLimits(0.60, 2.50, 35.0, 1.0, 2.0)
        verifier = LegalRegulationVerifier()
        violations = verifier.verify(design, 500.0, limits)
        setback_v = [v for v in violations if v.type == "setback"]
        assert len(setback_v) == 0

    def test_setback_fail(self):
        """세트백 미달 시 위반 감지."""
        design = self._make_design(setback_distances={"north": 0.5, "south": 0.3})
        limits = LegalLimits(0.60, 2.50, 35.0, 1.0, 2.0)
        verifier = LegalRegulationVerifier()
        violations = verifier.verify(design, 500.0, limits)
        setback_v = [v for v in violations if v.type == "setback"]
        assert len(setback_v) == 2
        assert all(v.severity == "error" for v in setback_v)

    def test_setback_none(self):
        """setback_distances가 None이면 검증 건너뜀."""
        design = self._make_design(setback_distances=None)
        limits = LegalLimits(0.60, 2.50, 35.0, 1.0, 2.0)
        verifier = LegalRegulationVerifier()
        violations = verifier.verify(design, 500.0, limits)
        setback_v = [v for v in violations if v.type == "setback"]
        assert len(setback_v) == 0

    def test_setback_partial_fail(self):
        """일부 면만 미달."""
        design = self._make_design(setback_distances={"north": 2.0, "south": 0.5})
        limits = LegalLimits(0.60, 2.50, 35.0, 1.0, 2.0)
        verifier = LegalRegulationVerifier()
        violations = verifier.verify(design, 500.0, limits)
        setback_v = [v for v in violations if v.type == "setback"]
        assert len(setback_v) == 1
        assert setback_v[0].current_value == 0.5


# ── 일조권 검증 테스트 ──


class TestSunlightVerification:
    """정북방향 일조권 이격거리 테스트."""

    def test_north_setback_10m_below(self):
        """10m 이하 건물: 1.5m 이상(시행령 86조 2023.9.12 개정 현행)."""
        # 8m 건물 → 법정 1.5m (구버전 4.0m은 저층 과대이격 결함)
        assert _calculate_north_setback(8.0) == 1.5

    def test_north_setback_10m_exact(self):
        """10m 건물(임계): 1.5m."""
        assert _calculate_north_setback(10.0) == 1.5

    def test_north_setback_above_10m(self):
        """10m 초과 건물: 높이의 1/2."""
        # 15m 건물 → 15/2 = 7.5
        assert _calculate_north_setback(15.0) == 7.5

    def test_north_setback_very_low(self):
        """매우 낮은 건물도 법정 하한 1.5m."""
        assert _calculate_north_setback(1.0) == 1.5

    def test_sunlight_violation(self):
        """정북방향 이격거리 미달 시 위반 감지."""
        design = DesignData(
            points=[], lines=[], surfaces=[],
            building_height_m=15.0,
            north_setback_m=3.0,  # 필요: 7.5m
        )
        limits = LegalLimits(0.60, 2.50, 35.0, 1.0, 2.0)
        verifier = LegalRegulationVerifier()
        violations = verifier.verify(design, 500.0, limits)
        sunlight_v = [v for v in violations if v.type == "sunlight"]
        assert len(sunlight_v) == 1
        assert sunlight_v[0].current_value == 3.0
        assert sunlight_v[0].limit_value == pytest.approx(7.5)

    def test_sunlight_pass(self):
        """이격거리 충분하면 위반 없음."""
        design = DesignData(
            points=[], lines=[], surfaces=[],
            building_height_m=8.0,
            north_setback_m=5.0,  # 필요: 1.5m (10m 이하)
        )
        limits = LegalLimits(0.60, 2.50, 35.0, 1.0, 2.0)
        verifier = LegalRegulationVerifier()
        violations = verifier.verify(design, 500.0, limits)
        sunlight_v = [v for v in violations if v.type == "sunlight"]
        assert len(sunlight_v) == 0


# ── 용도지역별 법규 조회 테스트 ──


class TestZoneLimits:
    """용도지역별 법규 기본값 조회 테스트."""

    def test_zone_1R(self):
        """제1종일반주거."""
        lim = ZONE_LIMITS["1R"]
        assert lim.building_coverage_ratio == 0.60
        assert lim.max_height_m == 12.0

    def test_zone_2R(self):
        """제2종일반주거."""
        lim = ZONE_LIMITS["2R"]
        assert lim.floor_area_ratio == 2.00

    def test_zone_3R(self):
        """제3종일반주거."""
        lim = ZONE_LIMITS["3R"]
        assert lim.building_coverage_ratio == 0.50
        assert lim.min_setback_m == 1.5

    def test_zone_GC(self):
        """일반상업."""
        lim = ZONE_LIMITS["GC"]
        assert lim.floor_area_ratio == 4.00
        assert lim.min_setback_m == 0.0

    def test_zone_NC(self):
        """근린상업."""
        lim = ZONE_LIMITS["NC"]
        assert lim.floor_area_ratio == 9.00

    def test_zone_QI(self):
        """준공업."""
        lim = ZONE_LIMITS["QI"]
        assert lim.max_height_m == 35.0

    def test_zone_QR(self):
        """준주거."""
        lim = ZONE_LIMITS["QR"]
        assert lim.floor_area_ratio == 5.00

    def test_get_zone_limits_method(self):
        """BuildingComplianceService.get_zone_limits 메서드."""
        lim = BuildingComplianceService.get_zone_limits("GC")
        assert lim is not None
        assert lim.max_height_m == 50.0

    def test_get_zone_limits_unknown(self):
        """미등록 코드는 None."""
        lim = BuildingComplianceService.get_zone_limits("XX")
        assert lim is None


# ── 복합 위반 테스트 ──


class TestCompoundViolations:
    """세트백 + 일조권 + 건폐율 복합 위반 테스트."""

    def test_multiple_violations(self):
        """세트백 + 일조권 + 높이 동시 위반."""
        pts = [
            DesignPoint("p1", 0, 0),
            DesignPoint("p2", 300, 0),
            DesignPoint("p3", 300, 300),
            DesignPoint("p4", 0, 300),
        ]
        surf = DesignSurface("s1", ["p1", "p2", "p3", "p4"])
        design = DesignData(
            points=pts,
            lines=[],
            surfaces=[surf],
            floor_count=5,
            building_height_m=40.0,  # 높이 초과 (제한 35m)
            scale=10.0,
            setback_distances={"north": 0.3},  # 세트백 미달
            north_setback_m=2.0,  # 일조권 미달 (40m → (40-9)*0.5+4.5=20.0 필요)
        )
        limits = LegalLimits(0.60, 2.50, 35.0, 1.0, 2.0)
        verifier = LegalRegulationVerifier()
        violations = verifier.verify(design, 500.0, limits)

        types = {v.type for v in violations}
        assert "height" in types
        assert "setback" in types
        assert "sunlight" in types
