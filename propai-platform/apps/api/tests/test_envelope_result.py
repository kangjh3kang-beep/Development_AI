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
from app.services.cad.provenance import (
    ENGINE_SOURCE_VERSION,
    canonical_json,
    compute_geometry_hash,
    compute_input_hash,
    make_run_id,
)


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

        # 기하 매핑(키 오타 회귀 방지 — depth/층고/높이까지 명시 잠금)
        assert er.geometry.building_width_m == 24.0
        assert er.geometry.building_depth_m == 18.0
        assert er.geometry.floor_height_m == 3.0
        assert er.geometry.building_height_m == 120.0
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

    def test_adapter_does_not_mutate_input(self):
        # ★핵심 무회귀 계약: 어댑터는 순수 읽기 — 입력 mass를 절대 변경하지 않는다.
        #   향후 어댑터가 mass에 쓰기를 추가하면 이 테스트가 잡는다(소비처 회귀 토양 차단).
        import copy

        mass = _podium_tower_mass()
        before = copy.deepcopy(mass)
        mass_to_envelope_result(mass, total_units=180)
        assert mass == before


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


class TestProvenanceHelpers:
    """순수 provenance 헬퍼(canonical_json·해시·run_id)의 결정론·형식 잠금(INC3)."""

    def test_canonical_json_key_order_invariant(self):
        # ★canonical: 키 순서가 달라도 같은 내용이면 완전히 같은 문자열(해시 안정성의 핵심).
        a = {"zone_code": "2R", "site_area_sqm": 1000.0}
        b = {"site_area_sqm": 1000.0, "zone_code": "2R"}
        assert canonical_json(a) == canonical_json(b)
        # 공백이 제거된 한 줄 JSON(구분자 ',' ':'·한글 그대로)
        assert ", " not in canonical_json({"건물": "동", "수": 2})
        assert "동" in canonical_json({"건물": "동"})  # ensure_ascii=False

    def test_input_hash_deterministic_and_key_order_invariant(self):
        # 같은 핑거프린트(키 순서만 다름) → 같은 input_hash(결정론·canonical)
        fp1 = {"site_area_sqm": 2000.0, "zone_code": "GC", "building_use": "공동주택"}
        fp2 = {"building_use": "공동주택", "zone_code": "GC", "site_area_sqm": 2000.0}
        assert compute_input_hash(fp1) == compute_input_hash(fp2)
        # sha256 16진수 64자
        h = compute_input_hash(fp1)
        assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)

    def test_input_hash_differs_for_different_fingerprint(self):
        # 다른 핑거프린트 → 다른 input_hash(출처 구분)
        fp1 = {"site_area_sqm": 2000.0, "zone_code": "GC"}
        fp2 = {"site_area_sqm": 2000.0, "zone_code": "2R"}
        assert compute_input_hash(fp1) != compute_input_hash(fp2)

    def test_input_hash_int_float_normalized(self):
        # ★멱등 강건성: 같은 부지를 2000(정수) vs 2000.0(실수)으로 넣어도 같은 해시(수치 정규화).
        assert compute_input_hash({"site_area_sqm": 2000}) == compute_input_hash({"site_area_sqm": 2000.0})
        # 미세 부동소수(반올림 6자리 이내) 변동도 같은 해시 — 의미없는 변경에 둔감.
        assert compute_input_hash({"far": 1000.0}) == compute_input_hash({"far": 1000.0000001})
        # bool은 숫자로 정규화하지 않는다(True가 1.0이 되면 안 됨).
        assert compute_input_hash({"daylight_step": True}) != compute_input_hash({"daylight_step": 1})

    def test_make_run_id_deterministic_format(self):
        # run_id = "c2r_" + input_hash[:16](결정론·형식 잠금)
        h = compute_input_hash({"zone_code": "2R"})
        run_id = make_run_id(h)
        assert run_id == "c2r_" + h[:16]
        assert run_id.startswith("c2r_") and len(run_id) == len("c2r_") + 16
        # 같은 입력해시 → 같은 run_id(멱등)
        assert make_run_id(h) == run_id

    def test_geometry_hash_deterministic(self):
        # 같은 기하 → 같은 geometry_hash, 다른 기하 → 다른 해시
        g1 = {"num_floors": 12, "footprint_sqm": 400.0}
        g2 = {"footprint_sqm": 400.0, "num_floors": 12}  # 키 순서만 다름
        assert compute_geometry_hash(g1) == compute_geometry_hash(g2)
        g3 = {"num_floors": 13, "footprint_sqm": 400.0}
        assert compute_geometry_hash(g1) != compute_geometry_hash(g3)


