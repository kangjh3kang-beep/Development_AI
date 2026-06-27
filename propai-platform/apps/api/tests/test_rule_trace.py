"""rule_trace + rule_set_hash 단위 테스트(C2R rule kernel trace + §4 rule_set_hash·INC5-a).

핵심 회귀잠금:
- 주거지역(2R) → 정북일조(solar_61_86) entry 포함, 상업(GC) → solar entry 제외(적용 안 됨·무날조)
- 조례값 주어지면 ordinance entry 포함, 없으면 제외(무날조·가짜 entry 금지)
- rule_set_hash 결정론(같은 입력 같은 해시·키순서 무관·int/float 둔감)
- generate() envelope_result에 rule_trace·rule_set_hash 채워짐 + 기존 키 무변경(무회귀)
- ★수치 무변경: rule_trace 부착 전후 매스 수치(num_floors·far_pct 등) 동일(회귀잠금)
"""

import copy

from app.services.cad.auto_design_engine import AutoDesignEngineService, SiteInput
from app.services.cad.provenance import compute_input_hash
from app.services.cad.rule_trace import build_rule_trace


def _entry(rule_trace: list[dict], rule_code: str) -> dict | None:
    """rule_trace에서 특정 rule_code의 entry를 찾는다(없으면 None)."""
    return next((e for e in rule_trace if e["rule_code"] == rule_code), None)


def _legal(zone: str) -> dict:
    """get_legal_limits 반환값(법정 한도 dict)을 그대로 쓴다(실 경로 정합)."""
    return AutoDesignEngineService.get_legal_limits(zone)


def _mass(site: SiteInput, legal: dict) -> dict:
    """compute_optimal_mass 출력(매스 dict)을 실제 엔진으로 산출한다(read-only 검증용)."""
    eff = AutoDesignEngineService.compute_effective_site(site)
    return AutoDesignEngineService.compute_optimal_mass(site, eff, legal)


class TestSolarEntryByZone:
    """정북일조(solar_61_86) entry는 주거지역에만 — 상업/준주거에는 없음(적용 안 됨·무날조)."""

    def test_residential_2r_includes_solar(self):
        site = SiteInput(site_area_sqm=1000, zone_code="2R", building_use="공동주택")
        legal = _legal("2R")
        rt, _ = build_rule_trace(site, legal, _mass(site, legal))
        solar = _entry(rt, "건축법_61/시행령_86")
        assert solar is not None  # 주거지역 → 정북일조 적용
        assert solar["applied"]["sunlight_mode"] in {"hard_cap", "step_profile"}
        assert "정북" in solar["basis"]

    def test_commercial_gc_excludes_solar(self):
        site = SiteInput(site_area_sqm=2000, zone_code="GC", building_use="공동주택")
        legal = _legal("GC")
        rt, _ = build_rule_trace(site, legal, _mass(site, legal))
        # 상업지역(GC) → 정북일조 미적용(sunlight_mode=not_applicable) → entry 없음(무날조)
        assert _entry(rt, "건축법_61/시행령_86") is None

    def test_area_119_always_present(self):
        # 용적률·건폐율 한도(area_119)는 항상 entry(주거·상업 공통).
        for zone in ("2R", "GC"):
            site = SiteInput(site_area_sqm=1500, zone_code=zone)
            legal = _legal(zone)
            rt, _ = build_rule_trace(site, legal, _mass(site, legal))
            area = _entry(rt, "건축법시행령_119/국토계획법시행령_84_85")
            assert area is not None
            assert "용적률" in area["basis"] and "건폐율" in area["basis"]


