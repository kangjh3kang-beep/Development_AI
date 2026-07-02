"""Phase 2 T1 — 결정론 모순 탐지기(contradiction.py) 단위테스트(무 DB).

순수 함수만 검증: status 플립·수치 델타·추출·집계. DB·LLM 비의존.
"""
from app.services.ledger import contradiction


def test_status_flip_pass_to_fail_is_high():
    flips = contradiction.detect_status_flips({"far": "pass"}, {"far": "fail"})
    assert flips == [{"kind": "status_flip", "key": "far",
                      "prev": "pass", "now": "fail", "severity": "high"}]


def test_status_flip_pass_to_warning_is_medium():
    flips = contradiction.detect_status_flips({"a": "적합"}, {"a": "조건부적합"})
    assert flips[0]["severity"] == "medium"


def test_status_improvement_is_low_but_flagged():
    flips = contradiction.detect_status_flips({"a": "fail"}, {"a": "pass"})
    assert flips[0]["severity"] == "low"


def test_status_unchanged_not_flagged():
    assert contradiction.detect_status_flips({"a": "pass"}, {"a": "pass"}) == []


def test_numeric_delta_relative_thresholds():
    out = contradiction.detect_numeric_deltas({"x": 100.0, "y": 100.0, "z": 100.0},
                                  {"x": 121.0, "y": 111.0, "z": 105.0},
                                  rel_threshold=0.10)
    sev = {d["key"]: d["severity"] for d in out}
    assert sev["x"] == "high" and sev["y"] == "medium"   # z(5%)는 임계 미만 → 제외
    assert "z" not in sev


def test_numeric_abs_threshold_for_rate():
    # profit_rate 5%p 절대임계 — 상대변화는 작아도 절대 변화로 플래그
    out = contradiction.detect_numeric_deltas({"profit_rate": 18.0}, {"profit_rate": 12.0},
                                  rel_threshold=0.50, abs_thresholds={"profit_rate": 5.0})
    assert out and out[0]["key"] == "profit_rate"


def test_extract_status_from_findings_brief():
    payload = {"findings_brief": [{"check_id": "far", "status": "fail"}],
               "verdict": "부적합"}
    st = contradiction.extract_status(payload)
    assert st["far"] == "fail" and st["__verdict__"] == "부적합"


def test_extract_numbers_flattens_paths_skipping_bools():
    nums = contradiction.extract_numbers({"a": 1, "b": {"c": 2.5}, "ok": True, "lst": [10, 20]})
    assert nums == {"a": 1.0, "b.c": 2.5, "lst[0]": 10.0, "lst[1]": 20.0}


def test_detect_contradictions_aggregates_and_summarizes():
    prior = {"payload": {"findings_brief": [{"check_id": "far", "status": "pass"}],
                         "profit_rate": 20.0}}
    current = {"payload": {"findings_brief": [{"check_id": "far", "status": "fail"}],
                           "profit_rate": 10.0}}
    res = contradiction.detect_contradictions(prior, current, rel_threshold=0.10)
    assert res["has_contradiction"] is True
    assert res["max_severity"] == "high"
    keys = {c["key"] for c in res["contradictions"]}
    assert "far" in keys and "profit_rate" in keys


def test_detect_contradictions_empty_when_no_prior():
    assert contradiction.detect_contradictions(None, {"payload": {"x": 1}})["has_contradiction"] is False


def test_compare_with_prior_adds_contradictions_keeping_status_changes():
    # T3: design_audit seed(_compare_with_prior)에 모순 플래그 additive 합류(기존 키 불변)
    from app.services.design_audit.design_audit_orchestrator import _compare_with_prior
    prior = {"version": 1, "payload": {"verdict": "적합",
             "findings_brief": [{"check_id": "far", "status": "pass"}]}}
    findings = [{"check_id": "far", "status": "fail"}]
    out = _compare_with_prior(prior, findings)
    assert out["status_changes"] == [{"check_id": "far", "prev_status": "pass", "now_status": "fail"}]
    assert out["contradictions"]["has_contradiction"] is True
    assert out["contradictions"]["max_severity"] == "high"
    assert out["prior_verdict"] == "적합"   # 기존 키 불변
