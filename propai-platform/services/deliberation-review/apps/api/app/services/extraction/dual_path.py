"""P1 — 이중경로 요소 추출. BIM(IFC) 있으면 구조화 추출, 없으면 VLLM/2D(ElementClassifier).

BIM이 있으면 2D 도면 한계·VLLM 환각을 우회(국내 R&D BIM 방향 정합). 둘 다 없으면 source=none(표면화).
"""
from __future__ import annotations

from app.adapters.bim.ifc_parser import IfcParser
from app.contracts.bim import ExtractionResult
from app.contracts.semantic_element import SemanticElement
from app.services.element.element_classifier import ElementClassifier


def resolve_elements(payload: dict) -> ExtractionResult:
    ifc = payload.get("ifc")
    if ifc:
        model = IfcParser().parse(ifc)
        ses = [
            SemanticElement(
                element_id=e.guid or f"bim-{i}",
                semantic_type=e.semantic_type,
                confidence=1.0,  # BIM은 구조화 입력 → 추출 불확실성 없음(분류 신뢰도 ≠ 측정 신뢰도)
                source_sheets=["BIM"],
                provenance={"ifc_type": e.ifc_type, "name": e.name},
            )
            for i, e in enumerate(model.elements)
        ]
        return ExtractionResult(source="BIM", bim=model, semantic_elements=ses, note="IFC 구조화 추출")

    elements = payload.get("elements")
    if elements:
        ses = ElementClassifier().classify({"elements": elements})
        return ExtractionResult(source="VLLM", semantic_elements=ses, note="2D/VLLM 추출")

    return ExtractionResult(source="none", note="추출 입력(ifc/elements) 없음")
