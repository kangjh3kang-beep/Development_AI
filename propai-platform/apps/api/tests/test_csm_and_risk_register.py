"""CSM(Canonical Site Model) 조립체 + Risk Register 계약 테스트 (W2-6, v4.0 §P5 실용 1차).

검증 축:
 (a) assemble_csm — 결정론(동일 입력 → 동일 csm_hash), 섹션 5종 재구조화(값 참조만, 재계산 0).
 (b) diff_csm — 1개 섹션만 변경 시 그 섹션만 changed로 검출(부분 invalidation의 전제).
 (c) invalidation_advice — SECTION_DOWNSTREAM 선언적 매핑을 그대로 따름 + auto_reexecuted
     항상 False(자동 재실행 금지).
 (d) RiskItem — score=P×I×D, P/I/D 범위(1~5) 위반 시 거부.
 (e) RiskRegister — red_flag는 average_score와 무관하게 항상 표면화(평균 상쇄 금지).
 (f) build_risk_register — 기존 표식(special_parcel/ordinance/access_basis) → 리스크 도출,
     ParcelGraph CRITICAL·Required Data Matrix BLOCKED/CONDITIONAL(선택 입력) → 리스크 도출.
 (g) comprehensive_analysis_service 배선 계약 — _attach_csm_and_risk_register가 additive로만
     동작하고 실패해도 기존 분석 결과를 훼손하지 않음(무회귀).
"""
from __future__ import annotations

import pytest

from app.services.provenance.csm import (
    CSM_SECTION_NAMES,
    SECTION_DOWNSTREAM,
    assemble_csm,
    csm_from_dict,
    diff_csm,
    invalidation_advice,
    sections_of,
)
from app.services.provenance.risk_register import (
    RiskItem,
    RiskRegister,
    build_risk_register,
)

# ══════════════════════════════════════════════════════════════════════════
# (a) assemble_csm — 결정론 + 섹션 재구조화
# ══════════════════════════════════════════════════════════════════════════

_BASE_ANALYSIS: dict = {
    "pnu": "1111010100100010000",
    "address": "서울특별시 종로구 세종로 1",
    "zone_type": "제2종일반주거지역",
    "land_area_sqm": 500.0,
    "land_area_basis": {"gfa_basis": "단일/미제공 — 대지면적 그대로"},
    "parcel_count": 1,
    "integrated_zoning": None,
    "special_parcel": {"developability": "POSSIBLE", "category": None},
    "developability": "POSSIBLE",
    "allowed_buildings": {"allowed_types": ["공동주택"]},
    "dev_act_permit_gate": {"status": "PASS"},
    "upzoning": {"scenarios": []},
    "legal_refs": [],
    "evidence": [],
    "effective_far": {
        "national_far_pct": 200.0, "national_bcr_pct": 60.0,
        "ordinance_far_pct": 200.0, "ordinance_bcr_pct": 60.0,
        "effective_far_pct": 200.0, "effective_bcr_pct": 60.0,
        "ordinance_confirmed": True,
    },
    "access_basis": {"status": "PASS"},
    "land_prices": {"official_price_per_sqm": 3_000_000},
    "transaction_prices": {"count": 5},
    "sale_prices": {"estimated_per_pyeong": 3000},
    "location": {"grade": "A"},
    "development_plans": {"items": []},
}


def _clone(**overrides) -> dict:
    data = {k: (dict(v) if isinstance(v, dict) else v) for k, v in _BASE_ANALYSIS.items()}
    data.update(overrides)
    return data


def test_csm_section_names_are_exactly_5_and_map_p0_to_p4():
    assert CSM_SECTION_NAMES == ("parcel", "legal", "effective_limits", "access", "market")


def test_assemble_csm_is_deterministic_for_identical_input():
    csm1 = assemble_csm(_clone(), assembled_at="2026-07-23T00:00:00+00:00")
    csm2 = assemble_csm(_clone(), assembled_at="2026-07-23T00:00:00+00:00")
    assert csm1.csm_hash == csm2.csm_hash
    assert csm1.section_hashes == csm2.section_hashes


