"""Phase 2 T1 — 결정론 모순 탐지기(contradiction.py) 단위테스트(무 DB).

순수 함수만 검증: status 플립·수치 델타·추출·집계. DB·LLM 비의존.
"""
from app.services.ledger import contradiction as C


def test_status_flip_pass_to_fail_is_high():
    flips = C.detect_status_flips({"far": "pass"}, {"far": "fail"})
    assert flips == [{"kind": "status_flip", "key": "far",
                      "prev": "pass", "now": "fail", "severity": "high"}]


def test_status_flip_pass_to_warning_is_medium():
    flips = C.detect_status_flips({"a": "적합"}, {"a": "조건부적합"})
    assert flips[0]["severity"] == "medium"


def test_status_improvement_is_low_but_flagged():
    flips = C.detect_status_flips({"a": "fail"}, {"a": "pass"})
    assert flips[0]["severity"] == "low"


def test_status_unchanged_not_flagged():
    assert C.detect_status_flips({"a": "pass"}, {"a": "pass"}) == []


def test_numeric_delta_relative_thresholds():
    out = C.detect_numeric_deltas({"x": 100.0, "y": 100.0, "z": 100.0},
                                  {"x": 121.0, "y": 111.0, "z": 105.0},
                                  rel_threshold=0.10)
    sev = {d["key"]: d["severity"] for d in out}
    assert sev["x"] == "high" and sev["y"] == "medium"   # z(5%)는 임계 미만 → 제외
    assert "z" not in sev


def test_numeric_abs_threshold_for_rate():
    # profit_rate 5%p 절대임계 — 상대변화는 작아도 절대 변화로 플래그
    out = C.detect_numeric_deltas({"profit_rate": 18.0}, {"profit_rate": 12.0},
                                  rel_threshold=0.50, abs_thresholds={"profit_rate": 5.0})
    assert out and out[0]["key"] == "profit_rate"


def test_extract_status_from_findings_brief():
    payload = {"findings_brief": [{"check_id": "far", "status": "fail"}],
               "verdict": "부적합"}
    st = C.extract_status(payload)
    assert st["far"] == "fail" and st["__verdict__"] == "부적합"


def test_extract_numbers_flattens_paths_skipping_bools():
    nums = C.extract_numbers({"a": 1, "b": {"c": 2.5}, "ok": True, "lst": [10, 20]})
    assert nums == {"a": 1.0, "b.c": 2.5, "lst[0]": 10.0, "lst[1]": 20.0}


def test_detect_contradictions_aggregates_and_summarizes():
    prior = {"payload": {"findings_brief": [{"check_id": "far", "status": "pass"}],
                         "profit_rate": 20.0}}
    current = {"payload": {"findings_brief": [{"check_id": "far", "status": "fail"}],
                           "profit_rate": 10.0}}
    res = C.detect_contradictions(prior, current, rel_threshold=0.10)
    assert res["has_contradiction"] is True
    assert res["max_severity"] == "high"
    keys = {c["key"] for c in res["contradictions"]}
    assert "far" in keys and "profit_rate" in keys


def test_detect_contradictions_empty_when_no_prior():
    assert C.detect_contradictions(None, {"payload": {"x": 1}})["has_contradiction"] is False


def test_group_normalizes_array_index_to_star():
    assert C._normalize_key("upzoning.scenarios[0].expected_far_pct_low") == \
        "upzoning.scenarios[*].expected_far_pct_low"
    assert C._normalize_key("upzoning.scenarios[12].far") == "upzoning.scenarios[*].far"
    assert C._normalize_key("a.b.c") == "a.b.c"  # 인덱스 없는 키는 그대로


def test_groups_collapse_scenario_array_leaves():
    """★표시 폭발 해소: scenarios[0..9] 20개 leaf(각 필드 10개씩)가 그룹 2개로 압축된다."""
    scenarios_prior = [
        {"expected_far_pct_low": 100.0, "expected_far_pct_high": 150.0} for _ in range(10)
    ]
    scenarios_current = [
        {"expected_far_pct_low": 200.0, "expected_far_pct_high": 300.0} for _ in range(10)
    ]
    prior = {"payload": {"upzoning": {"scenarios": scenarios_prior}}}
    current = {"payload": {"upzoning": {"scenarios": scenarios_current}}}
    res = C.detect_contradictions(prior, current, rel_threshold=0.10)

    # 기존 leaf 단위 배열은 그대로 20건(하위호환 — 국소패치 없이 additive만 추가).
    assert len(res["contradictions"]) == 20
    # 그룹은 필드 패턴별 1~2개로 압축된다(같은 자리+같은 변화폭이므로 묶임).
    assert 1 <= len(res["groups"]) <= 2
    for g in res["groups"]:
        assert g["leaf_count"] == 10
        assert g["key_pattern"].endswith("expected_far_pct_low") or \
            g["key_pattern"].endswith("expected_far_pct_high")
        assert "[*]" in g["key_pattern"]
        assert len(g["sample_keys"]) <= 3
    assert res["group_counts"]["high"] + res["group_counts"]["medium"] + res["group_counts"]["low"] \
        == len(res["groups"])
    assert res["max_severity_by_group"] in ("high", "medium", "low")


def test_groups_keep_distinct_values_separate():
    """서로 다른 prev/now(진짜 다른 leaf)는 그룹이 합쳐지지 않는다(무손실 압축)."""
    prior = {"payload": {"scenarios": [{"far": 100.0}, {"far": 120.0}]}}
    current = {"payload": {"scenarios": [{"far": 200.0}, {"far": 260.0}]}}
    res = C.detect_contradictions(prior, current, rel_threshold=0.10)
    assert len(res["contradictions"]) == 2
    assert len(res["groups"]) == 2  # 값이 다르므로 묶이지 않음
    assert all(g["leaf_count"] == 1 for g in res["groups"])


def test_groups_empty_when_no_contradictions():
    res = C.detect_contradictions(None, {"payload": {"x": 1}})
    assert res["groups"] == []
    assert res["group_counts"] == {"low": 0, "medium": 0, "high": 0}
    assert res["max_severity_by_group"] is None


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
