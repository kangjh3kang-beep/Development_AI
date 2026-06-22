"""verifier_service._emit_growth_issues 단위테스트 — 오류 '유형' 기억(재발방지 데이터원).

capture_service.record_event를 모의해 verify_issue 이벤트의 형태/PII안전/best-effort를 검증.
"""

import json

import app.services.growth.capture_service as cap
from app.services.verification.verifier_service import _emit_growth_issues


def test_emit_growth_issues_records_types(monkeypatch):
    captured: dict = {}

    def _rec(event_type, props):
        captured["event_type"] = event_type
        captured["props"] = props

    monkeypatch.setattr(cap, "record_event", _rec)
    _emit_growth_issues("feasibility", [
        {"type": "수치불일치", "claim": "용적률 200% (강남구 …)", "severity": "high"},
        {"type": "범위위반", "claim": "면적 1000㎡", "severity": "medium"},
    ])
    assert captured["event_type"] == "verify_issue"
    p = captured["props"]
    assert p["service"] == "feasibility" and p["severity"] == "high"
    pl = p["payload"]
    assert pl["analysis_type"] == "feasibility"
    assert pl["issue_types"] == ["수치불일치", "범위위반"]
    assert pl["severities"] == ["high", "medium"]
    assert pl["issue_count"] == 2
    # ★PII 방지: 값/주소가 담긴 자유서술 claim은 적재되지 않음
    assert "강남구" not in json.dumps(pl, ensure_ascii=False)
    assert "claim" not in pl


def test_emit_growth_issues_empty_noop(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(cap, "record_event", lambda *a, **k: calls.__setitem__("n", calls["n"] + 1))
    _emit_growth_issues("market", [])
    assert calls["n"] == 0


def test_emit_growth_issues_severity_rollup(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(cap, "record_event", lambda et, p: captured.update(p=p))
    # high 없으면 medium으로 집계
    _emit_growth_issues("avm", [{"type": "x", "severity": "low"}, {"type": "y", "severity": "medium"}])
    assert captured["p"]["severity"] == "medium"


def test_emit_growth_issues_skips_non_dict_symmetrically(monkeypatch):
    # 비-dict 원소는 types/severities에서 대칭으로 제외(인덱스 정합 유지)
    captured: dict = {}
    monkeypatch.setattr(cap, "record_event", lambda et, p: captured.update(p=p))
    _emit_growth_issues("permit", ["notadict", {"type": "a", "severity": "high"}, 123])
    pl = captured["p"]["payload"]
    assert pl["issue_types"] == ["a"] and pl["severities"] == ["high"]
    assert pl["issue_count"] == 1


def test_emit_growth_issues_caps_payload(monkeypatch):
    # 대량 issues면 유형/심각도 리스트는 50개로 상한, issue_count는 원본 유지
    captured: dict = {}
    monkeypatch.setattr(cap, "record_event", lambda et, p: captured.update(p=p))
    _emit_growth_issues("market", [{"type": "t", "severity": "low"} for _ in range(120)])
    pl = captured["p"]["payload"]
    assert len(pl["issue_types"]) == 50 and len(pl["severities"]) == 50
    assert pl["issue_count"] == 120


def test_emit_growth_issues_never_raises(monkeypatch):
    # record_event가 터져도 호출경로로 전파 안 됨(best-effort·검증 반환 불변)
    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(cap, "record_event", _boom)
    _emit_growth_issues("cost", [{"type": "x", "severity": "high"}])  # 예외 없이 반환되어야 함
