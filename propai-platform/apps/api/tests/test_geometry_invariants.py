"""기하 불변식 하드게이트(geometry_invariants) 단위 테스트.

핵심 회귀잠금:
- ★주거 매스인데 0세대 → FAIL (이번 세션의 0세대 버그 재발 차단)
- 면적 불보존(footprint≠width×depth) → PASS_WITH_WARNINGS(차단 아님)
- 건폐율/용적률 법정초과 → FAIL
- footprint > 부지면적 → FAIL
- floors_for_units > num_floors → FAIL
- 정상 podium-tower 매스 → FAIL 아님(PASS 또는 경고)
- 미상 키 → SKIP(가짜 PASS/FAIL 없음)
"""

from app.services.cad.geometry_invariants import (
    GeometryInvariantResult,
    GeoStatus,
    check_mass_invariants,
    check_polygon_invariants,
)


def _codes(result: GeometryInvariantResult) -> set[str]:
    return {c.code for c in result.checks}


def _status_of(result: GeometryInvariantResult, code: str) -> GeoStatus | None:
    for c in result.checks:
        if c.code == code:
            return c.status
    return None


class TestAreaConservation:
    """INV-GEO-006 면적 보존 — 불일치는 FAIL이 아니라 경고."""

    def test_violation_is_warning_not_fail(self):
        # footprint가 width×depth와 크게 어긋남 → 경고
        mass = {
            "building_width_m": 20.0,
            "building_depth_m": 20.0,  # 400㎡ 이어야 하는데
            "building_footprint_sqm": 600.0,  # 600㎡로 불일치
        }
        result = check_mass_invariants(mass)
        assert _status_of(result, "INV-GEO-006") is GeoStatus.PASS_WITH_WARNINGS
        assert result.status is not GeoStatus.FAIL  # 면적불일치만으로는 차단 안 함
        assert any("INV-GEO-006" in w for w in result.warnings)

    def test_consistent_area_passes(self):
        mass = {
            "building_width_m": 20.0,
            "building_depth_m": 20.0,
            "building_footprint_sqm": 400.0,
        }
        result = check_mass_invariants(mass)
        assert _status_of(result, "INV-GEO-006") is GeoStatus.PASS


class TestUnitsFeasibility:
    """INV-GEO-UNITS 0세대 차단 — ★핵심 회귀잠금."""

    def test_residential_zero_units_fails(self):
        mass = {
            "building_width_m": 22.0,
            "building_depth_m": 20.0,
            "building_footprint_sqm": 440.0,
            "num_floors": 38,
            "total_floor_area_sqm": 16720.0,
        }
        result = check_mass_invariants(
            mass, total_units=0, building_use="공동주택"
        )
        assert _status_of(result, "INV-GEO-UNITS") is GeoStatus.FAIL
        assert result.is_fail
        assert any("0세대" in e for e in result.errors)

    def test_residential_zero_units_but_feasible_false_not_fail(self):
        # ★엔진이 '성립 불가'를 정직 표기한 정상 0세대(작은 부지·순면적<최소평형)는 버그 아님 →
        #   FAIL이 아니라 PASS_WITH_WARNINGS. ENFORCE 승격 시 소형부지 대량 오탐 방지 회귀잠금.
        mass = {
            "building_width_m": 8.0,
            "building_depth_m": 8.0,
            "building_footprint_sqm": 64.0,
            "num_floors": 3,
            "total_floor_area_sqm": 192.0,
        }
        result = check_mass_invariants(
            mass, total_units=0, building_use="공동주택", units_feasible=False
        )
        assert _status_of(result, "INV-GEO-UNITS") is GeoStatus.PASS_WITH_WARNINGS
        assert not result.is_fail  # 정직한 성립불가는 차단 대상 아님

    def test_residential_with_units_passes(self):
        mass = {
            "building_width_m": 22.0,
            "building_depth_m": 20.0,
            "building_footprint_sqm": 440.0,
            "num_floors": 38,
            "total_floor_area_sqm": 16720.0,
        }
        result = check_mass_invariants(
            mass, total_units=304, building_use="공동주택"
        )
        assert _status_of(result, "INV-GEO-UNITS") is GeoStatus.PASS

    def test_non_residential_zero_units_skipped(self):
        # 비주거(상업)는 0세대(상가만)일 수 있으므로 세대 체크 SKIP
        mass = {
            "building_footprint_sqm": 440.0,
            "num_floors": 10,
            "total_floor_area_sqm": 4400.0,
        }
        result = check_mass_invariants(
            mass, total_units=0, building_use="일반업무"
        )
        assert "INV-GEO-UNITS" not in _codes(result)

    def test_units_unknown_skipped(self):
        # total_units 미상 → SKIP(가짜 FAIL 금지)
        mass = {
            "building_footprint_sqm": 440.0,
            "num_floors": 38,
            "total_floor_area_sqm": 16720.0,
        }
        result = check_mass_invariants(mass, building_use="공동주택")
        assert "INV-GEO-UNITS" not in _codes(result)


