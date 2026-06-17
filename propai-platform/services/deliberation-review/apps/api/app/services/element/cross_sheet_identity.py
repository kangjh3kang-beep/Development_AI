"""R0.5 — cross-sheet 동일성(WB18). 평면-단면 동일 요소 매칭(best-effort).

매칭 실패 → identity_status=UNMATCHED + confidence 하향(신규 기전 없이 게이팅에 흡수).
날조 금지: 짝을 찾지 못하면 만들지 않고 UNMATCHED로 표면화.
"""
from __future__ import annotations

from app.contracts.semantic_element import IdentityStatus, SemanticElement
from app.core.confidence import degrade
from app.core.parameters import param


class CrossSheetIdentity:
    def match(
        self,
        element: SemanticElement,
        counterparts: list[SemanticElement] | None = None,
    ) -> SemanticElement:
        candidates = counterparts or []

        # 자기증거: 이미 복수 시트(평면+단면 등)에 걸쳐 있으면 동일성 성립(하향 없이 MATCHED).
        if len(set(element.source_sheets)) >= 2:
            return element.model_copy(
                update={
                    "identity_status": IdentityStatus.MATCHED,
                    "provenance": {**element.provenance, "matched_with": "self_multi_sheet"},
                }
            )

        matched = next(
            (
                c
                for c in candidates
                if c.semantic_type == element.semantic_type
                and set(c.source_sheets) != set(element.source_sheets)
            ),
            None,
        )

        if matched is not None:
            merged_sheets = sorted(set(element.source_sheets) | set(matched.source_sheets))
            return element.model_copy(
                update={
                    "identity_status": IdentityStatus.MATCHED,
                    "source_sheets": merged_sheets,
                    "provenance": {**element.provenance, "matched_with": matched.element_id},
                }
            )

        penalty = float(param("cross_sheet_unmatched_penalty"))
        return element.model_copy(
            update={
                "identity_status": IdentityStatus.UNMATCHED,
                "confidence": degrade(element.confidence, penalty),
                "provenance": {**element.provenance, "matched_with": None},
            }
        )
