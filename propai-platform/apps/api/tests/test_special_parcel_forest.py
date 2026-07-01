"""임야(산지) 공식 산림데이터 게이트(E1) 검증.

★배경(레드팀 P1-2): 임목본수도·경사도는 인허가급 데이터가 아니다. 산림청 공식 조사데이터
(산지구분·평균경사도·입목축적 등)가 없으면 산지전용 확정 판단이 불가하므로, 임야 필지는
'확정 설계'를 내지 않고 '참고용 예비안(NEEDS_OFFICIAL_SURVEY)'으로만 강등돼야 한다.

이 테스트는 임야 지목이 NEEDS_OFFICIAL_SURVEY로 판정되고, 게이트가 TENTATIVE(참고안)로
환원되며, 정직-실패 문구와 forest_facts(전부 미상=None)가 붙는지 확인한다.
"""
from app.services.zoning.special_parcel import (
    _RANK,
    GATE_TENTATIVE_DEVELOPABILITY,
    _rule_by_land_category,
    detect_multi_parcel,
    detect_special_parcel,
    gate_decision,
    tentative_marker,
)

# 정직-실패 마커(적어도 하나는 포함돼야 임야 필지가 '확정 아님·참고안·공식조사'로 고지된 것).
_HONEST_SURVEY_MARKERS = ("확정 아님", "참고", "공식")


def test_forest_land_category_needs_official_survey():
    """(a) 임야/산림 지목 → developability==NEEDS_OFFICIAL_SURVEY, official_survey_required True,
    forest_facts에 정량 필드가 전부 미상(None)으로 존재."""
    for cat in ("임야", "산림", "임야(산지)"):
        rule = _rule_by_land_category(cat)
        assert rule is not None, f"{cat} 규칙이 감지되지 않음"
        assert rule["developability"] == "NEEDS_OFFICIAL_SURVEY", f"{cat}: {rule['developability']}"
        # 공식조사 필요·확정 차단 신호.
        assert rule["official_survey_required"] is True
        assert rule["blocking_unknown"] is True
        # forest_facts — E3가 채울 정량 필드가 현재는 전부 None(무날조).
        facts = rule["forest_facts"]
        assert isinstance(facts, dict)
        expected_keys = {
            "보전산지_여부", "산지구분", "평균경사도_pct", "표고비율_pct",
            "입목축적_per_ha", "관할평균_입목축적_per_ha", "임상", "official_data_source",
        }
        assert set(facts.keys()) == expected_keys, f"forest_facts 키 불일치: {facts.keys()}"
        assert all(v is None for v in facts.values()), "forest_facts 정량 필드는 아직 전부 미상(None)이어야 함"
        # 산림조사 관련 선행요건이 확장됐는지.
        prereqs = " ".join(rule["permit_prerequisites"])
        assert "산림조사서" in prereqs and "대체산림자원조성비" in prereqs
        # legal_ref_keys는 forest_conversion 유지.
        assert rule["legal_ref_keys"] == ["forest_conversion"]


def test_gate_decision_forest_is_tentative():
    """(b) gate_decision("NEEDS_OFFICIAL_SURVEY", None) == "TENTATIVE"(참고안 — BLOCK도 PASS도 아님)."""
    assert gate_decision("NEEDS_OFFICIAL_SURVEY", None) == "TENTATIVE"
    # 소문자/공백 정규화도 안전.
    assert gate_decision(" needs_official_survey ", None) == "TENTATIVE"
    # 대조군: 확정 개발부지가 아님을 명시(PASS 아님).
    assert gate_decision("POSSIBLE", "YES") == "PASS"


def test_tentative_marker_forest_survey_text():
    """(c) tentative_marker("NEEDS_OFFICIAL_SURVEY", None) → 공식 산림조사 필요 정직 문구."""
    msg = tentative_marker("NEEDS_OFFICIAL_SURVEY", None)
    assert "공식 산림데이터" in msg
    assert "산림조사서" in msg
    assert "확정" in msg  # 확정 아님을 명시
    # 산지구분·경사도·입목축적 정량 항목이 문구에 언급되는지(정직 고지).
    assert "평균경사도" in msg and "입목축적" in msg


def test_rank_contains_needs_official_survey():
    """(d) _RANK에 새 값이 잠정(=CONDITIONAL와 동일 값 2)으로 존재. 기존 값 불변."""
    assert "NEEDS_OFFICIAL_SURVEY" in _RANK
    assert _RANK["NEEDS_OFFICIAL_SURVEY"] == _RANK["CONDITIONAL"] == 2
    # 기존 등급 값은 그대로.
    assert _RANK["POSSIBLE"] == 0 and _RANK["BLOCKED"] == 4 and _RANK["PRECONDITION"] == 3


