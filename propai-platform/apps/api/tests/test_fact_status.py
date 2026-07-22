"""Fact 상태 어휘 계약 테스트 (W2-1) — 7상태·정규화·전이규칙(DB 불요, 순수 함수)."""
from __future__ import annotations

from app.services.provenance import fact_status as fs


def test_valid_statuses_are_exactly_7():
    assert len(fs.VALID_FACT_STATUSES) == 7
    assert {
        "OBSERVED", "DERIVED", "ASSUMED", "INFERRED", "CONFLICT", "UNKNOWN", "STALE",
    } == fs.VALID_FACT_STATUSES


def test_fact_status_enum_values_match():
    assert fs.FactStatus.OBSERVED == "OBSERVED"
    assert fs.FactStatus.UNKNOWN == "UNKNOWN"
    assert fs.FactStatus.CONFLICT == "CONFLICT"


def test_normalize_fact_status_none_and_blank_return_none():
    assert fs.normalize_fact_status(None) is None
    assert fs.normalize_fact_status("") is None
    assert fs.normalize_fact_status("   ") is None


def test_normalize_fact_status_trims_and_uppercases():
    assert fs.normalize_fact_status("  observed ") == "OBSERVED"
    assert fs.normalize_fact_status("stale") == "STALE"


def test_is_valid_fact_status_true_for_known_values():
    assert fs.is_valid_fact_status("OBSERVED") is True
    assert fs.is_valid_fact_status("observed") is True  # 대소문자 무관


def test_is_valid_fact_status_false_for_unknown_token():
    assert fs.is_valid_fact_status("BOGUS") is False
    assert fs.is_valid_fact_status(None) is False


def test_can_transition_unknown_to_observed_allowed():
    ok, _ = fs.can_transition_fact("UNKNOWN", "OBSERVED")
    assert ok is True


def test_can_transition_unknown_to_assumed_allowed():
    ok, _ = fs.can_transition_fact("UNKNOWN", "ASSUMED")
    assert ok is True


def test_can_transition_conflict_to_unknown_rejected():
    # ★불변식: CONFLICT를 조용히 UNKNOWN으로 되돌리는 경로는 계약 위반 — 거부되어야 한다.
    ok, reason = fs.can_transition_fact("CONFLICT", "UNKNOWN")
    assert ok is False
    assert "허용되지 않은" in reason


def test_can_transition_assumed_directly_to_conflict_rejected():
    # 전이표에 없는 경로(ASSUMED→CONFLICT)는 거부된다.
    ok, _ = fs.can_transition_fact("ASSUMED", "CONFLICT")
    assert ok is False


def test_can_transition_initial_none_allows_any_valid_target():
    ok, _ = fs.can_transition_fact(None, "ASSUMED")
    assert ok is True
    ok2, _ = fs.can_transition_fact(None, "OBSERVED")
    assert ok2 is True


def test_can_transition_invalid_target_rejected():
    ok, reason = fs.can_transition_fact("OBSERVED", "BOGUS")
    assert ok is False
    assert "유효하지 않은 목표" in reason


def test_can_transition_invalid_current_rejected():
    ok, reason = fs.can_transition_fact("BOGUS", "OBSERVED")
    assert ok is False
    assert "유효하지 않은 현재" in reason


def test_can_transition_same_state_is_noop_allowed():
    ok, _ = fs.can_transition_fact("STALE", "STALE")
    assert ok is True


def test_can_transition_stale_back_to_observed_allowed():
    # 재수집으로 신선도 회복 — 허용.
    ok, _ = fs.can_transition_fact("STALE", "OBSERVED")
    assert ok is True


def test_can_transition_observed_to_assumed_rejected():
    # 실측값을 임의로 가정값으로 되돌리는 경로는 규칙에 없다(거부).
    ok, _ = fs.can_transition_fact("OBSERVED", "ASSUMED")
    assert ok is False
