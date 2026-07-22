"""RFI(Request for Information) 루프 계약 테스트 (W3-6, v4.0 스펙 P [RFI 루프] 실용 1차).

검증 축:
 (a) RFIStatus 4종 & VALID_RFI_STATUSES.
 (b) RFISeverity 5종 — RDM RequirementLevel(+critical)에서 파생하는 규칙표.
 (c) can_transition_rfi — 화이트리스트(OPEN→ANSWERED→RESOLVED·OPEN→OVERRIDDEN·
     ANSWERED→OPEN 재개), 불법 전이 거부, 동일상태 재확인 허용.
 (d) RFIItem 유효성 검사 — 잘못된 status/severity 즉시 거부(ValueError).
 (e) RFIRegister — collect/get/by_status/open_items, 동일 rfi_id 재방출 무해화(기존 유지).
 (f) RFIRegister 생명주기 — answer/resolve/override/reopen + 불법 전이 시 RFITransitionError.
 (g) emit_rfi — 1줄 방출 헬퍼(severity 자동 파생, 결정론적 rfi_id).
 (h) to_dict() 안정 직렬화 — item_count/open_count/critical_open_count 집계.
 (i) comprehensive_analysis_service 배선 계약 — _attach_rfi_register가 조례확인필요 마커
     (#422)에서만 RFI를 방출하고, additive로만 동작하며 실패해도 기존 분석 결과를 훼손하지
     않는다(무회귀 — _attach_csm_and_risk_register와 동일 패턴).
"""
from __future__ import annotations

import pytest

from app.services.provenance.required_data import RequirementLevel
from app.services.rfi.rfi_register import (
    VALID_RFI_SEVERITIES,
    VALID_RFI_STATUSES,
    RFIItem,
    RFIRegister,
    RFISeverity,
    RFIStatus,
    RFITransitionError,
    build_subject_ref,
    can_transition_rfi,
    emit_rfi,
    severity_from_requirement_level,
)

# ══════════════════════════════════════════════════════════════════════════
# (a) RFIStatus 4종
# ══════════════════════════════════════════════════════════════════════════


def test_rfi_statuses_are_exactly_4():
    assert {"OPEN", "ANSWERED", "RESOLVED", "OVERRIDDEN"} == VALID_RFI_STATUSES


def test_rfi_severities_are_exactly_5():
    assert {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"} == VALID_RFI_SEVERITIES


# ══════════════════════════════════════════════════════════════════════════
# (b) severity 파생 — RDM RequirementLevel(+critical) → RFISeverity
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("level", "critical", "expected"),
    [
        ("required", True, RFISeverity.CRITICAL.value),
        ("required", False, RFISeverity.HIGH.value),
        ("conditionally_required", True, RFISeverity.CRITICAL.value),
        ("conditionally_required", False, RFISeverity.MEDIUM.value),
        ("recommended", False, RFISeverity.LOW.value),
        ("reference_only", False, RFISeverity.INFO.value),
        # 대소문자 무관 정규화.
        ("REQUIRED", False, RFISeverity.HIGH.value),
    ],
)
def test_severity_from_requirement_level_derivation_table(level, critical, expected):
    assert severity_from_requirement_level(level, critical=critical) == expected


def test_severity_from_requirement_level_rejects_invalid_level():
    with pytest.raises(ValueError, match="requirement_level"):
        severity_from_requirement_level("invalid_level")


def test_severity_reuses_rdm_requirement_level_enum_values():
    # 새 어휘 발명 금지 — RDM RequirementLevel 값 그대로 통과해야 한다.
    for level in RequirementLevel:
        severity_from_requirement_level(level.value)  # 예외 없이 통과


# ══════════════════════════════════════════════════════════════════════════
# (c) can_transition_rfi — 화이트리스트
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("current", "target", "expected_ok"),
    [
        ("OPEN", "ANSWERED", True),
        ("OPEN", "OVERRIDDEN", True),
        ("ANSWERED", "RESOLVED", True),
        ("ANSWERED", "OPEN", True),
        # 불법 전이.
        ("OPEN", "RESOLVED", False),
        ("RESOLVED", "OPEN", False),
        ("OVERRIDDEN", "ANSWERED", False),
        ("ANSWERED", "OVERRIDDEN", False),
        # 종결상태에서 나가는 전이는 전부 불허.
        ("RESOLVED", "ANSWERED", False),
        ("OVERRIDDEN", "OPEN", False),
    ],
)
def test_can_transition_rfi_whitelist(current, target, expected_ok):
    ok, _reason = can_transition_rfi(current, target)
    assert ok is expected_ok