class TestOrdinanceEntry:
    """조례(ordinance) entry는 조례값이 주어진 경우에만(무날조 — 없으면 제외)."""

    def test_ordinance_given_includes_entry(self):
        site = SiteInput(
            site_area_sqm=1000, zone_code="2R",
            ordinance_far_percent=180.0, ordinance_bcr_percent=55.0,
        )
        legal = _legal("2R")
        rt, _ = build_rule_trace(site, legal, _mass(site, legal))
        ord_entry = _entry(rt, "지자체_도시계획조례")
        assert ord_entry is not None
        assert ord_entry["applied"]["ordinance_far_pct"] == 180.0
        assert ord_entry["applied"]["ordinance_bcr_pct"] == 55.0

    def test_no_ordinance_excludes_entry(self):
        # 조례값 미주입 → ordinance entry 없음(가짜 entry 금지)
        site = SiteInput(site_area_sqm=1000, zone_code="2R")
        legal = _legal("2R")
        rt, _ = build_rule_trace(site, legal, _mass(site, legal))
        assert _entry(rt, "지자체_도시계획조례") is None

    def test_partial_ordinance_far_only_includes_entry(self):
        # 조례 far만 주어져도 entry 포함, bcr는 None(무날조 — 미상은 None)
        site = SiteInput(site_area_sqm=1000, zone_code="2R", ordinance_far_percent=190.0)
        legal = _legal("2R")
        rt, _ = build_rule_trace(site, legal, _mass(site, legal))
        ord_entry = _entry(rt, "지자체_도시계획조례")
        assert ord_entry is not None
        assert ord_entry["applied"]["ordinance_far_pct"] == 190.0
        assert ord_entry["applied"]["ordinance_bcr_pct"] is None


class TestBindingEntry:
    """층수 결속요인(binding) entry는 binding_constraint가 있으면 포함."""

    def test_binding_entry_present(self):
        site = SiteInput(site_area_sqm=1000, zone_code="2R")
        legal = _legal("2R")
        mass = _mass(site, legal)
        rt, _ = build_rule_trace(site, legal, mass)
        binding = _entry(rt, "binding_constraint")
        assert binding is not None
        assert binding["applied"]["binding_constraint"] == mass["binding_constraint"]
        assert binding["applied"]["num_floors"] == mass["num_floors"]


class TestRuleSetHashDeterminism:
    """rule_set_hash 결정론 — 같은 입력 같은 해시(키순서·int/float 무관)."""

    def test_same_input_same_hash(self):
        site = SiteInput(site_area_sqm=1000, zone_code="2R", ordinance_far_percent=180.0)
        legal = _legal("2R")
        mass = _mass(site, legal)
        _, rs1 = build_rule_trace(site, legal, mass)
        _, rs2 = build_rule_trace(site, legal, mass)
        assert compute_input_hash(rs1) == compute_input_hash(rs2)
        # sha256 16진수 64자
        h = compute_input_hash(rs1)
        assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)

    def test_hash_key_order_invariant(self):
        # rule_set 키 순서를 섞어도 같은 해시(canonical_json sort_keys 재사용)
        site = SiteInput(site_area_sqm=1000, zone_code="2R")
        legal = _legal("2R")
        _, rs = build_rule_trace(site, legal, _mass(site, legal))
        shuffled = dict(reversed(list(rs.items())))
        assert compute_input_hash(rs) == compute_input_hash(shuffled)

    def test_different_zone_different_hash(self):
        # 다른 용도지역 → 다른 rule_set_hash(출처 구분)
        s2r = SiteInput(site_area_sqm=1500, zone_code="2R")
        sgc = SiteInput(site_area_sqm=1500, zone_code="GC")
        _, rs_2r = build_rule_trace(s2r, _legal("2R"), _mass(s2r, _legal("2R")))
        _, rs_gc = build_rule_trace(sgc, _legal("GC"), _mass(sgc, _legal("GC")))
        assert compute_input_hash(rs_2r) != compute_input_hash(rs_gc)

    def test_hash_int_float_normalized(self):
        # 같은 한도를 int vs float로 넣어도 같은 해시(normalize_fingerprint 재사용)
        site_i = SiteInput(site_area_sqm=1000, zone_code="2R", ordinance_far_percent=180)
        site_f = SiteInput(site_area_sqm=1000, zone_code="2R", ordinance_far_percent=180.0)
        legal = _legal("2R")
        _, rs_i = build_rule_trace(site_i, legal, _mass(site_i, legal))
        _, rs_f = build_rule_trace(site_f, legal, _mass(site_f, legal))
        assert compute_input_hash(rs_i) == compute_input_hash(rs_f)