class TestLegalLimits:
    """INV-GEO-LEGAL 법정 한도 초과 → FAIL."""

    def test_bcr_over_limit_fails(self):
        mass = {"bcr_pct": 75.0, "applied_max_bcr_pct": 60.0}
        result = check_mass_invariants(mass)
        assert _status_of(result, "INV-GEO-LEGAL") is GeoStatus.FAIL

    def test_far_over_limit_fails(self):
        mass = {"far_pct": 350.0, "applied_max_far_pct": 200.0}
        result = check_mass_invariants(mass)
        assert _status_of(result, "INV-GEO-LEGAL") is GeoStatus.FAIL

    def test_within_limit_passes(self):
        mass = {
            "bcr_pct": 58.0,
            "applied_max_bcr_pct": 60.0,
            "far_pct": 195.0,
            "applied_max_far_pct": 200.0,
        }
        result = check_mass_invariants(mass)
        assert _status_of(result, "INV-GEO-LEGAL") is GeoStatus.PASS

    def test_limit_unknown_skipped(self):
        mass = {"bcr_pct": 75.0, "far_pct": 350.0}  # applied_max_* 미상
        result = check_mass_invariants(mass)
        assert "INV-GEO-LEGAL" not in _codes(result)

    def test_small_overage_within_tolerance_passes(self):
        # 2% 허용 오차 이내(반올림)는 통과
        mass = {"bcr_pct": 60.5, "applied_max_bcr_pct": 60.0}
        result = check_mass_invariants(mass)
        assert _status_of(result, "INV-GEO-LEGAL") is GeoStatus.PASS


class TestFootprintWithinSite:
    """INV-GEO-002 건축면적 ≤ 대지면적 → 초과면 FAIL."""

    def test_footprint_exceeds_site_fails(self):
        mass = {"building_footprint_sqm": 600.0}
        result = check_mass_invariants(mass, site_area_sqm=500.0)
        assert _status_of(result, "INV-GEO-002") is GeoStatus.FAIL

    def test_footprint_within_site_passes(self):
        mass = {"building_footprint_sqm": 300.0}
        result = check_mass_invariants(mass, site_area_sqm=500.0)
        assert _status_of(result, "INV-GEO-002") is GeoStatus.PASS

    def test_site_area_unknown_skipped(self):
        mass = {"building_footprint_sqm": 600.0}
        result = check_mass_invariants(mass)  # site_area_sqm 미전달
        assert "INV-GEO-002" not in _codes(result)


class TestFloors:
    """INV-GEO-FLOORS 층수 정합."""

    def test_floors_for_units_over_total_fails(self):
        mass = {"num_floors": 30, "floors_for_units": 35}  # 주거층 > 전체층
        result = check_mass_invariants(mass)
        assert _status_of(result, "INV-GEO-FLOORS") is GeoStatus.FAIL

    def test_zero_floors_fails(self):
        mass = {"num_floors": 0}
        result = check_mass_invariants(mass)
        assert _status_of(result, "INV-GEO-FLOORS") is GeoStatus.FAIL

    def test_valid_floors_pass(self):
        mass = {"num_floors": 38, "floors_for_units": 35}
        result = check_mass_invariants(mass)
        assert _status_of(result, "INV-GEO-FLOORS") is GeoStatus.PASS

    def test_floors_unknown_skipped(self):
        result = check_mass_invariants({"building_footprint_sqm": 300.0})
        assert "INV-GEO-FLOORS" not in _codes(result)