# ──────────────────────────────────────────────────────────────────────────
# 2차 수정(E1 회귀) 검증 — 하드코딩 개발가능성 튜플이 NEEDS_OFFICIAL_SURVEY를 놓쳐,
#   임야 필지(resolvable="YES")에 "개발 가능합니다"/"표준 절차로 해결 가능" 안심 문구가
#   붙던 회귀를 막는다. caveat·honest·다필지 disclosure가 SSOT 멤버십으로 판정되는지 확인.
#   (아래 테스트들은 수정 前 코드에선 실패한다: 약한 else 문구에 "가능합니다"가 들어갔으므로.)
# ──────────────────────────────────────────────────────────────────────────


def test_detect_special_parcel_forest_caveat_honest_are_tentative():
    """단일 임야 필지 → development_caveat·honest_disclosure가 '개발 가능합니다'로 오고지되지 않고,
    '확정 아님/참고/공식 산림조사 필요' 정직 문구를 담는다(레드팀 지적 회귀 차단)."""
    r = detect_special_parcel({"land_category": "임야", "zone_type": "계획관리지역"})
    assert r is not None
    assert r["developability"] == "NEEDS_OFFICIAL_SURVEY"
    assert r["resolvable"] == "YES"  # 임야는 resolvable=YES라 하드코딩 else로 새던 지점.
    caveat = r["development_caveat"]
    honest = r["honest_disclosure"]
    # 안심 문구 금지: "가능합니다"가 들어가면 게이트(참고안)와 모순.
    assert "가능합니다" not in caveat, f"caveat가 여전히 '가능합니다'를 포함: {caveat}"
    assert "가능합니다" not in honest, f"honest가 여전히 '가능합니다'를 포함: {honest}"
    # 정직-실패 마커 포함(확정 아님 / 참고 / 공식).
    assert any(m in caveat for m in _HONEST_SURVEY_MARKERS), caveat
    assert any(m in honest for m in _HONEST_SURVEY_MARKERS), honest
    # 산림 특화 정직 문구가 실제로 실려 있는지(공식 산림데이터·산림조사서).
    assert "산림조사서" in honest and "공식 산림데이터" in honest


def test_detect_special_parcel_conditional_not_regressed():
    """대조군: 농지(CONDITIONAL 성격, resolvable=YES) 등 다른 특이 케이스는 여전히 잠정
    정직 문구를 받아야 한다(2차 수정이 기존 케이스를 퇴행시키지 않음)."""
    r = detect_special_parcel({"land_category": "답", "zone_type": "계획관리지역"})
    if r is not None:  # 농지 규칙이 감지되면
        honest = r["honest_disclosure"]
        # 잠정 등급이면 '확정 아님/잠재/조건' 톤이 유지되고 안심 단정이 없어야 한다.
        if r["developability"] in GATE_TENTATIVE_DEVELOPABILITY:
            assert "가능합니다" not in honest, honest


def test_detect_multi_parcel_forest_disclosure_is_tentative():
    """다필지 세트에 임야가 섞이면(임야는 resolvable=YES) 사업 게이트가 잠정으로 남고,
    disclosure가 '표준 절차로 해결 가능'이 아니라 '확정 아님·공식조사' 정직 고지를 준다."""
    m = detect_multi_parcel([
        {"land_category": "임야", "zone_type": "계획관리지역"},
        {"land_category": "대", "zone_type": "제2종일반주거지역"},
    ])
    assert m["developability"] == "NEEDS_OFFICIAL_SURVEY"
    disclosure = m["honest_disclosure"]
    assert "해결 가능" not in disclosure, f"다필지 disclosure가 여전히 '해결 가능': {disclosure}"
    assert any(mk in disclosure for mk in _HONEST_SURVEY_MARKERS), disclosure
    # 권고에 공식 산림데이터 확보 안내가 실려야 한다.
    assert "산림조사서" in m["recommendation"] or "공식 산림데이터" in m["recommendation"]


def test_scenario_gate_membership_surfaces_forest_disclosure():
    """scenario_simulator(라인~333)의 게이트 판정 재현 — 임야 special_gate가 SSOT 멤버십
    (GATE_TENTATIVE_DEVELOPABILITY)에 걸려 최상위 honest_disclosure가 노출돼야 한다.
    수정 前 하드코딩 튜플('CONDITIONAL','PRECONDITION','CAUTION')은 이를 놓쳐 노출 안 됐다."""
    sg = detect_special_parcel({"land_category": "임야", "zone_type": "계획관리지역"})
    dev = sg.get("developability")
    # 2차 수정된 노출 조건(SSOT 멤버십 + CAUTION).
    surfaces = bool(sg and (dev in GATE_TENTATIVE_DEVELOPABILITY or dev == "CAUTION"))
    assert surfaces, f"임야 게이트가 최상위 disclosure를 노출하지 못함: developability={dev}"
    # 수정 前 하드코딩 튜플이었다면 놓쳤을 것(회귀 근거).
    assert dev not in ("CONDITIONAL", "PRECONDITION", "CAUTION"), (
        "이 테스트는 NEEDS_OFFICIAL_SURVEY가 옛 튜플에 없었음을 전제로 한다"
    )
    # 노출되는 disclosure가 정직-실패 문구인지.
    assert any(mk in sg["honest_disclosure"] for mk in _HONEST_SURVEY_MARKERS)
