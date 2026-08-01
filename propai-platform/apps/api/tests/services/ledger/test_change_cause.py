"""변경 원인 분류 계약 잠금 — 라이브에서 실제로 오표기된 사례를 회귀락으로 박제한다.

★골든의 출처(중요): 아래 시나리오는 만들어낸 예시가 아니라 2026-08-01 프로덕션 화면에서
"이전 분석과 모순 감지 / 최고 심각도 HIGH"로 잘못 표시된 실제 4건이다
(effective_far.parcel_count 3→2 · zone_mix area · land_area_sqm 176458→152826 ·
location.education.school_count 5→1). 넷 다 진짜 모순이 아니었다.
"""

from __future__ import annotations

from app.services.ledger.change_cause import (
    CAUSE_INPUT_CHANGED,
    CAUSE_NONE,
    CAUSE_UNEXPLAINED,
    CAUSE_VERSION_CHANGED,
    classify_change_cause,
    diff_signature,
)
from app.services.ledger.contradiction import detect_contradictions


def _payload(*, parcel_count: int, land_area: float, schools: int,
             address: str = "경북 포항시 남구 호미곶면 대보리 산1-1",
             pnu: str = "4711135022200010001", schema: str = "site_analysis/v1"):
    """라이브 wb_payload 형태 — signature_parts 순서는 build_signature_parts 계약과 동일."""
    return {
        "kind": "site_analysis", "schema_version": schema,
        "land_area_sqm": land_area,
        "effective_far": {"parcel_count": parcel_count, "effective_far_pct": 80.0},
        "location": {"education": {"school_count": schools}},
        "signature_parts": [address, pnu, str(parcel_count), "False", ""],
    }


# ── 라이브 오표기 재현: 필지 3→2 재선택 ──────────────────────────────────────

def test_live_case_parcel_reselect_is_input_changed_not_contradiction():
    """★라이브 회귀: 필지를 3개→2개로 다시 고른 것은 '모순'이 아니라 '입력 변경'이다."""
    prior = _payload(parcel_count=3, land_area=176458, schools=5)
    current = _payload(parcel_count=2, land_area=152826, schools=1)

    out = detect_contradictions(prior, current)

    # 값 차이 자체는 여전히 검출된다(비교 기능은 보존 — 탐지를 없앤 게 아니다).
    assert out["has_contradiction"] is True
    cause = out["change_cause"]
    assert cause["cause"] == CAUSE_INPUT_CHANGED
    # ★핵심 계약: 확인 필요 아님 → 경고색·경보 억제의 근거.
    assert out["needs_review"] is False
    assert cause["needs_review"] is False
    assert cause["comparable"] is False
    # 달라진 입력 항목을 사람이 읽을 수 있게 지목한다.
    labels = [d["label"] for d in cause["changed_inputs"]]
    assert "선택 필지 수" in labels
    assert "3" in cause["reason"] and "2" in cause["reason"]


def test_input_changed_never_claims_which_is_correct():
    """★정직 계약: 입력이 다르면 우열을 말하지 않는다(어느 쪽이 '틀렸다'고 하면 안 됨)."""
    prior = _payload(parcel_count=3, land_area=176458, schools=5)
    current = _payload(parcel_count=2, land_area=152826, schools=1)
    cause = detect_contradictions(prior, current)["change_cause"]
    hint = cause["trust_hint"]
    assert "모두 유효" in hint
    for forbidden in ("틀렸", "오류", "잘못"):
        assert forbidden not in hint, f"입력 변경인데 우열/오류를 단정: {hint}"


# ── 입력 동일 + 값 상이 = 유일하게 확인이 필요한 경우 ────────────────────────

def test_same_input_different_value_is_unexplained_and_needs_review():
    """입력·기준이 같은데 값이 다르면 그때만 확인 필요로 올린다."""
    prior = _payload(parcel_count=2, land_area=152826, schools=1)
    current = _payload(parcel_count=2, land_area=99999, schools=1)

    out = detect_contradictions(prior, current)

    assert out["change_cause"]["cause"] == CAUSE_UNEXPLAINED
    assert out["needs_review"] is True
    assert out["change_cause"]["needs_review"] is True


