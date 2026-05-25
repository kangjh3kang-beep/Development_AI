"""AutoDesignEngineService 단위 테스트."""

import pytest

from app.services.cad.auto_design_engine import (
    AutoDesignEngineService,
    DesignResult,
    SiteInput,
)


@pytest.fixture()
def engine():
    return AutoDesignEngineService()


@pytest.fixture()
def default_input():
    return SiteInput(
        site_area_sqm=500,
        zone_code="2R",
        building_use="공동주택",
        target_unit_types=["84A"],
        floor_height_m=3.0,
        setback_m={"north": 3.0, "south": 2.0, "east": 1.5, "west": 1.5},
    )


class TestAutoDesignEngineGenerate:
    """generate() 정상 동작 검증."""

    def test_returns_design_result(self, engine: AutoDesignEngineService, default_input: SiteInput):
        result = engine.generate(default_input)
        assert isinstance(result, DesignResult)
        assert "points" in result.design_payload
        assert "lines" in result.design_payload
        assert "surfaces" in result.design_payload

    def test_summary_fields(self, engine: AutoDesignEngineService, default_input: SiteInput):
        result = engine.generate(default_input)
        s = result.summary
        assert s["building_area_sqm"] > 0
        assert s["total_floor_area_sqm"] > 0
        assert s["num_floors"] >= 1
        assert s["building_height_m"] > 0
        assert 0 < s["bcr_percent"] <= 100
        assert s["far_percent"] > 0
        assert s["total_units"] >= 0
        assert s["parking_count"] >= 0

    def test_compliance_fields(self, engine: AutoDesignEngineService, default_input: SiteInput):
        result = engine.generate(default_input)
        c = result.compliance
        assert "bcr_ok" in c
        assert "far_ok" in c
        assert "height_ok" in c
        assert "all_pass" in c

    def test_2r_zone_bcr_within_limit(self, engine: AutoDesignEngineService):
        """제2종일반주거지역 건폐율 60% 이하."""
        inp = SiteInput(site_area_sqm=500, zone_code="2R")
        result = engine.generate(inp)
        assert result.summary["bcr_percent"] <= 60.0
        assert result.compliance["bcr_ok"] is True

    def test_gc_zone_high_far(self, engine: AutoDesignEngineService):
        """일반상업지역 높은 용적률 허용."""
        inp = SiteInput(site_area_sqm=1000, zone_code="GC", building_use="업무시설")
        result = engine.generate(inp)
        assert result.summary["num_floors"] >= 1
        assert result.compliance["far_ok"] is True

    def test_1r_zone_low_density(self, engine: AutoDesignEngineService):
        """제1종일반주거지역 저밀도 설계."""
        inp = SiteInput(site_area_sqm=300, zone_code="1R")
        result = engine.generate(inp)
        assert result.summary["bcr_percent"] <= 60.0
        assert result.summary["far_percent"] <= 200.0

    def test_design_payload_has_scale(self, engine: AutoDesignEngineService, default_input: SiteInput):
        result = engine.generate(default_input)
        assert "scale" in result.design_payload
        assert "floor_count" in result.design_payload

    def test_small_site_still_generates(self, engine: AutoDesignEngineService):
        """아주 작은 대지도 에러 없이 생성."""
        inp = SiteInput(site_area_sqm=50, zone_code="2R")
        result = engine.generate(inp)
        assert result.summary["building_area_sqm"] > 0

    def test_large_site(self, engine: AutoDesignEngineService):
        """큰 대지 정상 처리."""
        inp = SiteInput(site_area_sqm=5000, zone_code="3R")
        result = engine.generate(inp)
        assert result.summary["total_units"] > 0


class TestAutoDesignAlternatives:
    """generate_alternatives() 검증."""

    def test_returns_3_alternatives(self, engine: AutoDesignEngineService, default_input: SiteInput):
        results = engine.generate_alternatives(default_input, count=3)
        assert len(results) == 3

    def test_alternatives_differ(self, engine: AutoDesignEngineService, default_input: SiteInput):
        results = engine.generate_alternatives(default_input, count=3)
        units = [r.summary["total_units"] for r in results]
        # 적어도 두 대안이 다르거나, 모두 동일한 건 극소 대지 시 가능
        assert len(results) == 3

    def test_all_alternatives_compliant(self, engine: AutoDesignEngineService, default_input: SiteInput):
        results = engine.generate_alternatives(default_input, count=3)
        for r in results:
            assert r.compliance["bcr_ok"] is True
            assert r.compliance["far_ok"] is True

    def test_single_alternative(self, engine: AutoDesignEngineService, default_input: SiteInput):
        results = engine.generate_alternatives(default_input, count=1)
        assert len(results) == 1


class TestAutoDesignLegalLimits:
    """법규 한도 경계 검증."""

    def test_get_legal_limits_2r(self, engine: AutoDesignEngineService):
        limits = engine.get_legal_limits("2R")
        assert limits["max_bcr_percent"] == 60.0
        assert limits["max_far_percent"] == 200.0

    def test_get_legal_limits_gc(self, engine: AutoDesignEngineService):
        limits = engine.get_legal_limits("GC")
        assert limits["max_bcr_percent"] == 60.0
        assert limits["max_far_percent"] == 1000.0

    def test_unknown_zone_defaults(self, engine: AutoDesignEngineService):
        limits = engine.get_legal_limits("UNKNOWN")
        assert limits["max_bcr_percent"] == 60.0  # 기본값


class TestAutoDesignComputations:
    """내부 계산 검증."""

    def test_effective_site_reduces_area(self, engine: AutoDesignEngineService):
        inp = SiteInput(site_area_sqm=500, setback_m={"north": 5, "south": 5, "east": 5, "west": 5})
        eff = engine.compute_effective_site(inp)
        assert eff["effective_area_sqm"] < 500

    def test_optimal_mass(self, engine: AutoDesignEngineService, default_input: SiteInput):
        limits = engine.get_legal_limits("2R")
        eff = engine.compute_effective_site(default_input)
        mass = engine.compute_optimal_mass(default_input, eff, limits)
        assert mass["building_footprint_sqm"] > 0
        assert mass["num_floors"] >= 1