class TestNoFabrication:
    """무날조 — 비-dict·빈 입력에도 예외 없이 동작(미상은 None·entry 누락 없음)."""

    def test_empty_inputs_safe(self):
        # legal·mass가 비어도 area_119 entry는 만들되 값은 None(가짜값 금지)
        rt, rs = build_rule_trace(SiteInput(site_area_sqm=0), {}, {})
        area = _entry(rt, "건축법시행령_119/국토계획법시행령_84_85")
        assert area is not None
        assert area["applied"]["far_pct"] is None
        # solar/ordinance/binding은 적용 안 됐으니 entry 없음
        assert _entry(rt, "건축법_61/시행령_86") is None
        assert _entry(rt, "지자체_도시계획조례") is None
        assert _entry(rt, "binding_constraint") is None
        # rule_set은 항상 dict(해시 가능)
        assert isinstance(rs, dict) and "zone_code" in rs

    def test_non_dict_legal_mass_absorbed(self):
        # legal/mass가 dict가 아니어도 예외 없이 빈 값으로 흡수
        rt, rs = build_rule_trace(SiteInput(site_area_sqm=100), None, None)  # type: ignore[arg-type]
        assert isinstance(rt, list) and isinstance(rs, dict)


class TestGenerateWiring:
    """generate() envelope_result에 rule_trace·rule_set_hash가 채워지고 기존 키는 불변(무회귀)."""

    def test_envelope_result_has_rule_trace_and_hash(self):
        engine = AutoDesignEngineService()
        result = engine.generate(SiteInput(site_area_sqm=1000, zone_code="2R", building_use="공동주택"))
        er = result.compliance["envelope_result"]
        assert er["rule_set_hash"] and len(er["rule_set_hash"]) == 64
        assert isinstance(er["rule_trace"], list) and len(er["rule_trace"]) >= 1
        codes = {e["rule_code"] for e in er["rule_trace"]}
        # 주거(2R) → 정북일조 entry 포함, area_119는 항상
        assert "건축법시행령_119/국토계획법시행령_84_85" in codes
        assert "건축법_61/시행령_86" in codes

    def test_commercial_no_solar_entry_in_generate(self):
        engine = AutoDesignEngineService()
        result = engine.generate(SiteInput(site_area_sqm=2000, zone_code="GC", building_use="공동주택"))
        er = result.compliance["envelope_result"]
        codes = {e["rule_code"] for e in er["rule_trace"]}
        assert "건축법_61/시행령_86" not in codes  # 상업 → 정북일조 미적용

    def test_generate_rule_set_hash_deterministic(self):
        # ★멱등: 같은 site_input → 같은 rule_set_hash(두 번 호출해도 동일)
        engine = AutoDesignEngineService()
        si = SiteInput(site_area_sqm=1500, zone_code="2R", building_use="공동주택")
        er1 = engine.generate(si).compliance["envelope_result"]
        er2 = engine.generate(si).compliance["envelope_result"]
        assert er1["rule_set_hash"] == er2["rule_set_hash"]

    def test_existing_compliance_keys_unchanged(self):
        # ★무회귀: rule_trace 배선이 기존 compliance 키를 건드리지 않는다(새 필드는 envelope_result 내부에만).
        engine = AutoDesignEngineService()
        result = engine.generate(SiteInput(site_area_sqm=500, zone_code="2R"))
        for key in (
            "bcr_ok", "far_ok", "height_ok", "setback_ok", "all_pass",
            "corrections_applied", "geometry_invariants", "geometry_invariant_blocked",
            "envelope_result",
        ):
            assert key in result.compliance, f"기존 compliance 키 {key} 누락 — 무회귀 위반"


class TestNumbersUnchanged:
    """★수치 무변경 회귀잠금 — rule_trace는 매스/요약 수치를 절대 바꾸지 않는다(읽기 전용)."""

    def test_mass_dict_not_mutated_by_build(self):
        # build_rule_trace는 순수 읽기 — mass dict를 절대 변경하지 않는다.
        site = SiteInput(site_area_sqm=1000, zone_code="2R")
        legal = _legal("2R")
        mass = _mass(site, legal)
        before = copy.deepcopy(mass)
        build_rule_trace(site, legal, mass)
        assert mass == before

    def test_summary_numbers_match_envelope(self):
        # generate() 결과에서 summary 매스 수치 == envelope_result.metrics(부착이 수치를 바꾸지 않음)
        engine = AutoDesignEngineService()
        result = engine.generate(SiteInput(site_area_sqm=1200, zone_code="2R", building_use="공동주택"))
        er = result.compliance["envelope_result"]
        assert result.summary["num_floors"] == er["geometry"]["num_floors"]
        assert result.summary["far_percent"] == er["metrics"]["far_pct"]
        assert result.summary["bcr_percent"] == er["metrics"]["bcr_pct"]
        assert result.summary["total_floor_area_sqm"] == er["metrics"]["gfa_sqm"]