def test_version_change_marks_latest_as_more_accurate():
    """입력 동일 + 스키마 버전 변경 → 최신이 더 정확하다고 안내."""
    prior = _payload(parcel_count=2, land_area=152826, schools=5, schema="site_analysis/v1")
    current = _payload(parcel_count=2, land_area=152826, schools=1, schema="site_analysis/v2")

    out = detect_contradictions(prior, current)

    assert out["change_cause"]["cause"] == CAUSE_VERSION_CHANGED
    assert out["needs_review"] is False
    assert "최신" in out["change_cause"]["trust_hint"]


def test_no_change_reports_none_cause():
    same = _payload(parcel_count=2, land_area=152826, schools=1)
    out = detect_contradictions(same, dict(same))
    assert out["has_contradiction"] is False
    assert out["change_cause"]["cause"] == CAUSE_NONE
    assert out["needs_review"] is False


# ── 근거 부족을 '이상 없음'으로 삼키지 않는다(무음 낙관 금지) ────────────────

def test_missing_signature_is_not_treated_as_same_input():
    """★구버전 기록(지문 없음)을 '입력 같음'으로 단정하면 안 된다 — 확인 필요로 남긴다."""
    prior = _payload(parcel_count=2, land_area=176458, schools=1)
    prior.pop("signature_parts")
    current = _payload(parcel_count=2, land_area=152826, schools=1)

    out = detect_contradictions(prior, current)

    assert out["change_cause"]["cause"] == CAUSE_UNEXPLAINED
    assert out["needs_review"] is True
    assert "확인할 수 없" in out["change_cause"]["reason"]


def test_diff_signature_returns_none_when_unknown():
    """지문을 못 읽으면 빈 리스트(같음)가 아니라 None(모름)을 낸다 — 이 구분이 위 계약의 근거."""
    known = _payload(parcel_count=2, land_area=1.0, schools=1)
    unknown = dict(known)
    unknown.pop("signature_parts")
    assert diff_signature(known, unknown) is None
    assert diff_signature(known, dict(known)) == []


# ── 스코프 회귀락: 어떤 입력 항목이 달라져도 잡아야 한다 ────────────────────

def test_every_contracted_signature_part_is_compared():
    """★스코프 잠금: 5개 계약 파트(주소·PNU·필지수·LLM·옵션) 중 무엇이 바뀌어도 감지한다.

    한 파트만 비교하도록 좁히는 변이(예: 필지수만 보기)를 잡는다.
    """
    base = ["주소A", "PNU1", "2", "False", ""]
    variants = [
        (0, ["주소B", "PNU1", "2", "False", ""]),
        (1, ["주소A", "PNU2", "2", "False", ""]),
        (2, ["주소A", "PNU1", "3", "False", ""]),
        (3, ["주소A", "PNU1", "2", "True", ""]),
        (4, ["주소A", "PNU1", "2", "False", "opt=1"]),
    ]
    for idx, changed in variants:
        prior = {"signature_parts": base, "land_area_sqm": 100.0}
        current = {"signature_parts": changed, "land_area_sqm": 200.0}
        cause = classify_change_cause(prior, current, has_changes=True)
        assert cause["cause"] == CAUSE_INPUT_CHANGED, f"파트 {idx} 변경을 놓쳤다"
        assert any(d["index"] == idx for d in cause["changed_inputs"])


def test_extra_parts_beyond_contract_are_ignored():
    """idx5+ (호출부 전용 extra_parts)는 비교 제외 — 프론트가 재계산 못 하므로 오발화 방지."""
    prior = {"signature_parts": ["주소A", "PNU1", "2", "False", "", "지문X"], "v": 1.0}
    current = {"signature_parts": ["주소A", "PNU1", "2", "False", "", "지문Y"], "v": 2.0}
    cause = classify_change_cause(prior, current, has_changes=True)
    assert cause["cause"] == CAUSE_UNEXPLAINED, "extra_parts 차이를 입력 변경으로 오판했다"


def test_backward_compatible_keys_preserved():
    """기존 소비처 계약(구버전 프론트)을 깨지 않는다."""
    prior = _payload(parcel_count=3, land_area=176458, schools=5)
    current = _payload(parcel_count=2, land_area=152826, schools=1)
    out = detect_contradictions(prior, current)
    for key in ("contradictions", "counts", "max_severity", "has_contradiction",
                "groups", "group_counts", "max_severity_by_group", "note"):
        assert key in out
