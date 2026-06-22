"""설명가능성 — final_gate 강등사유 라벨 + cross_validation 출처 ref 보존."""
from app.contracts.cross_validation import SourceValue
from app.contracts.verification import GateItem
from app.services.cross_validate.validator import CrossSourceValidator
from app.services.verify.final_gate import FinalGate


def test_final_gate_reason_labels():
    gate = FinalGate(threshold=0.7)
    # 검증결과 부재 → NEEDS_REVIEW + unverified 사유(무음 강등 금지).
    r1 = gate.apply(GateItem(composite_confidence=0.9, conflicts=[],
                             verification=None, dual_path_status=None))
    assert r1.status.value == "NEEDS_REVIEW" and "unverified" in r1.reason
    # 임계 미달 → below_threshold(값<임계) 명시.
    r2 = gate.apply(GateItem(composite_confidence=0.6, conflicts=[],
                             verification=None, dual_path_status=None))
    assert "below_threshold(0.6<0.7)" in r2.reason
    # 충돌·이중경로 HELD도 사유 누적.
    r3 = gate.apply(GateItem(composite_confidence=0.9, conflicts=["dup"],
                             verification=None, dual_path_status="HELD"))
    assert "conflict" in r3.reason and "dual_path_HELD" in r3.reason


def test_cross_validation_preserves_ref():
    v = CrossSourceValidator()
    vals = [
        SourceValue(source="law_go_kr", value=200, ref="law.go.kr/건축법"),
        SourceValue(source="mirror", value=200, ref="mirror#123"),
    ]
    cv = v.validate("far_limit", vals)
    assert cv.status.value == "UNANIMOUS"
    # 합의값의 출처별 1차출처 ref 보존(역추적 가능).
    refs = {s.source: s.ref for s in cv.sources}
    assert refs["law_go_kr"] == "law.go.kr/건축법" and refs["mirror"] == "mirror#123"
