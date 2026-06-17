"""AT-7 — ledger 충돌 플래그 → composite 하향 반영."""
from app.services.gate.confidence_composer import ConfidenceComposer

INPUTS = [0.9, 0.85, 0.8]


def test_conflict_flag_lowers_composite():
    composer = ConfidenceComposer()
    with_conflict = composer.compose(INPUTS, conflicts=["area_mismatch"])
    without_conflict = composer.compose(INPUTS)
    assert with_conflict < without_conflict


def test_hard_gate_min_rule_caps():
    composer = ConfidenceComposer()
    capped = composer.compose([0.9, 0.9], hard_gates=[0.3])
    assert capped <= 0.3
