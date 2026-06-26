"""C2R Think-Before 게이팅 테스트 — success_criteria 부재·인벨로프 모순 차단(결정론)."""

from app.services.c2r.think_before import evaluate


def _valid_brief() -> dict:
    return {
        "envelope_constraints": {
            "building_coverage_ratio_pct": {"value": 60},
            "floor_area_ratio_pct": {"value": 250},
            "max_floors": {"value": 7},
        },
        "program": {"target_floors": 6},
        "success_criteria": ["건폐율 표기 일치", "대지경계 보존"],
    }


def test_proceed_true_on_valid_brief():
    gate = evaluate(_valid_brief())
    assert gate["proceed"] is True
    assert gate["ambiguous"] is False
    assert gate["open_questions"] == []
    assert gate["missing_criteria"] == []


def test_proceed_false_when_success_criteria_empty():
    """success_criteria 비면 목표 미정의 → proceed False, ambiguous True."""
    brief = _valid_brief()
    brief["success_criteria"] = []
    gate = evaluate(brief)
    assert gate["proceed"] is False
    assert gate["ambiguous"] is True
    assert "success_criteria" in gate["missing_criteria"]


def test_proceed_false_when_constraints_missing():
    """건폐율·용적률 모두 미확보(None) → 근거 부재로 명료화 질문·차단."""
    brief = _valid_brief()
    brief["envelope_constraints"] = {
        "building_coverage_ratio_pct": {"value": None},
        "floor_area_ratio_pct": {"value": None},
    }
    gate = evaluate(brief)
    assert gate["proceed"] is False
    assert "building_coverage_ratio_pct" in gate["missing_criteria"]
    assert "floor_area_ratio_pct" in gate["missing_criteria"]
    assert len(gate["open_questions"]) >= 1


def test_proceed_false_when_mass_exceeds_envelope():
    """매스(목표 층수)가 인벨로프 권장 상한 초과 → 모순으로 차단."""
    brief = _valid_brief()
    brief["program"]["target_floors"] = 12  # max_floors=7 초과
    gate = evaluate(brief)
    assert gate["proceed"] is False
    assert gate["ambiguous"] is True
    assert any("초과" in q for q in gate["open_questions"])


def test_evaluate_is_deterministic():
    brief = _valid_brief()
    assert evaluate(brief) == evaluate(brief)