def test_assemble_csm_builds_all_5_sections_with_referenced_values_only():
    csm = assemble_csm(_BASE_ANALYSIS)
    assert set(csm.sections.keys()) == set(CSM_SECTION_NAMES)
    assert csm.sections["parcel"]["zone_type"] == "제2종일반주거지역"
    assert csm.sections["effective_limits"]["effective_far_pct"] == 200.0
    assert csm.sections["access"]["status"] == "PASS"
    assert csm.sections["market"]["land_prices"]["official_price_per_sqm"] == 3_000_000
    # sha256 hex 64자 — W2-3 handoff_bundle.compute_payload_checksum 알고리즘 재사용 확인.
    assert all(len(h) == 64 for h in csm.section_hashes.values())
    assert len(csm.csm_hash) == 64


def test_assemble_csm_handles_none_or_non_mapping_input_honestly():
    csm = assemble_csm(None)
    assert set(csm.sections.keys()) == set(CSM_SECTION_NAMES)
    assert all(v is None for v in csm.sections["parcel"].values())


def test_csm_round_trip_via_to_dict_and_csm_from_dict():
    csm = assemble_csm(_BASE_ANALYSIS)
    restored = csm_from_dict(csm.to_dict())
    assert restored is not None
    assert restored.csm_hash == csm.csm_hash
    assert restored.section_hashes == csm.section_hashes


def test_csm_from_dict_rejects_malformed_input_honestly():
    assert csm_from_dict(None) is None
    assert csm_from_dict({"not_a_csm": True}) is None
    assert csm_from_dict({"csm_hash": "abc"}) is None  # section_hashes 없음


def test_sections_of_accepts_both_instance_and_dict():
    csm = assemble_csm(_BASE_ANALYSIS)
    assert sections_of(csm) == csm.sections
    assert sections_of(csm.to_dict()) == csm.sections
    assert sections_of("not-a-csm") == {}  # 형식 안 맞으면 빈 dict(날조 금지)


def test_fact_refs_reflect_emptiness_per_section():
    csm = assemble_csm(_BASE_ANALYSIS)
    assert csm.fact_refs["parcel"]["fact_status"] == "DERIVED"
    empty_csm = assemble_csm(None)
    assert empty_csm.fact_refs["parcel"]["fact_status"] == "UNKNOWN"
    assert empty_csm.fact_refs["parcel"]["traced"] is False


# ══════════════════════════════════════════════════════════════════════════
# (b)(c) diff_csm + invalidation_advice — 부분 invalidation
# ══════════════════════════════════════════════════════════════════════════


def test_diff_csm_detects_only_the_changed_section():
    old = assemble_csm(_BASE_ANALYSIS)
    new_analysis = _clone()
    new_analysis["effective_far"]["effective_far_pct"] = 150.0  # legal 한도만 변경
    new = assemble_csm(new_analysis)
    changed = diff_csm(old, new)
    assert changed == ["effective_limits"]


def test_diff_csm_detects_multiple_changed_sections_independently():
    old = assemble_csm(_BASE_ANALYSIS)
    new_analysis = _clone()
    new_analysis["access_basis"]["status"] = "BLOCKED"
    new_analysis["sale_prices"]["estimated_per_pyeong"] = 5000
    new = assemble_csm(new_analysis)
    changed = diff_csm(old, new)
    assert set(changed) == {"access", "market"}
    assert "parcel" not in changed
    assert "legal" not in changed
    assert "effective_limits" not in changed


def test_diff_csm_with_no_prior_treats_all_sections_as_changed():
    new = assemble_csm(_BASE_ANALYSIS)
    assert set(diff_csm(None, new)) == set(CSM_SECTION_NAMES)


def test_diff_csm_no_change_when_analysis_identical():
    old = assemble_csm(_BASE_ANALYSIS)
    new = assemble_csm(_clone())
    assert diff_csm(old, new) == []


