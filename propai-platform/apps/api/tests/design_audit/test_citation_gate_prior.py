"""Phase 1: citation_gate가 prior_evidence의 수치를 grounded로 인정(치환 안 함)."""
from app.services.design_audit.blindspot_interpreter import citation_gate


def test_prior_number_is_grounded_not_gated():
    # findings엔 없지만 prior 원장엔 있는 수치(250.0)를 인용하면, prior_evidence 합류 시 치환되지 않아야.
    items = [{"claim": "용적률이 250.0%로 한도를 초과합니다", "basis": "FAR-01", "confidence": "high"}]
    findings = [{"check_id": "FAR-01", "status": "fail"}]  # 수치 없음
    prior = {"payload": {"findings_brief": [{"check_id": "FAR-01", "current": 250.0, "limit": 200.0}]}}

    without = citation_gate(items, findings, None)
    with_prior = citation_gate(items, findings, None, prior_evidence=prior)

    # prior 없으면 250.0이 미근거로 치환(gated)
    assert without[0]["citation_gate"]["gated"] is True
    # prior 합류 시 grounded → 치환 안 됨
    assert with_prior[0]["citation_gate"]["gated"] is False
    assert "250" in with_prior[0]["claim"]


def test_backward_compatible_two_three_args():
    items = [{"claim": "면적 검토", "basis": "AREA-01", "confidence": "medium"}]
    findings = [{"check_id": "AREA-01", "status": "pass"}]
    # 기존 2~3인자 호출 무변동(prior_evidence 기본 None)
    assert citation_gate(items, findings) == citation_gate(items, findings, None)
