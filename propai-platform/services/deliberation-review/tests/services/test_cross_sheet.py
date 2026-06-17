"""AT-5 — cross-sheet 매칭 실패 시 UNMATCHED + 신뢰도 하향(날조 금지)."""
from app.contracts.semantic_element import IdentityStatus, SemanticElement, SemanticType
from app.services.element.cross_sheet_identity import CrossSheetIdentity

PLAN_ONLY_ELEMENT = SemanticElement(
    element_id="e3",
    semantic_type=SemanticType.PILOTIS,
    confidence=0.9,
    source_sheets=["PLAN-1"],
)


def test_cross_sheet_unmatched():
    e = CrossSheetIdentity().match(PLAN_ONLY_ELEMENT)
    assert e.identity_status == IdentityStatus.UNMATCHED
    assert e.confidence < 1.0


def test_cross_sheet_matched():
    section_twin = SemanticElement(
        element_id="e3s",
        semantic_type=SemanticType.PILOTIS,
        confidence=0.85,
        source_sheets=["SEC-1"],
    )
    e = CrossSheetIdentity().match(PLAN_ONLY_ELEMENT, counterparts=[section_twin])
    assert e.identity_status == IdentityStatus.MATCHED
    assert "SEC-1" in e.source_sheets


def test_cross_sheet_self_evidenced_multi_sheet():
    # 이미 평면+단면에 걸친 요소는 외부 counterpart 없이도 MATCHED(하향 없음).
    spanning = SemanticElement(
        element_id="e4",
        semantic_type=SemanticType.PILOTIS,
        confidence=0.9,
        source_sheets=["PLAN-1", "SEC-1"],
    )
    e = CrossSheetIdentity().match(spanning)
    assert e.identity_status == IdentityStatus.MATCHED
    assert e.confidence == 0.9  # 자기증거 — 하향 없음
