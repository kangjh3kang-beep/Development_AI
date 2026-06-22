"""INC-9 — 비전 추출 합의 에이전트(N-패스 추출가 + 결정론 취합가).

여러 추출 패스(비전 N회/힌트/IFC)가 같은 요소를 다르게 분류할 수 있다(PARKING vs BASEMENT 등).
취합가는 LLM이 아니라 **결정론 합의**(CrossSourceValidator 재사용) — 추출가만 LLM, 취합가는 결정론이라
동일 캐시입력(INC-8) → 동일 합의 결과(INV-1). 요소를 키별로 묶어 semantic_hint 합의 상태
(UNANIMOUS/MAJORITY/CONFLICT/SINGLE)를 산출해 ExtractedElement에 승계. CONFLICT/SINGLE은 표면화(무음0).
"""
from __future__ import annotations

from collections.abc import Callable

from app.contracts.cross_validation import SourceValue
from app.contracts.drawing_extraction import ExtractedElement
from app.services.cross_validate.validator import CrossSourceValidator


def _default_key(e: ExtractedElement) -> str:
    """동일 물리요소 정렬 키 — 시트 + 패스 내 순번(element_id 접미 v/h 인덱스). 근사 정렬."""
    sheet = e.provenance.get("sheet", "")
    suffix = e.element_id.rsplit("-", 1)[-1]
    idx = "".join(ch for ch in suffix if ch.isdigit())
    return f"{sheet}#{idx}"


def merge_with_consensus(
    passes: list[list[ExtractedElement]],
    key_fn: Callable[[ExtractedElement], str] | None = None,
) -> list[ExtractedElement]:
    """N개 추출 패스 → 키별 결정론 합의 후 대표 요소 목록(consensus_status 동반).

    각 패스는 한 추출가(source 라벨=패스 인덱스)의 요소 목록. 같은 키의 semantic_hint를 CrossSourceValidator로
    합의 → 대표 요소(합의값 hint)에 consensus_status 부착. 단일 패스만 있는 키는 SINGLE.
    """
    key_fn = key_fn or _default_key
    validator = CrossSourceValidator()
    grouped: dict[str, list[ExtractedElement]] = {}
    for pi, elems in enumerate(passes):
        for e in elems:
            grouped.setdefault(key_fn(e), []).append(e)

    out: list[ExtractedElement] = []
    for key in sorted(grouped):
        members = grouped[key]
        values = [SourceValue(source=f"pass{i}", value=e.semantic_hint) for i, e in enumerate(members)]
        cv = validator.validate(key, values)
        rep = next((e for e in members if e.semantic_hint == cv.agreed_value), members[0])
        out.append(rep.model_copy(update={"consensus_status": cv.status.value}))
    return out