def test_can_transition_rfi_same_state_always_allowed():
    for status in VALID_RFI_STATUSES:
        ok, _ = can_transition_rfi(status, status)
        assert ok is True


def test_can_transition_rfi_rejects_invalid_status_values():
    ok, reason = can_transition_rfi("OPEN", "NOT_A_STATUS")
    assert ok is False
    assert "유효하지 않은" in reason

    ok, reason = can_transition_rfi("NOT_A_STATUS", "OPEN")
    assert ok is False
    assert "유효하지 않은" in reason


def test_can_transition_rfi_case_insensitive():
    ok, _ = can_transition_rfi("open", "answered")
    assert ok is True


# ══════════════════════════════════════════════════════════════════════════
# (d) RFIItem 유효성 검사
# ══════════════════════════════════════════════════════════════════════════


def _make_item(**overrides) -> RFIItem:
    base = dict(
        rfi_id="abc123",
        subject_ref="pnu=1111010100",
        missing_what="지자체 조례 실효 용적률",
        needed_for="실효 용적률 산정",
        blocking_calc="far_tier_service.calc_effective_far",
        default_assumption="법정상한 잠정 적용",
        severity=RFISeverity.HIGH.value,
    )
    base.update(overrides)
    return RFIItem(**base)


def test_rfi_item_rejects_invalid_severity():
    with pytest.raises(ValueError, match="severity"):
        _make_item(severity="not_a_severity")


def test_rfi_item_rejects_invalid_status():
    with pytest.raises(ValueError, match="status"):
        _make_item(status="not_a_status")


def test_rfi_item_default_status_is_open():
    item = _make_item()
    assert item.status == RFIStatus.OPEN.value


def test_rfi_item_to_dict_has_all_stable_keys():
    item = _make_item()
    d = item.to_dict()
    assert set(d.keys()) == {
        "rfi_id", "subject_ref", "missing_what", "needed_for", "blocking_calc",
        "default_assumption", "severity", "status", "created_at", "answer",
        "answered_at", "resolved_at", "override_note",
    }


# ══════════════════════════════════════════════════════════════════════════
# (e) RFIRegister — collect/get/by_status
# ══════════════════════════════════════════════════════════════════════════


def test_register_collect_and_get():
    register = RFIRegister()
    item = _make_item()
    register.collect(item)
    assert register.get("abc123") is item
    assert register.get("no_such_id") is None


def test_register_collect_duplicate_rfi_id_keeps_existing():
    register = RFIRegister()
    first = _make_item(missing_what="첫 방출")
    register.collect(first)
    # 상태를 전이시켜(기록 발생) 재방출이 그 기록을 덮어쓰지 않는지 확인.
    register.answer("abc123", "응답 도착")
    duplicate = _make_item(missing_what="첫 방출")  # 동일 rfi_id
    returned = register.collect(duplicate)
    assert returned.status == RFIStatus.ANSWERED.value  # 기존 상태 보존(덮어쓰기 없음)
    assert len(register.items) == 1


def test_register_by_status_and_open_items():
    register = RFIRegister()
    register.collect(_make_item(rfi_id="a"))
    register.collect(_make_item(rfi_id="b"))
    register.answer("a", "답변")
    assert [it.rfi_id for it in register.open_items] == ["b"]
    assert [it.rfi_id for it in register.by_status("ANSWERED")] == ["a"]


# ══════════════════════════════════════════════════════════════════════════
# (f) RFIRegister 생명주기 — answer/resolve/override/reopen
# ══════════════════════════════════════════════════════════════════════════


def test_full_lifecycle_open_answered_resolved():
    register = RFIRegister()
    register.collect(_make_item())
    answered = register.answer("abc123", "관할청 확인 결과 조례 150%")
    assert answered.status == RFIStatus.ANSWERED.value
    assert answered.answer == "관할청 확인 결과 조례 150%"
    assert answered.answered_at is not None

    resolved = register.resolve("abc123")
    assert resolved.status == RFIStatus.RESOLVED.value
    assert resolved.resolved_at is not None


