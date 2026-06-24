"""특이부지 '개발 불가' → '개발가능 방안(선행절차)' 제시 검증.

★사용자 피드백: 특이부지를 '개발 불가'로 끝내지 말고 인허가·도시계획 변경 등 개발가능
방법을 제시. special_parcel이 보유한 resolution_paths·permit_prerequisites·alternatives를
추천 방안으로 surface하는지 확인.
"""
from app.services.development.scenario_simulator import DevelopmentScenarioSimulator as Sim


def test_resolution_extracted_from_gate():
    """게이트 resolution_paths + factor permit_prerequisites + alternatives 집계(중복 제거)."""
    gate = {
        "developability": "BLOCKED", "resolvable": "NO",
        "resolution_paths": ["도시계획시설(학교) 폐지·실효", "도시·군관리계획 변경"],
        "alternatives": ["해당 필지 제외 검토"],
        "factors": [{
            "category": "학교용지(도시계획시설 가능성)",
            "permit_prerequisites": ["교육청 협의(공립)", "도시계획시설 폐지/변경 절차 착수",
                                     "도시·군관리계획 변경"],  # 중복
            "legal_ref_keys": ["urban_planning_facility", "edu_env_protection"],
        }],
    }
    methods, ref_keys, alts = Sim._resolution_from_gate(gate)
    assert "도시·군관리계획 변경" in methods
    assert "교육청 협의(공립)" in methods
    assert methods.count("도시·군관리계획 변경") == 1  # 중복 제거
    assert "urban_planning_facility" in ref_keys
    assert "해당 필지 제외 검토" in alts


def test_empty_gate_safe():
    """빈/누락 게이트도 안전(빈 리스트)."""
    assert Sim._resolution_from_gate({}) == ([], [], [])
    assert Sim._resolution_from_gate({"factors": [{}]}) == ([], [], [])


def test_methods_present_means_developable_via_precondition():
    """resolution_paths/permit_prerequisites가 있으면 '선행절차 통해 개발 가능' 신호."""
    gate = {"factors": [{"permit_prerequisites": ["농지전용허가", "농지보전부담금 납부"],
                         "legal_ref_keys": ["farmland_conversion"]}]}
    methods, ref_keys, _ = Sim._resolution_from_gate(gate)
    assert methods and "농지전용허가" in methods
    assert "farmland_conversion" in ref_keys
