"""build_mass_contract 공용 헬퍼 + 전 설계경로 계약 배선 단위 테스트(C2R 계약 전역배선).

핵심 회귀잠금(무회귀·무날조):
- build_mass_contract가 매스에서 계약 묶음(envelope_result+geometry_invariants)을 만든다.
- site_input+legal이 있으면 rule_trace/rule_set_hash까지 채운다(자동산출 분기).
- site/legal이 없으면 rule_trace는 비고(가짜 entry 금지·무날조), 핑거프린트로 input_hash만 채운다.
- total_units 미상이면 '주거 0세대' 점검을 SKIP(가짜 FAIL 금지).
- generate() 결과 계약이 리팩토링 전후 동일(키·status·canonical_floors) — DRY 치환 거동 동일.
- _resolve_mass 미러: site+legal 매스에 build_mass_contract → mass["compliance"]에 envelope_result 존재.
- /mass 응답 조립 미러: 응답 dict에 compliance.envelope_result 포함(라우터 import 없이 조립 검증 —
  router는 auth_service(bcrypt) 의존으로 venv에서 import 불가 → 조립 로직만 미러).
"""

import pytest

from app.services.cad.auto_design_engine import AutoDesignEngineService, SiteInput
from app.services.cad.design_contract import build_mass_contract
from app.services.cad.envelope_result import mass_to_envelope_result


def _import_router():
    """라우터 _resolve_mass·BimGenerateRequest를 import한다(불가하면 graceful skip).

    왜(쉬운 설명): 라우터(design_v61)는 인증·DB 등 전체 의존성을 끌어오므로, 의존성이 없는
      가벼운 venv에서는 import가 안 될 수 있다. 그런 환경에선 이 테스트를 건너뛰고(skip),
      전체 의존성이 깔린 CI/프로덕션에서만 '라우터 실코드'로 배선을 검증한다(미러 한계 보완).
    """
    pytest.importorskip("fastapi")
    try:
        from app.routers.design_v61 import BimGenerateRequest, _resolve_mass
    except Exception as e:  # noqa: BLE001 — 의존성 부재 환경은 정직하게 skip
        pytest.skip(f"라우터 import 불가(이 환경엔 전체 의존성 없음): {str(e)[:80]}")
    return _resolve_mass, BimGenerateRequest


def _auto_mass(zone: str = "GC", use: str = "공동주택", area: float = 2000.0):
    """자동산출 매스(site+legal)를 _resolve_mass land_area 분기와 동일하게 만든다."""
    svc = AutoDesignEngineService()
    site = SiteInput(site_area_sqm=area, zone_code=zone, building_use=use, target_unit_types=["84A"])
    legal = svc.get_legal_limits(zone)
    eff = svc.compute_effective_site(site)
    mass = svc.compute_optimal_mass(site, eff, legal)
    return svc, site, legal, mass


class TestBuildMassContractWithSite:
    """site_input+legal이 있으면 envelope_result+geometry_invariants+rule_trace를 모두 만든다."""

    def test_returns_envelope_and_invariants(self):
        _svc, site, legal, mass = _auto_mass()
        contract = build_mass_contract(mass, site_input=site, legal=legal)
        assert set(contract.keys()) == {"envelope_result", "geometry_invariants"}
        er = contract["envelope_result"]
        assert er["schema_version"] == "propai.envelope_result.v0.1"
        assert er["status"] in {"PASS", "PASS_WITH_WARNINGS", "FAIL"}
        assert er["metrics"]["canonical_floors"] is not None

    def test_rule_trace_and_hash_present(self):
        # ★site+legal → 적용 법규 추적표(rule_trace)와 rule_set_hash가 채워진다.
        _svc, site, legal, mass = _auto_mass()
        er = build_mass_contract(mass, site_input=site, legal=legal)["envelope_result"]
        assert len(er["rule_trace"]) > 0, "site+legal이면 rule_trace entry가 있어야 한다"
        assert er["rule_set_hash"] is not None
        # provenance 핑거프린트는 site_input에서 구성 → input_hash·run_id가 결정론적으로 채워진다.
        assert er["input_hash"] is not None
        assert er["run_id"] is not None

    def test_geometry_invariants_attached_to_mass(self):
        # ★헬퍼는 mass["geometry_invariants"]만 additive로 채운다(매스 산출 키 무변경).
        _svc, site, legal, mass = _auto_mass()
        before_keys = set(mass.keys())
        build_mass_contract(mass, site_input=site, legal=legal)
        assert "geometry_invariants" in mass
        # 추가된 키는 geometry_invariants 하나뿐(다른 산출 키는 그대로).
        assert before_keys <= set(mass.keys())
        new_keys = set(mass.keys()) - before_keys
        assert new_keys == {"geometry_invariants"}

    def test_deterministic_same_input_same_hash(self):
        # ★결정론: 같은 입력이면 input_hash·run_id가 같다(멱등).
        _s1, site1, legal1, mass1 = _auto_mass()
        _s2, site2, legal2, mass2 = _auto_mass()
        er1 = build_mass_contract(mass1, site_input=site1, legal=legal1)["envelope_result"]
        er2 = build_mass_contract(mass2, site_input=site2, legal=legal2)["envelope_result"]
        assert er1["input_hash"] == er2["input_hash"]
        assert er1["run_id"] == er2["run_id"]


