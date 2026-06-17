"""P-A — 멀티모달 도면 자동해석 계약. 도면 시트(이미지/표제란) → 구조화 요소(+수량/면적).

설계도서 자동분석의 진입점: 사람이 elements를 손으로 짜지 않고, 도면에서 자동 추출.
원칙 승계: 날조 금지(이미지/힌트 없으면 추출 불가를 표면화), 결정론(동일 입력 동일 출력),
근거 동반(provenance=어느 시트/어느 경로[vision|hint]). 미상 타입은 UNKNOWN(임의 단정 금지, INV-9).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.contracts._types import Probability

_VALID_TYPES = {
    "PILOTIS", "BALCONY", "EAVE", "BASEMENT", "PARKING", "CORE_STAIR",
    "EXT_WALL", "PLOT_BOUNDARY", "BUILDING_LINE", "UNKNOWN",
}


def normalize_semantic_hint(raw: object) -> str:
    """추출 타입 문자열 → SemanticType 이름. 미상/빈값은 UNKNOWN(날조 금지)."""
    if not raw:
        return "UNKNOWN"
    s = str(raw).strip().upper()
    return s if s in _VALID_TYPES else "UNKNOWN"


class DrawingSheet(BaseModel):
    """입력 도면 시트 1장. image_ref가 있으면 비전(live) 추출, 없으면 element_hints 폴백."""

    sheet_id: str
    image_ref: str | None = None           # 도면 파일/이미지 참조(live 비전 입력)
    sheet_role: str | None = None          # 시트역할(SITE/PLAN/SECTION…) 알면 추출 정밀화
    titleblock_text: str | None = None
    # 오프라인/mock 폴백: 상위(2D 벡터/사람)가 이미 식별한 요소 힌트. 없으면 비전 필요.
    element_hints: list[dict] = Field(default_factory=list)  # [{semantic_hint, hint_strength, area?, quantity?}]
    # 면적표(AREA_TABLE 시트) — 자동 산정 기준(outer_area). 명시 또는 live 비전이 채움. {target, outer_area}
    area_table: dict | None = None


class ExtractedElement(BaseModel):
    """도면에서 추출된 요소 1건. area/quantity는 정량(산정 입력으로 승계 가능)."""

    element_id: str
    semantic_hint: str                     # SemanticType 이름 또는 UNKNOWN
    hint_strength: Probability = 0.0
    area: float | None = None
    quantity: float | None = None
    provenance: dict = Field(default_factory=dict)  # {sheet, src: vision|hint}


class DrawingExtraction(BaseModel):
    """도면 자동해석 산출. source로 경로(VLLM_VISION|HINTS|none) 표면화."""

    source: str = "none"                   # VLLM_VISION | HINTS | none
    elements: list[ExtractedElement] = Field(default_factory=list)
    area_tables: list[dict] = Field(default_factory=list)  # [{target, outer_area}] — 자동 산정 기준
    notes: list[str] = Field(default_factory=list)

    def to_pipeline_elements(self) -> list[dict]:
        """resolve_elements(ElementClassifier)가 받는 형식으로 변환(features에 area 동반)."""
        out: list[dict] = []
        for e in self.elements:
            features: dict = {"semantic_hint": e.semantic_hint, "hint_strength": e.hint_strength}
            if e.area is not None:
                features["area"] = e.area
            if e.quantity is not None:
                features["quantity"] = e.quantity
            out.append({"element_id": e.element_id, "features": features,
                        "provenance": e.provenance})
        return out