def test_invalidation_advice_legal_change_recommends_design_and_feasibility():
    advice = invalidation_advice(["legal"])
    assert advice["recommended_reanalysis"] == ["design", "feasibility"]
    assert advice["reasons"]["design"] == ["legal"]
    assert advice["reasons"]["feasibility"] == ["legal"]
    assert advice["auto_reexecuted"] is False


def test_invalidation_advice_market_change_recommends_feasibility_only():
    advice = invalidation_advice(["market"])
    assert advice["recommended_reanalysis"] == ["feasibility"]


def test_invalidation_advice_access_change_recommends_design_and_feasibility():
    """R1 반영: 접도 변경(맹지화 등)은 설계뿐 아니라 사업성(pro-forma) 직결 —
    과소통보보다 과다통보가 안전(diff_csm 원칙)."""
    advice = invalidation_advice(["access"])
    assert advice["recommended_reanalysis"] == ["design", "feasibility"]


def test_invalidation_advice_no_change_recommends_nothing():
    advice = invalidation_advice([])
    assert advice["recommended_reanalysis"] == []
    assert advice["auto_reexecuted"] is False


def test_section_downstream_dependency_table_covers_all_5_sections():
    assert set(SECTION_DOWNSTREAM.keys()) == set(CSM_SECTION_NAMES)


# ══════════════════════════════════════════════════════════════════════════
# (d) RiskItem — score=P×I×D + 범위 검증
# ══════════════════════════════════════════════════════════════════════════


def test_risk_item_score_is_product_of_p_i_d():
    item = RiskItem(
        risk_id="r1", category="parcel", description="테스트",
        probability=3, impact=4, detection_difficulty=2,
    )
    assert item.score == 24


@pytest.mark.parametrize("field_name", ["probability", "impact", "detection_difficulty"])
def test_risk_item_rejects_out_of_range_scale(field_name):
    kwargs = {"probability": 3, "impact": 3, "detection_difficulty": 3}
    kwargs[field_name] = 6
    with pytest.raises(ValueError):
        RiskItem(risk_id="r1", category="c", description="d", **kwargs)


def test_risk_item_rejects_zero_and_bool_scale():
    with pytest.raises(ValueError):
        RiskItem(risk_id="r1", category="c", description="d", probability=0, impact=3, detection_difficulty=3)
    with pytest.raises(ValueError):
        RiskItem(risk_id="r1", category="c", description="d", probability=True, impact=3, detection_difficulty=3)


# ══════════════════════════════════════════════════════════════════════════
# (e) RiskRegister — Red Flag는 평균 상쇄 금지
# ══════════════════════════════════════════════════════════════════════════


def test_red_flag_surfaces_regardless_of_low_average_score():
    low1 = RiskItem(risk_id="low1", category="c", description="low1", probability=1, impact=1, detection_difficulty=1)
    low2 = RiskItem(risk_id="low2", category="c", description="low2", probability=1, impact=1, detection_difficulty=1)
    red = RiskItem(
        risk_id="red1", category="c", description="치명적", probability=1, impact=1, detection_difficulty=1,
        red_flag=True,
    )
    register = RiskRegister(items=[low1, low2, red], generated_at="2026-07-23T00:00:00+00:00")
    as_dict = register.to_dict()
    # 평균 점수는 낮지만(1점씩) red_flag는 그와 무관하게 항상 노출된다.
    assert as_dict["average_score"] == 1.0
    assert as_dict["red_flag_count"] == 1
    assert [r["risk_id"] for r in as_dict["red_flags"]] == ["red1"]


def test_risk_register_empty_items_has_none_average_and_max():
    register = RiskRegister(items=[], generated_at="2026-07-23T00:00:00+00:00")
    as_dict = register.to_dict()
    assert as_dict["average_score"] is None
    assert as_dict["max_score"] is None
    assert as_dict["red_flag_count"] == 0


# ══════════════════════════════════════════════════════════════════════════
# (f) build_risk_register — 기존 표식 재사용 → 리스크 도출
# ══════════════════════════════════════════════════════════════════════════