class TestBuildMassContractNoSite:
    """site/legal이 없는 분기(명시 치수·폴백) — rule_trace 생략(무날조), 핑거프린트만으로 input_hash."""

    def _dims_mass(self):
        return {
            "building_width_m": 20.0,
            "building_depth_m": 15.0,
            "num_floors": 10,
            "floor_height_m": 3.0,
        }

    def test_no_rule_trace_when_no_site_legal(self):
        # ★무날조: site/legal 없으면 rule_trace는 빈 리스트·rule_set_hash는 None(가짜 entry 금지).
        mass = self._dims_mass()
        fp = {"zone_code": "2R", "building_use": "공동주택", **mass}
        er = build_mass_contract(mass, fingerprint=fp)["envelope_result"]
        assert er["rule_trace"] == []
        assert er["rule_set_hash"] is None

    def test_input_hash_from_fingerprint(self):
        # 핑거프린트가 주어지면 input_hash·run_id가 채워진다(같은 요청이면 같은 run_id).
        mass = self._dims_mass()
        fp = {"zone_code": "2R", "building_use": "공동주택", **mass}
        er = build_mass_contract(mass, fingerprint=fp)["envelope_result"]
        assert er["input_hash"] is not None
        assert er["run_id"] is not None

    def test_no_fingerprint_means_no_input_hash(self):
        # 핑거프린트도 없으면 input_hash/run_id는 None(가짜 해시 금지·무날조). 단 geometry_hash는 항상.
        mass = self._dims_mass()
        er = build_mass_contract(mass)["envelope_result"]
        assert er["input_hash"] is None
        assert er["run_id"] is None
        assert er["geometry_hash"] is not None

    def test_total_units_unknown_skips_unit_check(self):
        # ★/mass 경로처럼 total_units 미상이면 '주거 0세대' 점검을 SKIP(가짜 FAIL 금지).
        mass = self._dims_mass()
        contract = build_mass_contract(mass)
        geo = contract["geometry_invariants"]
        codes = {c["code"] for c in geo["checks"]}
        assert "INV-GEO-UNITS" not in codes, "total_units 미상이면 세대 점검은 SKIP이어야 한다"
        assert geo["status"] != "FAIL"


class TestGenerateRefactorParity:
    """generate() DRY 치환 거동 동일 — 헬퍼 출력이 직접 어댑터 호출 결과와 정합(무회귀)."""

    def test_generate_compliance_has_full_contract(self):
        engine = AutoDesignEngineService()
        result = engine.generate(SiteInput(site_area_sqm=2000, zone_code="GC", building_use="공동주택"))
        # 계약이 compliance에 그대로 실린다.
        assert "envelope_result" in result.compliance
        assert "geometry_invariants" in result.compliance
        er = result.compliance["envelope_result"]
        assert er["schema_version"] == "propai.envelope_result.v0.1"
        assert len(er["rule_trace"]) > 0  # generate는 site+legal이 있으므로 rule_trace 존재
        assert er["rule_set_hash"] is not None

    def test_existing_compliance_keys_unchanged(self):
        # ★무회귀: 리팩토링 후에도 기존 compliance 키가 전부 존재해야 한다.
        engine = AutoDesignEngineService()
        result = engine.generate(SiteInput(site_area_sqm=500, zone_code="2R"))
        for key in (
            "bcr_ok", "far_ok", "height_ok", "setback_ok", "all_pass",
            "corrections_applied", "geometry_invariants", "geometry_invariant_blocked",
        ):
            assert key in result.compliance, f"기존 compliance 키 {key} 누락 — 무회귀 위반"

    def test_helper_envelope_matches_direct_adapter(self):
        # 헬퍼가 만든 envelope_result가 직접 어댑터(mass_to_envelope_result) 호출과 핵심 필드 정합.
        svc = AutoDesignEngineService()
        site = SiteInput(site_area_sqm=2000, zone_code="GC", building_use="공동주택", target_unit_types=["84A"])
        legal = svc.get_legal_limits("GC")
        eff = svc.compute_effective_site(site)
        mass = svc.compute_optimal_mass(site, eff, legal)
        helper_er = build_mass_contract(mass, site_input=site, legal=legal)["envelope_result"]
        # 직접 어댑터(같은 geo_invariants 사용) — geometry/metrics가 동일해야 한다.
        direct = mass_to_envelope_result(
            mass, geo_invariants=mass["geometry_invariants"]
        ).model_dump(mode="json")
        assert helper_er["geometry"] == direct["geometry"]
        assert helper_er["metrics"] == direct["metrics"]


