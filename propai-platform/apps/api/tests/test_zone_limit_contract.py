"""공용 fail-closed 용도지역 한도계약 검증 — 확정/추정 분리·무근거폴백 차단."""

from app.services.zoning.zone_limit_contract import resolve_zone_limits


def test_confirmed_zone_returns_legal_limits():
    """인식되는 용도지역 → matched=True·확정 한도·법령키 부착."""
    r = resolve_zone_limits("제2종일반주거지역")
    assert r.matched is True
    assert r.confidence == "confirmed"
    assert r.max_far_pct is not None and r.max_far_pct > 0
    assert r.max_bcr_pct is not None and r.max_bcr_pct > 0
    assert "far_limit" in r.legal_ref_keys and "bcr_limit" in r.legal_ref_keys
    assert r.is_fallback is False


def test_empty_zone_is_fail_closed():
    """빈 zone → ★확정 한도 None(무근거 무경고 폴백 차단)·추정값은 opt-in·사유 명시."""
    for empty in ("", "   ", None):
        r = resolve_zone_limits(empty)
        assert r.matched is False
        assert r.confidence == "fallback"
        assert r.max_far_pct is None, "fail-closed: 확정 한도가 새면 안 됨"
        assert r.max_bcr_pct is None
        assert r.estimated_far_pct is not None  # 추정은 opt-in으로만 제공
        assert r.fallback_reason and "미입력" in r.fallback_reason
        assert r.legal_ref_keys == []
        assert r.is_fallback is True


def test_unrecognized_zone_is_fail_closed():
    """미인식 zone(오타/임의문자) → 서브스트링 버그 없이 fail-closed·사유에 입력값 표기."""
    r = resolve_zone_limits("알 수 없는 용도지역XYZ")
    assert r.matched is False
    assert r.max_far_pct is None  # 250% 무근거 폴백이 새지 않음
    assert r.fallback_reason and "미인식" in r.fallback_reason


def test_substring_false_confirm_blocked():
    """★서브스트링 false-confirm 차단(근본A 핵심): 짧은 조각이 confirmed 한도를 받으면 안 됨.

    위임 출처 normalize_zone_name은 양방향 부분문자열 매칭이라 '역'·'주거'·'지역'이 임의
    용도지역으로 매칭된다. 계약의 _is_spurious_match 가드가 이를 fail-closed로 강등해야 한다.
    """
    for fragment in ("역", "주거", "지역", "전용", "상업"):
        r = resolve_zone_limits(fragment)
        assert r.matched is False, f"'{fragment}' 가 confirmed로 오매칭됨(가드 실패)"
        assert r.max_far_pct is None, f"'{fragment}' 에 확정 한도가 새면 안 됨"
        assert r.confidence == "fallback"


def test_effective_override_is_authoritative():
    """실효 far/bcr 권위 입력 → 확정으로 우선(법정표보다 입력 실효값 우선)."""
    r = resolve_zone_limits("제2종일반주거지역", far_override_pct=200.0, bcr_override_pct=60.0)
    assert r.matched is True
    assert r.confidence == "confirmed"
    assert r.max_far_pct == 200.0
    assert r.max_bcr_pct == 60.0


def test_override_with_unknown_zone_still_confirmed():
    """zone 미인식이어도 실효 입력이 있으면 그 값으로 확정(입력이 권위)."""
    r = resolve_zone_limits(None, far_override_pct=250.0)
    assert r.matched is True
    assert r.max_far_pct == 250.0


def test_partial_override_unknown_zone_no_phantom_legal_ref():
    """부분 override(far만)+미인식 zone → far만 확정·bcr None·far 근거만 부착(값없는 근거 금지)."""
    r = resolve_zone_limits("미인식XYZ", far_override_pct=250.0)
    assert r.matched is True
    assert r.max_far_pct == 250.0
    assert r.max_bcr_pct is None            # 보완할 법정표 없음 → None(소비자 null-check)
    assert "far_limit" in r.legal_ref_keys
    assert "bcr_limit" not in r.legal_ref_keys  # 값 없는 한도에 근거 안 붙음
    assert "zone_use" not in r.legal_ref_keys   # 미인식 zone → 용도 근거 없음