def test_needs_official_survey_special_parcel_produces_red_flag_risk():
    analysis = _clone(special_parcel={"developability": "NEEDS_OFFICIAL_SURVEY", "category": "임야(산지)"})
    csm = assemble_csm(analysis)
    register = build_risk_register(csm)
    parcel_risks = [i for i in register.items if i.category == "parcel"]
    assert len(parcel_risks) == 1
    assert parcel_risks[0].red_flag is True
    assert "NEEDS_OFFICIAL_SURVEY" in parcel_risks[0].basis


def test_possible_special_parcel_produces_no_survey_risk():
    csm = assemble_csm(_BASE_ANALYSIS)  # developability=POSSIBLE
    register = build_risk_register(csm)
    assert not [i for i in register.items if "NEEDS_OFFICIAL_SURVEY" in i.basis]


def test_unconfirmed_ordinance_produces_legal_risk_without_red_flag():
    analysis = _clone()
    analysis["effective_far"]["ordinance_confirmed"] = False
    csm = assemble_csm(analysis)
    register = build_risk_register(csm)
    legal_risks = [i for i in register.items if i.category == "legal"]
    assert len(legal_risks) == 1
    assert legal_risks[0].red_flag is False


def test_confirmed_ordinance_produces_no_legal_risk():
    csm = assemble_csm(_BASE_ANALYSIS)  # ordinance_confirmed=True
    register = build_risk_register(csm)
    assert not [i for i in register.items if i.category == "legal"]


def test_access_requires_authority_confirmation_produces_red_flag_risk():
    analysis = _clone(access_basis={"status": "REQUIRES_AUTHORITY_CONFIRMATION"})
    csm = assemble_csm(analysis)
    register = build_risk_register(csm)
    access_risks = [i for i in register.items if i.category == "access"]
    assert len(access_risks) == 1
    assert access_risks[0].red_flag is True


def test_access_pass_produces_no_access_risk():
    csm = assemble_csm(_BASE_ANALYSIS)  # access_basis.status=PASS
    register = build_risk_register(csm)
    assert not [i for i in register.items if i.category == "access"]


def test_parcel_graph_critical_parcels_produce_red_flag_risk_when_provided():
    csm = assemble_csm(_BASE_ANALYSIS)
    parcel_graph = {
        "critical_parcels": {"CRITICAL": ["11110-1", "11110-2"], "IMPORTANT": [], "NORMAL": []},
    }
    register = build_risk_register(csm, parcel_graph=parcel_graph)
    critical_risks = [i for i in register.items if "핵심필지" in i.description]
    assert len(critical_risks) == 1
    assert critical_risks[0].red_flag is True
    assert critical_risks[0].category == "parcel"


def test_parcel_graph_without_critical_parcels_produces_no_extra_risk():
    csm = assemble_csm(_BASE_ANALYSIS)
    parcel_graph = {"critical_parcels": {"CRITICAL": [], "IMPORTANT": ["x"], "NORMAL": []}}
    register = build_risk_register(csm, parcel_graph=parcel_graph)
    assert not [i for i in register.items if "핵심필지" in i.description]


def test_parcel_graph_none_does_not_raise_and_produces_no_critical_risk():
    csm = assemble_csm(_BASE_ANALYSIS)
    register = build_risk_register(csm, parcel_graph=None)
    assert not [i for i in register.items if "핵심필지" in i.description]


def test_required_data_matrix_blocked_produces_red_flag_data_readiness_risk():
    from app.services.provenance.required_data import DataRequirement, evaluate_matrix

    matrix = evaluate_matrix(
        [DataRequirement(field="max_far", requirement_level="required", critical=True)],
        {},  # max_far 결측 → BLOCKED
    )
    csm = assemble_csm(_BASE_ANALYSIS)
    register = build_risk_register(csm, required_data=matrix)
    dr_risks = [i for i in register.items if i.category == "data_readiness"]
    assert len(dr_risks) == 1
    assert dr_risks[0].red_flag is True
    assert "BLOCKED" in dr_risks[0].basis


