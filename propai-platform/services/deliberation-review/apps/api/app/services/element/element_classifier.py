"""R0.5 — 요소 의미분류(L1.1). 기하요소 → 의미타입. 불확실 시 UNKNOWN + confidence 하향(INV-9).

채택 최소 신뢰도(param)는 코드 하드코딩 금지(JSON 주입). 미달/미상 힌트는 임의 타입 부여 금지.
평면+단면 교차참조 신호(present_in_sheets)는 provenance로 보존(하류 cross-sheet에서 활용).
"""
from __future__ import annotations

from app.contracts.semantic_element import SemanticElement, SemanticType
from app.core.parameters import param


def _items(payload: object) -> list[dict]:
    if isinstance(payload, dict) and "elements" in payload:
        return payload["elements"]
    if isinstance(payload, list):
        return payload
    return [payload]  # 단일 요소


class ElementClassifier:
    def classify(self, payload: object) -> list[SemanticElement]:
        min_conf = float(param("element_classify_min_confidence"))
        out: list[SemanticElement] = []

        for el in _items(payload):
            features = el.get("features", {})
            hint = features.get("semantic_hint")
            strength = float(features.get("hint_strength", 0.0))

            if hint in SemanticType.__members__ and hint != "UNKNOWN" and strength >= min_conf:
                stype = SemanticType[hint]
                confidence = strength
            else:
                # 불확실 — 임의 타입 금지, UNKNOWN으로 하향 표면화.
                stype = SemanticType.UNKNOWN
                confidence = strength

            out.append(
                SemanticElement(
                    element_id=el["element_id"],
                    semantic_type=stype,
                    confidence=confidence,
                    source_sheets=el.get("present_in_sheets", []),
                    provenance={"hint": hint, "strength": strength},
                )
            )

        return out
