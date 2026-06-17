"""INC-9 — 비전 N-패스 합의: 만장일치/과반/불일치(결정론 취합가, CrossSourceValidator 재사용)."""
from app.contracts.drawing_extraction import ExtractedElement
from app.services.extraction.vision_consensus import merge_with_consensus


def _el(hint, idx=0, sheet="A"):
    return ExtractedElement(element_id=f"{sheet}-v{idx}", semantic_hint=hint,
                            provenance={"sheet": sheet})


def test_consensus_unanimous():
    out = merge_with_consensus([[_el("PARKING")], [_el("PARKING")], [_el("PARKING")]])
    assert len(out) == 1
    assert out[0].consensus_status == "UNANIMOUS" and out[0].semantic_hint == "PARKING"


def test_consensus_majority_picks_agreed():
    out = merge_with_consensus([[_el("PARKING")], [_el("PARKING")], [_el("BASEMENT")]])
    assert out[0].consensus_status == "MAJORITY"
    assert out[0].semantic_hint == "PARKING"  # 과반 합의값 대표


def test_consensus_conflict_two_way_tie():
    out = merge_with_consensus([[_el("PARKING")], [_el("BASEMENT")]])
    assert out[0].consensus_status == "CONFLICT"  # 동수 → 합의 실패 표면화(무음0)


def test_consensus_single_pass():
    out = merge_with_consensus([[_el("PILOTIS")]])
    assert out[0].consensus_status == "SINGLE"  # 단일 추출가 → 교차검증 불가


def test_consensus_separate_elements_by_key():
    # 서로 다른 순번(키) 요소는 독립 합의.
    out = merge_with_consensus([
        [_el("PARKING", 0), _el("EAVE", 1)],
        [_el("PARKING", 0), _el("EAVE", 1)],
    ])
    assert {e.semantic_hint: e.consensus_status for e in out} == {
        "PARKING": "UNANIMOUS", "EAVE": "UNANIMOUS"}
