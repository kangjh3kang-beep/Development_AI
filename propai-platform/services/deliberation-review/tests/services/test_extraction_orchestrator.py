"""INC-10 — 추출 오케스트레이터 단위 검증.

P-에이전트 완료 게이트: 취합가가 LLM이 아님(결정론 합의), 합의 결정론(동일 캐시입력 2회 동일),
CONFLICT→needs_review 무음0, 단계 trace 노출(관측성).
"""
from app.contracts.drawing_extraction import ExtractedElement
from app.services.extraction.extraction_orchestrator import (
    _aggregate_consensus,
    orchestrate_extraction,
)

_HINT_DRAWINGS = [{
    "sheet_id": "A-01", "sheet_role": "PLAN",
    "element_hints": [
        {"semantic_hint": "PILOTIS", "hint_strength": 0.9, "area": 100.0},
        {"semantic_hint": "BALCONY", "hint_strength": 0.8, "area": 20.0, "depth": 1.2},
    ],
    "area_table": {"target": "building_area", "outer_area": 600.0},
}]


def _orch(**over):
    kw = dict(drawings=_HINT_DRAWINGS, drawing={"scale_text": "1:100"},
              explicit_calc_targets=[], ifc=None, direct_elements=[])
    kw.update(over)
    return orchestrate_extraction(**kw)


def test_trace_stages_and_sources():
    # 명시적 에이전트 파이프라인 6단계가 trace로 노출(관측성).
    bundle = _orch()
    assert [s.stage for s in bundle.trace] == \
        ["role_resolve", "extract", "aggregate", "calc_target", "dual_path", "verify"]
    assert bundle.drawing_source == "HINTS"
    assert bundle.calc_targets_source == "DRAWING_AUTO"
    assert bundle.extraction.source == "VLLM"
    # 단일 패스 취합가 → 모두 SINGLE(값 보존, 메타만 부착).
    agg = next(s for s in bundle.trace if s.stage == "aggregate")
    assert agg.detail["distribution"] == {"SINGLE": 2}


def test_consensus_deterministic_same_input_twice():
    # 합의 결정론 — 동일 입력 2회 동일 산출(취합가가 결정론이므로, INV-1).
    b1, b2 = _orch(), _orch()
    assert b1.deterministic_trace() == b2.deterministic_trace()
    assert b1.skipped == b2.skipped
    assert b1.calc_targets == b2.calc_targets
    assert b1.drawing_elements == b2.drawing_elements


def _el(t: str, eid: str) -> ExtractedElement:
    return ExtractedElement(element_id=eid, semantic_hint=t, provenance={"sheet": "S1"})


def test_aggregator_is_deterministic_and_not_llm():
    # 취합가 = CrossSourceValidator(결정론) — API키·네트워크 불요. 동일 입력 동일 합의.
    passes = [[_el("PARKING", "S1-v0")], [_el("PARKING", "S1-v0")], [_el("PARKING", "S1-v0")]]
    out1, d1, n1 = _aggregate_consensus(passes)
    out2, d2, n2 = _aggregate_consensus(passes)
    assert d1 == d2 and n1 == n2
    assert d1["distribution"] == {"UNANIMOUS": 1}  # 3패스 만장일치
    assert not n1  # CONFLICT 없음 → 표면화 note 없음


def test_aggregator_conflict_surfaced_needs_review():
    # 동수 불일치(PARKING vs BASEMENT) → CONFLICT, needs_review 표면화(무음0).
    passes = [[_el("PARKING", "S1-v0")], [_el("BASEMENT", "S1-v0")]]
    _out, detail, notes = _aggregate_consensus(passes)
    assert detail["distribution"].get("CONFLICT") == 1
    assert any("CONFLICT" in x and "needs_review" in x for x in notes)


class _StaticVision:
    """N-패스 결정론 추출가(동일 캐시입력 모사) — 매 호출 동일 결과."""

    def extract_elements(self, image_ref, hint_text):
        return [{"type": "PARKING", "confidence": 0.9}]


class _FlipVision:
    """패스마다 다른 분류(불일치 모사) — CONFLICT 표면화 검증용."""

    def __init__(self):
        self.calls = 0

    def extract_elements(self, image_ref, hint_text):
        self.calls += 1
        return [{"type": "PARKING" if self.calls == 1 else "BASEMENT", "confidence": 0.9}]


def _npass_orch(vision, passes):
    from app.adapters.vision.drawing_extractor import DrawingExtractor
    from app.core import parameters
    parameters.set_override("vision_consensus_passes", passes)
    try:
        return orchestrate_extraction(
            drawings=[{"sheet_id": "S1", "image_ref": "x.png"}], drawing={},
            explicit_calc_targets=[], ifc=None, direct_elements=[],
            extractor=DrawingExtractor(vision_client=vision))
    finally:
        parameters._overrides.pop("vision_consensus_passes", None)


def test_npass_vision_consensus_unanimous():
    # N-패스(동일 캐시입력) → 결정론 합의 UNANIMOUS(INC-8 캐시 → INV-1).
    bundle = _npass_orch(_StaticVision(), passes=3)
    agg = next(s for s in bundle.trace if s.stage == "aggregate")
    assert agg.detail["n_passes"] == 3
    assert agg.detail["distribution"] == {"UNANIMOUS": 1}
    assert bundle.drawing_source == "VLLM_VISION"


def test_npass_vision_conflict_surfaced_in_skipped():
    # 패스 불일치 → CONFLICT, trace status + skipped 표면화(무음 채택 금지).
    bundle = _npass_orch(_FlipVision(), passes=2)
    agg = next(s for s in bundle.trace if s.stage == "aggregate")
    assert "CONFLICT" in agg.detail["distribution"]
    assert agg.status == "CONFLICT"
    assert any(s.startswith("vision_consensus:") for s in bundle.skipped)