def test_lifecycle_open_overridden():
    register = RFIRegister()
    register.collect(_make_item())
    overridden = register.override("abc123", note="기한 임박 — 법정상한으로 진행")
    assert overridden.status == RFIStatus.OVERRIDDEN.value
    assert overridden.override_note == "기한 임박 — 법정상한으로 진행"
    assert overridden.resolved_at is not None


def test_lifecycle_answered_reopen():
    register = RFIRegister()
    register.collect(_make_item())
    register.answer("abc123", "불충분한 답변")
    reopened = register.reopen("abc123")
    assert reopened.status == RFIStatus.OPEN.value
    assert reopened.answer is None


def test_illegal_transition_raises_rfi_transition_error():
    register = RFIRegister()
    register.collect(_make_item())
    with pytest.raises(RFITransitionError) as exc_info:
        register.transition("abc123", RFIStatus.RESOLVED.value)  # OPEN → RESOLVED 는 불법
    assert exc_info.value.rfi_id == "abc123"
    assert exc_info.value.current == RFIStatus.OPEN.value
    assert exc_info.value.target == RFIStatus.RESOLVED.value


def test_transition_unknown_rfi_id_raises_key_error():
    register = RFIRegister()
    with pytest.raises(KeyError):
        register.transition("no_such_id", RFIStatus.ANSWERED.value)


def test_terminal_states_reject_further_transitions():
    register = RFIRegister()
    register.collect(_make_item())
    register.override("abc123")
    with pytest.raises(RFITransitionError):
        register.transition("abc123", RFIStatus.OPEN.value)


# ══════════════════════════════════════════════════════════════════════════
# (g) emit_rfi — 1줄 방출 헬퍼
# ══════════════════════════════════════════════════════════════════════════


def test_emit_rfi_derives_severity_and_collects():
    register = RFIRegister()
    item = emit_rfi(
        register,
        subject_ref="pnu=123",
        missing_what="조례 실효 용적률",
        needed_for="실효 용적률 산정",
        blocking_calc="far_tier_service.calc_effective_far",
        default_assumption="법정상한 잠정 적용",
        requirement_level=RequirementLevel.REQUIRED.value,
        critical=False,
    )
    assert item.severity == RFISeverity.HIGH.value
    assert item.status == RFIStatus.OPEN.value
    assert register.get(item.rfi_id) is item


def test_emit_rfi_is_deterministic_for_same_subject_and_gap():
    register = RFIRegister()
    item1 = emit_rfi(
        register, subject_ref="pnu=123", missing_what="조례 실효 용적률",
        needed_for="a", blocking_calc="b", default_assumption="c",
    )
    item2 = emit_rfi(
        register, subject_ref="pnu=123", missing_what="조례 실효 용적률",
        needed_for="different", blocking_calc="different", default_assumption="different",
    )
    # 결정론적 id → 재방출은 register.collect()가 기존 항목을 그대로 반환(중복 누적 없음).
    assert item1.rfi_id == item2.rfi_id
    assert len(register.items) == 1
    assert item2.needed_for == "a"  # 최초 방출 내용 보존


def test_build_subject_ref_prefers_pnu_over_address():
    ref = build_subject_ref(pnu="123", address="서울시 종로구", field_name="far")
    assert ref == "pnu=123|field=far"


def test_build_subject_ref_falls_back_to_unknown():
    assert build_subject_ref() == "unknown"


# ══════════════════════════════════════════════════════════════════════════
# (h) to_dict() 안정 직렬화
# ══════════════════════════════════════════════════════════════════════════


def test_register_to_dict_stable_aggregate_counts():
    register = RFIRegister()
    emit_rfi(
        register, subject_ref="s1", missing_what="m1", needed_for="n", blocking_calc="b",
        default_assumption="d", requirement_level="required", critical=True,
    )
    emit_rfi(
        register, subject_ref="s2", missing_what="m2", needed_for="n", blocking_calc="b",
        default_assumption="d", requirement_level="required", critical=False,
    )
    d = register.to_dict()
    assert d["item_count"] == 2
    assert d["open_count"] == 2
    assert d["critical_open_count"] == 1
    assert len(d["items"]) == 2
    assert set(d.keys()) == {
        "items", "generated_at", "item_count", "open_count", "critical_open_count",
    }


