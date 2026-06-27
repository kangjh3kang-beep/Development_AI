"""EnvelopeResult 단일계약 + 어댑터(mass_to_envelope_result) 단위 테스트(INC2-a).

핵심 회귀잠금:
- ★podium-tower 매스 → canonical_floors=floors_for_units(podium 제외 주거층) 정합
- 미상 키 → None(가짜값 0 금지·무날조)
- 비-dict 입력 → 예외 없이 빈 결과
- geo_invariants status=FAIL → EnvelopeResult.status=FAIL 반영
- model_dump(mode="json") 직렬화 안전(GeoStatus enum이 문자열로)
- generate() 결과 compliance에 envelope_result 부착 + 기존 키 무변경(무회귀)
"""

from app.services.cad.auto_design_engine import AutoDesignEngineService, SiteInput
from app.services.cad.envelope_result import (
    EnvelopeResult,
    mass_to_envelope_result,
)
from app.services.cad.geometry_invariants import GeoStatus


def _podium_tower_mass() -> dict:
    """GC 2000㎡류 주상복합 podium-tower 매스(어댑터 변환 검증용 골든 입력)."""
    return {
        "building_width_m": 24.0,        # tower 폭(headline로 덮인 값)
        "building_depth_m": 18.0,
        "building_footprint_sqm": 432.0,  # tower 바닥판
        "num_floors": 40,                 # 전체 층수(podium+tower)
        "floor_height_m": 3.0,
        "building_height_m": 120.0,
        "total_floor_area_sqm": 20000.0,
        "bcr_pct": 58.0,
        "far_pct": 1000.0,
        "applied_max_bcr_pct": 60.0,
        "applied_max_far_pct": 1000.0,
        "massing_profile": "podium_tower",
        "podium": {"width_m": 40.0, "depth_m": 30.0, "floors": 4, "footprint_sqm": 1200.0},
        "tower": {"width_m": 24.0, "depth_m": 18.0, "floors": 36, "footprint_sqm": 432.0},
        "floors_for_units": 36,          # ★정본 주거층수(podium 4층 제외)
        "residential_gfa_sqm": 15552.0,
    }


class TestPodiumTowerMapping:
    """podium-tower 매스가 올바른 EnvelopeResult로 변환되는지(정본 층수·박스 매핑)."""

    def test_geometry_and_metrics_mapped(self):
        er = mass_to_envelope_result(_podium_tower_mass(), total_units=180)

        # 기하 매핑
        assert er.geometry.building_width_m == 24.0
        assert er.geometry.footprint_sqm == 432.0
        assert er.geometry.num_floors == 40
        assert er.geometry.massing_profile == "podium_tower"
        assert er.geometry.podium == {
            "width_m": 40.0, "depth_m": 30.0, "floors": 4, "footprint_sqm": 1200.0,
        }
        assert er.geometry.tower["floors"] == 36
        assert er.geometry.floors_for_units == 36
        assert er.geometry.residential_gfa_sqm == 15552.0

        # 핵심 수치 매핑
        assert er.metrics.bcr_pct == 58.0
        assert er.metrics.far_pct == 1000.0
        assert er.metrics.gfa_sqm == 20000.0
        assert er.metrics.total_units == 180
        assert er.metrics.applied_max_bcr_pct == 60.0
        assert er.metrics.applied_max_far_pct == 1000.0

    def test_canonical_floors_is_residential_not_total(self):
        # ★정본 층수는 podium 제외 주거층(floors_for_units=36)이지 전체 40층이 아니다.
        er = mass_to_envelope_result(_podium_tower_mass())
        assert er.metrics.canonical_floors == 36

    def test_canonical_floors_falls_back_to_num_floors(self):
        # floors_for_units가 없는 단일박스 매스는 num_floors가 정본 층수가 된다.
        mass = {"num_floors": 12, "building_width_m": 20.0}
        er = mass_to_envelope_result(mass)
        assert er.metrics.canonical_floors == 12


class TestNoFabrication:
    """무날조 — 미상 키는 None(가짜 0 금지)."""

    def test_missing_keys_are_none(self):
        # 거의 빈 매스 → 모든 미상 필드가 None(0이 아니라)
        er = mass_to_envelope_result({})
        assert er.geometry.building_width_m is None
        assert er.geometry.footprint_sqm is None
        assert er.geometry.num_floors is None
        assert er.geometry.podium is None
        assert er.geometry.tower is None
        assert er.metrics.bcr_pct is None
        assert er.metrics.gfa_sqm is None
        assert er.metrics.canonical_floors is None
        assert er.metrics.total_units is None

    def test_nan_and_garbage_absorbed_to_none(self):
        # NaN/문자열 쓰레기 → None(예외 없이 흡수)
        mass = {
            "building_width_m": float("nan"),
            "num_floors": "abc",
            "bcr_pct": float("inf"),
            "podium": "not-a-dict",
        }
        er = mass_to_envelope_result(mass)
        assert er.geometry.building_width_m is None
        assert er.geometry.num_floors is None
        assert er.metrics.bcr_pct is None
        assert er.geometry.podium is None


