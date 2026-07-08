"""C3 — capture_service.record_fallback 계약 단위테스트(무 DB, in-memory 큐 검사).

healing_rules.py(자가치유 후보 수집)가 구독하는 계약: event_type='fallback', service 컬럼,
payload.kind. ledger_broken은 severity='critical'이어야 원장 변조탐지 브랜치가 잡는다
(healing_rules.py:198~209 실측). 이 테스트는 record_fallback이 그 계약을 정확히 채우는지,
그리고 어떤 예외도 호출경로로 전파하지 않는지(best-effort) 검증한다.
"""
from __future__ import annotations

from app.services.growth import capture_service


def _drain_all() -> list[dict]:
    return capture_service._drain(capture_service.queue_size())


def test_record_fallback_fills_healing_rules_contract():
    _drain_all()  # 다른 테스트가 남긴 잔여 이벤트 정리(격리)
    capture_service.record_fallback("deliberation_engine", "engine_unreachable", reason="engine_url_unset")
    rows = _drain_all()
    assert len(rows) == 1
    row = rows[0]
    assert row["event_type"] == "fallback"
    assert row["service"] == "deliberation_engine"
    assert row["severity"] == "warn"  # 기본값
    assert row["payload"]["kind"] == "engine_unreachable"
    assert row["payload"]["reason"] == "engine_url_unset"


def test_record_fallback_ledger_broken_uses_critical_severity():
    _drain_all()
    capture_service.record_fallback("analysis_ledger", "ledger_broken", severity="critical",
                                    analysis_type="site_analysis", broken_count=2)
    row = _drain_all()[0]
    assert row["severity"] == "critical"
    assert row["payload"] == {"kind": "ledger_broken", "analysis_type": "site_analysis", "broken_count": 2}


def test_record_fallback_swallows_exceptions(monkeypatch):
    """이벤트 수집 실패가 호출경로로 전파되면 안 된다(best-effort — record_event와 동일 계약)."""
    def _boom(*a, **k):
        raise RuntimeError("queue full 시뮬")

    monkeypatch.setattr(capture_service, "record_event", _boom)
    capture_service.record_fallback("x", "y")  # 예외 없이 반환하면 통과
    assert True
