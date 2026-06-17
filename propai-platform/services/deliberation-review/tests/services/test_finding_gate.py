"""AT-6 — 합성 신뢰도 임계 미달 → NEEDS_REVIEW 분리(단정 금지)."""
from app.contracts.finding import Finding, GatedStatus, Verdict
from app.core.parameters import param
from app.services.gate.finding_gate import FindingGate

LOW_CONF_FINDING = Finding(rule_id="far_limit", verdict=Verdict.COMPLIANT, composite_confidence=0.4)
HIGH_CONF_FINDING = Finding(rule_id="far_limit", verdict=Verdict.COMPLIANT, composite_confidence=0.95)


def test_low_composite_confidence_gated():
    gate = FindingGate(threshold=param("finding_confidence_threshold"))
    f = gate.apply(LOW_CONF_FINDING)
    assert f.gated_status == GatedStatus.NEEDS_REVIEW


def test_high_confidence_confirmed():
    gate = FindingGate(threshold=param("finding_confidence_threshold"))
    f = gate.apply(HIGH_CONF_FINDING)
    assert f.gated_status == GatedStatus.CONFIRMED


def test_conflict_flag_forces_review():
    gate = FindingGate(threshold=param("finding_confidence_threshold"))
    finding = Finding(rule_id="r", verdict=Verdict.COMPLIANT, composite_confidence=0.99, conflicts=["x"])
    assert gate.apply(finding).gated_status == GatedStatus.NEEDS_REVIEW


def test_finding_defaults_to_needs_review_until_gated():
    # 게이트 전 finding은 확정 아님(무음 오통과 금지, INV-18).
    f = Finding(rule_id="r", verdict=Verdict.COMPLIANT, composite_confidence=0.99)
    assert f.gated_status == GatedStatus.NEEDS_REVIEW