# ══════════════════════════════════════════════════════════════════════════
# (i) comprehensive_analysis_service 배선 — additive + 무회귀
# ══════════════════════════════════════════════════════════════════════════

_BASE_RESULT: dict = {
    "pnu": "1111010100100010000",
    "address": "서울특별시 종로구 세종로 1",
    "zone_type": "제2종일반주거지역",
    "effective_far": {
        "national_far_pct": 200.0, "national_bcr_pct": 60.0,
        "ordinance_far_pct": 200.0, "ordinance_bcr_pct": 60.0,
        "effective_far_pct": 200.0, "effective_bcr_pct": 60.0,
        "ordinance_confirmed": True,
        "far_basis_detail": {"조례확인필요": False},
    },
}


def _clone_result(**overrides) -> dict:
    data = {k: (dict(v) if isinstance(v, dict) else v) for k, v in _BASE_RESULT.items()}
    data.update(overrides)
    return data


def test_wiring_emits_rfi_when_ordinance_unconfirmed_marker_present():
    from app.services.land_intelligence.comprehensive_analysis_service import (
        _attach_rfi_register,
    )

    result = _clone_result(effective_far={
        "national_far_pct": 100.0, "national_bcr_pct": 20.0,
        "ordinance_far_pct": 100.0, "ordinance_bcr_pct": 20.0,
        "effective_far_pct": 100.0, "effective_bcr_pct": 20.0,
        "ordinance_confirmed": False,
        "far_basis_detail": {"조례확인필요": True},
    })
    existing_keys = set(result.keys())
    _attach_rfi_register(result)

    assert "rfi_register" in result
    reg = result["rfi_register"]
    assert reg["item_count"] == 1
    assert reg["open_count"] == 1
    assert reg["items"][0]["severity"] == RFISeverity.HIGH.value
    assert reg["items"][0]["status"] == RFIStatus.OPEN.value
    assert "pnu=" in reg["items"][0]["subject_ref"]
    # 기존 키는 전혀 제거/변경되지 않는다(additive — rfi_register 1개만 늘어난다).
    assert existing_keys.issubset(result.keys())
    assert result["zone_type"] == _BASE_RESULT["zone_type"]


def test_wiring_no_rfi_when_ordinance_confirmed():
    from app.services.land_intelligence.comprehensive_analysis_service import (
        _attach_rfi_register,
    )

    result = _clone_result()  # 기본값: ordinance_confirmed=True, 조례확인필요=False
    _attach_rfi_register(result)
    assert result["rfi_register"]["item_count"] == 0
    assert result["rfi_register"]["open_count"] == 0


def test_wiring_tolerates_malformed_effective_far_with_zero_emission():
    """effective_far가 dict가 아닌 기형 입력 — 크래시 없이 방출 0건으로 degrade."""
    from app.services.land_intelligence.comprehensive_analysis_service import (
        _attach_rfi_register,
    )

    result: dict = {"address": "테스트", "effective_far": "not_a_dict"}
    _attach_rfi_register(result)  # 예외를 던지지 않아야 한다
    assert result["address"] == "테스트"  # 기존 값 무손상
    assert result["rfi_register"]["item_count"] == 0


def test_wiring_failure_does_not_raise_and_leaves_result_untouched(monkeypatch):
    """emit_rfi 자체가 예외를 던지는 극단 상황 — additive 키가 아예 부착되지 않아야 한다
    (CSM/Risk Register 배선 테스트의 순환참조 강제실패와 동일한 degrade 검증 패턴)."""
    import app.services.rfi.rfi_register as rfi_register_module
    from app.services.land_intelligence.comprehensive_analysis_service import (
        _attach_rfi_register,
    )

    def _boom(*args, **kwargs):
        raise RuntimeError("강제 실패")

    monkeypatch.setattr(rfi_register_module, "emit_rfi", _boom)

    result = _clone_result(effective_far={
        "national_far_pct": 100.0, "far_basis_detail": {"조례확인필요": True},
        "ordinance_confirmed": False,
    })
    _attach_rfi_register(result)  # 예외를 던지지 않아야 한다(degrade 로그만)
    assert result["address"] == _BASE_RESULT["address"]  # 기존 값 무손상
    assert "rfi_register" not in result  # 실패 시 additive 키는 부착되지 않는다