class TestResolveMassMirror:
    """_resolve_mass land_area 분기 미러 — mass["compliance"]에 envelope_result가 부착된다."""

    def test_land_area_branch_attaches_compliance(self):
        _svc, site, legal, mass = _auto_mass()
        # _resolve_mass land_area 분기와 동일: build_mass_contract → mass["compliance"]
        mass["compliance"] = build_mass_contract(mass, site_input=site, legal=legal)
        assert "compliance" in mass
        assert "envelope_result" in mass["compliance"]
        assert mass["compliance"]["envelope_result"]["schema_version"] == "propai.envelope_result.v0.1"

    def test_mass_response_includes_compliance(self):
        # /mass 응답 조립 미러(라우터 import 없이) — 응답 dict에 compliance.envelope_result가 동봉된다.
        _svc, site, legal, mass = _auto_mass()
        mass["compliance"] = build_mass_contract(mass, site_input=site, legal=legal)
        # compute_design_mass return 형태를 그대로 조립(핵심 키 + 신규 compliance).
        bw, bd, nf = float(mass["building_width_m"]), float(mass["building_depth_m"]), int(mass["num_floors"])
        fh = float(mass.get("floor_height_m", 3.0))
        response = {
            "building_width_m": round(bw, 2),
            "building_depth_m": round(bd, 2),
            "num_floors": nf,
            "floor_height_m": fh,
            "bcr_pct": mass.get("bcr_pct"),
            "far_pct": mass.get("far_pct"),
            "compliance": mass.get("compliance"),
        }
        assert response["compliance"] is not None
        assert "envelope_result" in response["compliance"]
        assert response["compliance"]["envelope_result"]["metrics"]["canonical_floors"] is not None


class TestResolveMassRouterIntegration:
    """★미러가 아닌 '라우터 실코드' 통합검증 — _resolve_mass 3분기가 실제로 compliance를 부착하는지 잠근다.

    (코드리뷰 MEDIUM#2 보완) 미러 테스트는 로직을 손으로 복제해 라우터의 '호출'을 검증하지 못한다.
    이 클래스는 라우터 _resolve_mass를 직접 호출해, 분기 선택·계약 부착 배선을 실코드로 회귀잠금한다.
    전체 의존성이 깔린 CI/프로덕션에서 실행되고, 가벼운 venv에선 _import_router가 graceful skip한다.
    """

    def test_explicit_dims_branch_attaches_compliance(self):
        # 명시 치수 분기 → site/legal 없음 → envelope_result+geometry_invariants만(rule_trace 비고·무날조).
        _resolve_mass, BimGenerateRequest = _import_router()  # noqa: N806 — 클래스 언팩
        req = BimGenerateRequest(
            building_width_m=20.0, building_depth_m=15.0, floor_count=10, zone_code="3R",
        )
        mass = _resolve_mass(req)
        assert "compliance" in mass, "명시 치수 분기가 compliance를 부착해야 한다"
        er = mass["compliance"]["envelope_result"]
        assert er["schema_version"] == "propai.envelope_result.v0.1"
        # site/legal 없으므로 rule_trace는 비어있고 rule_set_hash는 None(가짜 entry 금지·무날조).
        assert er["rule_trace"] == []
        assert er["rule_set_hash"] is None
        # 핑거프린트로 input_hash는 채워진다(정직한 provenance).
        assert er["input_hash"]

    def test_land_area_branch_attaches_compliance_with_rule_trace(self):
        # 자동산출 분기 → site+legal 있음 → rule_trace/rule_set_hash까지 채운다.
        _resolve_mass, BimGenerateRequest = _import_router()  # noqa: N806 — 클래스 언팩
        req = BimGenerateRequest(land_area_sqm=2000.0, zone_code="GC", building_use="공동주택")
        mass = _resolve_mass(req)
        assert "compliance" in mass, "자동산출 분기가 compliance를 부착해야 한다"
        er = mass["compliance"]["envelope_result"]
        assert er["schema_version"] == "propai.envelope_result.v0.1"
        assert er["rule_trace"], "site+legal 분기는 rule_trace를 채워야 한다(≥1)"
        assert er["rule_set_hash"], "site+legal 분기는 rule_set_hash를 채워야 한다"

    def test_resolve_mass_is_deterministic(self):
        # 같은 요청 → 같은 run_id/input_hash(멱등) — provenance 결정론 회귀잠금.
        _resolve_mass, BimGenerateRequest = _import_router()  # noqa: N806 — 클래스 언팩

        def _run():
            req = BimGenerateRequest(land_area_sqm=2000.0, zone_code="GC", building_use="공동주택")
            return _resolve_mass(req)["compliance"]["envelope_result"]

        a, b = _run(), _run()
        assert a["run_id"] == b["run_id"]
        assert a["input_hash"] == b["input_hash"]