class TestAdapterProvenance:
    """어댑터(mass_to_envelope_result)가 provenance 필드를 결정론·무날조로 채우는지(INC3)."""

    def test_input_fingerprint_fills_hash_and_run_id(self):
        fp = {"site_area_sqm": 2000.0, "zone_code": "GC"}
        er = mass_to_envelope_result(_podium_tower_mass(), input_fingerprint=fp)
        # input_hash·run_id가 결정론적으로 채워진다
        assert er.input_hash == compute_input_hash(fp)
        assert er.run_id == make_run_id(er.input_hash)
        # run_id 형식 잠금: "c2r_" + 16hex
        assert er.run_id.startswith("c2r_") and len(er.run_id) == len("c2r_") + 16

    def test_same_fingerprint_same_run_id_idempotent(self):
        # ★결정론: 같은 핑거프린트(키 순서만 달라도) → 같은 input_hash·run_id(멱등)
        fp1 = {"site_area_sqm": 2000.0, "zone_code": "GC", "building_use": "공동주택"}
        fp2 = {"building_use": "공동주택", "site_area_sqm": 2000.0, "zone_code": "GC"}
        er1 = mass_to_envelope_result(_podium_tower_mass(), input_fingerprint=fp1)
        er2 = mass_to_envelope_result(_podium_tower_mass(), input_fingerprint=fp2)
        assert er1.input_hash == er2.input_hash
        assert er1.run_id == er2.run_id

    def test_different_fingerprint_different_hash(self):
        er1 = mass_to_envelope_result(_podium_tower_mass(), input_fingerprint={"zone_code": "GC"})
        er2 = mass_to_envelope_result(_podium_tower_mass(), input_fingerprint={"zone_code": "2R"})
        assert er1.input_hash != er2.input_hash
        assert er1.run_id != er2.run_id

    def test_no_fingerprint_leaves_hash_and_run_id_none(self):
        # ★무날조: input_fingerprint가 없으면 input_hash/run_id는 None(가짜 해시 금지)
        er = mass_to_envelope_result(_podium_tower_mass())
        assert er.input_hash is None
        assert er.run_id is None
        # source_version·geometry_hash는 무날조와 무관하게 항상 채워진다
        assert er.source_version == ENGINE_SOURCE_VERSION
        assert er.geometry_hash is not None and len(er.geometry_hash) == 64

    def test_geometry_hash_computed_from_output_geometry(self):
        # geometry_hash는 산출 기하(EnvelopeGeometry)에서 계산된다 — 기하 동일 → 해시 동일
        mass = _podium_tower_mass()
        er1 = mass_to_envelope_result(mass)
        er2 = mass_to_envelope_result(dict(mass))  # 같은 기하 입력
        assert er1.geometry_hash == er2.geometry_hash
        assert er1.geometry_hash == compute_geometry_hash(er1.geometry.model_dump(mode="json"))
        # 기하가 바뀌면(층수↑) geometry_hash도 달라진다
        mass_diff = dict(mass)
        mass_diff["floors_for_units"] = 30
        er3 = mass_to_envelope_result(mass_diff)
        assert er3.geometry_hash != er1.geometry_hash

    def test_source_version_always_filled(self):
        # source_version은 코드 상수라 항상 유효(비-dict·빈 입력에도)
        assert mass_to_envelope_result({}).source_version == ENGINE_SOURCE_VERSION
        assert mass_to_envelope_result(None).source_version == ENGINE_SOURCE_VERSION  # type: ignore[arg-type]

    def test_non_dict_input_still_has_geometry_hash_and_source(self):
        # 비-dict 입력도 빈 기하 해시·source_version은 채운다(provenance 일관성)
        er = mass_to_envelope_result(None)  # type: ignore[arg-type]
        assert er.geometry_hash is not None and len(er.geometry_hash) == 64
        assert er.source_version == ENGINE_SOURCE_VERSION
        # 핑거프린트 없으니 input_hash/run_id는 None(무날조)
        assert er.input_hash is None and er.run_id is None


class TestGenerateProvenanceWiring:
    """generate() 결과 envelope_result에 provenance가 채워지고 기존 키는 불변(무회귀·INC3)."""

    def test_envelope_result_has_provenance_filled(self):
        engine = AutoDesignEngineService()
        result = engine.generate(SiteInput(site_area_sqm=2000, zone_code="GC", building_use="공동주택"))
        er = result.compliance["envelope_result"]
        # run_id/input_hash/geometry_hash/source_version 모두 채워짐
        assert er["run_id"] and er["run_id"].startswith("c2r_")
        assert er["input_hash"] and len(er["input_hash"]) == 64
        assert er["geometry_hash"] and len(er["geometry_hash"]) == 64
        assert er["source_version"] == ENGINE_SOURCE_VERSION
        # run_id는 input_hash 앞 16자 기반(결정론)
        assert er["run_id"] == "c2r_" + er["input_hash"][:16]

    def test_generate_run_id_deterministic_same_input(self):
        # ★멱등: 같은 site_input → 같은 run_id·input_hash(두 번 호출해도 동일)
        engine = AutoDesignEngineService()
        si = SiteInput(site_area_sqm=1500, zone_code="2R", building_use="공동주택")
        er1 = engine.generate(si).compliance["envelope_result"]
        er2 = engine.generate(si).compliance["envelope_result"]
        assert er1["run_id"] == er2["run_id"]
        assert er1["input_hash"] == er2["input_hash"]

    def test_generate_existing_compliance_keys_unchanged(self):
        # ★무회귀: provenance 배선이 기존 compliance 키를 건드리지 않는다(새 필드는 envelope_result 내부에만).
        engine = AutoDesignEngineService()
        result = engine.generate(SiteInput(site_area_sqm=500, zone_code="2R"))
        for key in (
            "bcr_ok", "far_ok", "height_ok", "setback_ok", "all_pass",
            "corrections_applied", "geometry_invariants", "geometry_invariant_blocked",
            "envelope_result",
        ):
            assert key in result.compliance, f"기존 compliance 키 {key} 누락 — 무회귀 위반"