class TestNonDictInput:
    """비-dict 입력 → 예외 없이 빈 결과."""

    def test_none_input(self):
        er = mass_to_envelope_result(None)  # type: ignore[arg-type]
        assert isinstance(er, EnvelopeResult)
        assert er.geometry.building_width_m is None
        assert er.metrics.canonical_floors is None
        assert er.status is GeoStatus.PASS

    def test_list_input(self):
        er = mass_to_envelope_result([1, 2, 3])  # type: ignore[arg-type]
        assert isinstance(er, EnvelopeResult)
        assert er.metrics.gfa_sqm is None


class TestStatusFromInvariants:
    """status는 기하불변식 최악등급을 반영한다."""

    def test_fail_status_reflected(self):
        geo = {"status": "FAIL", "checks": [], "warnings": [], "errors": ["[INV-GEO-UNITS] 0세대"]}
        er = mass_to_envelope_result(_podium_tower_mass(), geo_invariants=geo)
        assert er.status is GeoStatus.FAIL
        assert er.geometry_invariants == geo

    def test_warnings_reflected(self):
        geo = {
            "status": "PASS_WITH_WARNINGS", "checks": [],
            "warnings": ["[INV-GEO-006] 면적 불일치"], "errors": [],
        }
        er = mass_to_envelope_result(_podium_tower_mass(), geo_invariants=geo)
        assert er.status is GeoStatus.PASS_WITH_WARNINGS
        assert er.warnings == ["[INV-GEO-006] 면적 불일치"]

    def test_no_invariants_defaults_pass(self):
        er = mass_to_envelope_result(_podium_tower_mass())
        assert er.status is GeoStatus.PASS
        assert er.geometry_invariants is None

    def test_unknown_status_defaults_pass(self):
        # 알 수 없는 status 문자열 → PASS(가짜 FAIL 금지)
        geo = {"status": "WEIRD", "checks": [], "warnings": [], "errors": []}
        er = mass_to_envelope_result(_podium_tower_mass(), geo_invariants=geo)
        assert er.status is GeoStatus.PASS


class TestJsonSerialization:
    """model_dump(mode='json') 직렬화 안전성."""

    def test_status_serializes_to_string(self):
        geo = {"status": "FAIL", "checks": [], "warnings": [], "errors": []}
        er = mass_to_envelope_result(_podium_tower_mass(), geo_invariants=geo)
        dumped = er.model_dump(mode="json")
        # GeoStatus enum이 문자열로 직렬화돼야 한다(JSON 안전).
        assert dumped["status"] == "FAIL"
        assert dumped["schema_version"] == "propai.envelope_result.v0.1"
        assert dumped["geometry"]["floors_for_units"] == 36
        assert dumped["metrics"]["canonical_floors"] == 36

    def test_evidence_injected(self):
        ev = [{"value": 1000.0, "basis": "용적률", "source": "조례", "confidence": 0.9}]
        er = mass_to_envelope_result(_podium_tower_mass(), evidence=ev)
        assert er.evidence == ev


class TestGenerateAdditiveAttachment:
    """generate() 결과 compliance에 envelope_result가 부착되고 기존 키는 불변(무회귀)."""

    def test_envelope_result_attached(self):
        engine = AutoDesignEngineService()
        result = engine.generate(SiteInput(site_area_sqm=2000, zone_code="GC", building_use="공동주택"))

        assert "envelope_result" in result.compliance
        er = result.compliance["envelope_result"]
        assert er["schema_version"] == "propai.envelope_result.v0.1"
        # status는 문자열로 직렬화돼 있어야 한다.
        assert er["status"] in {"PASS", "PASS_WITH_WARNINGS", "FAIL"}
        # 정본 층수가 metrics에 실린다(매스 floors_for_units 또는 num_floors).
        assert er["metrics"]["canonical_floors"] is not None

    def test_existing_compliance_keys_unchanged(self):
        # ★무회귀: 기존 compliance 키들이 그대로 존재해야 한다(새 키만 추가).
        engine = AutoDesignEngineService()
        result = engine.generate(SiteInput(site_area_sqm=500, zone_code="2R"))

        for key in (
            "bcr_ok", "far_ok", "height_ok", "setback_ok", "all_pass",
            "corrections_applied", "geometry_invariants", "geometry_invariant_blocked",
        ):
            assert key in result.compliance, f"기존 compliance 키 {key} 누락 — 무회귀 위반"

    def test_summary_payload_unchanged_shape(self):
        # summary/design_payload는 envelope_result 부착의 영향을 받지 않는다.
        engine = AutoDesignEngineService()
        result = engine.generate(SiteInput(site_area_sqm=800, zone_code="3R"))
        assert "total_units" in result.summary
        assert "num_floors" in result.summary
        assert isinstance(result.design_payload, dict)
