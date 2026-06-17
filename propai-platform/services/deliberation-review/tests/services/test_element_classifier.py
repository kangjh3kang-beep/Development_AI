"""AT-3/AT-4 — 요소 의미분류: 필로티 태그 제공, 불확실 요소는 UNKNOWN+confidence 하향."""
from app.contracts.semantic_element import SemanticType
from app.services.element.element_classifier import ElementClassifier

PLAN_PLUS_SECTION_WITH_PILOTIS = {
    "elements": [
        {
            "element_id": "e1",
            "features": {"semantic_hint": "PILOTIS", "hint_strength": 0.9},
            "present_in_sheets": ["PLAN-1", "SEC-1"],
        }
    ]
}

AMBIGUOUS_ELEMENT = {
    "elements": [
        {"element_id": "e2", "features": {"hint_strength": 0.3}},
    ]
}


def test_pilotis_classified():
    els = ElementClassifier().classify(PLAN_PLUS_SECTION_WITH_PILOTIS)
    assert any(e.semantic_type == SemanticType.PILOTIS for e in els)


def test_uncertain_element_no_default_type():
    e = ElementClassifier().classify(AMBIGUOUS_ELEMENT)[0]
    assert e.semantic_type == SemanticType.UNKNOWN
    assert e.confidence < 0.5