def test_required_data_matrix_conditional_produces_non_red_flag_risk():
    from app.services.provenance.required_data import DataRequirement, evaluate_matrix

    matrix = evaluate_matrix(
        [DataRequirement(field="road_width_m", requirement_level="recommended")],
        {},  # 결측이지만 recommended·critical=False → CONDITIONAL
    )
    assert matrix.decision == "CONDITIONAL"
    csm = assemble_csm(_BASE_ANALYSIS)
    register = build_risk_register(csm, required_data=matrix)
    dr_risks = [i for i in register.items if i.category == "data_readiness"]
    assert len(dr_risks) == 1
    assert dr_risks[0].red_flag is False


def test_required_data_matrix_pass_produces_no_data_readiness_risk():
    from app.services.provenance.required_data import DataRequirement, evaluate_matrix

    matrix = evaluate_matrix(
        [DataRequirement(field="zone_type", requirement_level="required", critical=True)],
        {"zone_type": "제2종일반주거지역"},
    )
    assert matrix.decision == "PASS"
    csm = assemble_csm(_BASE_ANALYSIS)
    register = build_risk_register(csm, required_data=matrix)
    assert not [i for i in register.items if i.category == "data_readiness"]


def test_required_data_matrix_accepts_plain_dict_form():
    csm = assemble_csm(_BASE_ANALYSIS)
    register = build_risk_register(
        csm, required_data={"decision": "BLOCKED", "conditional_reasons": ["road_width_m: 값 없음"]},
    )
    dr_risks = [i for i in register.items if i.category == "data_readiness"]
    assert len(dr_risks) == 1
    assert dr_risks[0].red_flag is True


def test_build_risk_register_accumulates_multiple_rules_simultaneously():
    analysis = _clone(
        special_parcel={"developability": "NEEDS_OFFICIAL_SURVEY", "category": "임야(산지)"},
        access_basis={"status": "REQUIRES_AUTHORITY_CONFIRMATION"},
    )
    analysis["effective_far"]["ordinance_confirmed"] = False
    csm = assemble_csm(analysis)
    register = build_risk_register(csm)
    categories = sorted(i.category for i in register.items)
    assert categories == ["access", "legal", "parcel"]
    assert register.to_dict()["red_flag_count"] == 2  # parcel(survey)·access 만 red_flag


def test_build_risk_register_accepts_csm_dict_form_as_well():
    csm = assemble_csm(_clone(special_parcel={"developability": "NEEDS_OFFICIAL_SURVEY", "category": None}))
    register = build_risk_register(csm.to_dict())
    assert any(i.category == "parcel" for i in register.items)


# ══════════════════════════════════════════════════════════════════════════
# (g) comprehensive_analysis_service 배선 — additive + 무회귀
# ══════════════════════════════════════════════════════════════════════════


def test_wiring_attaches_csm_hash_and_risk_register_additively():
    from app.services.land_intelligence.comprehensive_analysis_service import (
        _attach_csm_and_risk_register,
    )

    result = _clone()
    existing_keys = set(result.keys())
    _attach_csm_and_risk_register(result)
    assert "csm_hash" in result
    assert "risk_register" in result
    assert len(result["csm_hash"]) == 64
    assert isinstance(result["risk_register"], dict)
    # 기존 키는 전혀 제거/변경되지 않는다(additive — 신규 키 2개만 늘어난다).
    assert existing_keys.issubset(result.keys())
    assert result["zone_type"] == _BASE_ANALYSIS["zone_type"]


def test_wiring_failure_does_not_raise_and_leaves_result_untouched():
    """직렬화 불가(순환참조) 입력 — compute_payload_checksum(json.dumps) 강제 실패 유발."""
    from app.services.land_intelligence.comprehensive_analysis_service import (
        _attach_csm_and_risk_register,
    )

    result: dict = {"address": "테스트", "effective_far": {}}
    result["effective_far"]["self_ref"] = result["effective_far"]  # 순환참조

    _attach_csm_and_risk_register(result)  # 예외를 던지지 않아야 한다(degrade 로그만)
    assert result["address"] == "테스트"  # 기존 값 무손상
    assert "csm_hash" not in result  # 실패 시 additive 키는 부착되지 않는다
