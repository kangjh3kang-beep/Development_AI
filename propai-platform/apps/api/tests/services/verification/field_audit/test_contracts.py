"""field_audit 계약(contracts) 단위테스트 — AuditFinding·AuditReport shape·직렬화."""

import pytest
from pydantic import ValidationError

from app.services.verification.field_audit.contracts import AuditFinding, AuditReport


def test_audit_finding_shape_and_to_dict():
    f = AuditFinding(
        code="G1_PROTECTION_ZONE_RISK_FLOOR",
        severity="P0",
        panel="risk",
        field="risk_level",
        expected="높음",
        observed="낮음",
        rule_id="g1_protection_zone_severity",
        tier="A",
        note="통제보호구역 존재 → 리스크 하한 위반",
    )
    d = f.to_dict()
    assert d == f.model_dump()
    for k in ("code", "severity", "panel", "field", "expected", "observed", "rule_id", "tier", "note"):
        assert k in d
    assert d["severity"] == "P0"
    assert d["tier"] == "A"


def test_audit_finding_optional_note_defaults_none():
    f = AuditFinding(code="C", severity="P2", panel="p", field="fld",
                     rule_id="r", tier="B")
    assert f.note is None
    assert f.expected is None and f.observed is None


def test_audit_finding_rejects_bad_severity_and_tier():
    with pytest.raises(ValidationError):
        AuditFinding(code="C", severity="HIGH", panel="p", field="f", rule_id="r", tier="A")
    with pytest.raises(ValidationError):
        AuditFinding(code="C", severity="P0", panel="p", field="f", rule_id="r", tier="Z")


def test_audit_report_defaults_are_valid_empty():
    r = AuditReport()
    assert r.is_valid is True
    assert r.findings == []
    assert r.metadata == {}
    # ★커버리지 원장 seed — 빈 dict라도 필드 존재(bare "100%" 금지의 자리).
    assert r.coverage == {}
    assert "coverage" in r.to_dict()


def test_report_from_findings_p0_flips_is_valid():
    p2 = AuditFinding(code="c", severity="P2", panel="p", field="f", rule_id="r", tier="B")
    rep = AuditReport.from_findings([p2])
    assert rep.is_valid is True  # P2만 → 비차단

    p0 = AuditFinding(code="c", severity="P0", panel="p", field="f", rule_id="r", tier="A")
    rep2 = AuditReport.from_findings([p0, p2])
    assert rep2.is_valid is False  # P0 존재 → 하드 차단(is_valid=False)
    assert len(rep2.findings) == 2


def test_report_to_dict_is_json_serializable():
    import json

    rep = AuditReport.from_findings(
        [AuditFinding(code="c", severity="P1", panel="p", field="f", rule_id="r", tier="A")],
        metadata={"enabled": True},
        coverage={"denominator_kind": "landattr x decision_var"},
    )
    s = json.dumps(rep.to_dict(), ensure_ascii=False)
    assert "P1" in s