class TestPodiumTower:
    """정상 podium-tower 매스(GC 2000㎡류) → FAIL 아님."""

    def test_normal_podium_tower_not_fail(self):
        # 이번 세션 GC 2000㎡ 일반상업(far 1000%) 정상 podium-tower 형태
        site_area = 2000.0
        podium_fp = 1200.0  # bcr 60%
        tower_fp = 440.0  # tower bcr 22%
        podium_floors = 3
        tower_floors = 35
        total_gfa = podium_fp * podium_floors + tower_fp * tower_floors
        mass = {
            "massing_profile": "podium_tower",
            "building_width_m": 22.0,
            "building_depth_m": 20.0,
            "building_footprint_sqm": tower_fp,
            "num_floors": podium_floors + tower_floors,
            "floors_for_units": tower_floors,
            "floor_height_m": 3.0,
            "total_floor_area_sqm": round(total_gfa, 2),
            "bcr_pct": round(podium_fp / site_area * 100, 2),
            "far_pct": round(total_gfa / site_area * 100, 2),
            "applied_max_bcr_pct": 60.0,
            "applied_max_far_pct": 1000.0,
            "podium": {
                "footprint_sqm": podium_fp, "floors": podium_floors,
                "width_m": 34.6, "depth_m": 34.7,
            },
            "tower": {
                "footprint_sqm": tower_fp, "floors": tower_floors,
                "width_m": 22.0, "depth_m": 20.0,
            },
        }
        result = check_mass_invariants(
            mass, site_area_sqm=site_area, total_units=560, building_use="주상복합"
        )
        assert not result.is_fail
        assert _status_of(result, "INV-GEO-UNITS") is GeoStatus.PASS
        assert _status_of(result, "INV-GEO-FLOORS") is GeoStatus.PASS
        assert _status_of(result, "INV-GEO-LEGAL") is GeoStatus.PASS


class TestPolygonInvariants:
    """INV-GEO-001 폴리곤 유효성 + DesignGeometry 진입점."""

    def test_valid_square_passes(self):
        coords = [(0, 0), (10, 0), (10, 10), (0, 10)]
        result = check_polygon_invariants(coords)
        assert not result.is_fail

    def test_self_intersecting_bowtie_fails(self):
        # 나비넥타이(bowtie) — 자기교차 무효 폴리곤
        coords = [(0, 0), (10, 10), (10, 0), (0, 10)]
        result = check_polygon_invariants(coords)
        assert result.is_fail

    def test_too_few_points_skipped(self):
        result = check_polygon_invariants([(0, 0), (1, 1)])
        assert len(result.checks) == 0  # SKIP(가짜 FAIL 없음)
        assert result.status is GeoStatus.PASS

    def test_dict_coords_accepted(self):
        coords = [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}, {"x": 0, "y": 10}]
        result = check_polygon_invariants(coords)
        assert not result.is_fail


class TestResultAggregation:
    """결과 묶음 최악 등급·to_dict 직렬화."""

    def test_worst_status_is_fail_when_any_fail(self):
        mass = {
            "building_width_m": 20.0,
            "building_depth_m": 20.0,
            "building_footprint_sqm": 600.0,  # 면적 불일치 → 경고
            "bcr_pct": 75.0,
            "applied_max_bcr_pct": 60.0,  # 법정초과 → FAIL
        }
        result = check_mass_invariants(mass)
        assert result.status is GeoStatus.FAIL  # 최악(FAIL)이 전체 등급

    def test_to_dict_shape(self):
        mass = {"num_floors": 38, "floors_for_units": 35}
        d = check_mass_invariants(mass).to_dict()
        assert set(d.keys()) == {"status", "checks", "warnings", "errors"}
        assert isinstance(d["checks"], list)
        assert d["checks"][0]["code"].startswith("INV-GEO")

    def test_non_dict_mass_returns_empty_pass(self):
        result = check_mass_invariants(None)  # type: ignore[arg-type]
        assert result.status is GeoStatus.PASS
        assert len(result.checks) == 0


class TestEngineIntegrationShadow:
    """auto_design_engine 배선(shadow) — generate 결과에 geometry_invariants 부착·무회귀."""

    def test_generate_attaches_invariants_and_does_not_block(self):
        from app.services.cad.auto_design_engine import AutoDesignEngineService, SiteInput

        engine = AutoDesignEngineService()
        site = SiteInput(
            site_area_sqm=500,
            zone_code="2R",
            building_use="공동주택",
            target_unit_types=["84A"],
        )
        result = engine.generate(site)
        # additive 부착 확인
        assert "geometry_invariants" in result.compliance
        gi = result.compliance["geometry_invariants"]
        assert gi is not None
        assert "status" in gi and "checks" in gi
        # ★shadow 기본 — 차단 안 함
        assert result.compliance["geometry_invariant_blocked"] is False
