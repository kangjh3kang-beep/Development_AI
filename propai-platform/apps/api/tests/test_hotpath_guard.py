"""★A-3(배선 P1 — 법정초과 경량 가드 확산·G8) 공용 헬퍼 단위 테스트.

app/services/verification/hotpath_guard.py::apply_legal_hotpath_guard는
comprehensive_analysis_service.analyze()의 P0-3 패턴(check_against_legal 경량 배선)을
추출한 공용 헬퍼다. 산식은 check_against_legal 그대로 재사용(복제 0) — 여기서는 래핑
계약(result에 additive 부착·confidence 강등·무해 실패)만 검증한다.
"""
from __future__ import annotations

from app.services.verification.hotpath_guard import apply_legal_hotpath_guard


def test_high_severity_excess_attaches_warnings_and_degrades_confidence():
    """근거 없는 법정초과(자연녹지 법정 100%→139.6%) — integrity_warnings 부착 + confidence 강등.

    값 자체는 클램프하지 않는다(무날조) — result/confidence_target 어디에도 far_pct 변경 없음.
    """
    result: dict = {"effective_far_pct": 139.6}
    confidence_target: dict = {"effective_far_pct": 139.6}

    issues = apply_legal_hotpath_guard(
        result,
        zone_type="자연녹지지역", bcr_pct=35.8, far_pct=139.6,
        regulation_payload={"local_ordinance": {}, "zone_limits": {}},
        plan_payload=None,
        confidence_target=confidence_target,
    )

    assert issues, "법정초과가 적발되지 않음"
    assert any(i["severity"] == "high" for i in issues)
    assert result["integrity_warnings"] == issues
    assert result["effective_far_pct"] == 139.6  # 값 무변경(클램프 금지)
    assert confidence_target["confidence"] == "degraded"
    assert "integrity_warnings" in confidence_target["confidence_note"]


def test_within_legal_limit_no_warning_and_confidence_untouched():
    """법정상한 이내 — integrity_warnings 부착 없음(오탐 방지) + confidence_target 무변경."""
    result: dict = {"effective_far_pct": 100.0}
    confidence_target: dict = {"effective_far_pct": 100.0}

    issues = apply_legal_hotpath_guard(
        result,
        zone_type="자연녹지지역", bcr_pct=20.0, far_pct=100.0,
        regulation_payload={"local_ordinance": {}, "zone_limits": {}},
        confidence_target=confidence_target,
    )

    assert issues == []
    assert "integrity_warnings" not in result
    assert "confidence" not in confidence_target


def test_guard_failure_is_graceful_noop():
    """check_against_legal 호출 자체가 실패해도(예: 예기치 못한 payload 타입) 무해 no-op."""
    result: dict = {"marker": "unchanged"}

    # far_pct에 비교 불가능한 값을 넣어 내부 비교 연산(>)이 TypeError를 유발하게 한다.
    issues = apply_legal_hotpath_guard(
        result,
        zone_type="자연녹지지역", bcr_pct=None, far_pct="not-a-number",  # type: ignore[arg-type]
    )

    assert issues == []
    assert result == {"marker": "unchanged"}, "가드 실패가 기존 result를 손상시킴"
