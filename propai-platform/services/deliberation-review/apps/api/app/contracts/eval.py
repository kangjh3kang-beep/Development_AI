"""P4 — 추출 평가 계약(AECV-Bench 스타일). 골든셋 항목 + 평가 리포트(정확도/유형별/불일치)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.contracts._types import Probability


class GoldenItem(BaseModel):
    item_id: str
    kind: str  # sheet_role | element
    input: dict
    expected: str


class EvalReport(BaseModel):
    kind: str
    total: int
    correct: int
    accuracy: Probability
    per_type: dict = Field(default_factory=dict)      # expected타입 → {total, correct, accuracy}
    mismatches: list = Field(default_factory=list)     # [{item_id, expected, predicted}]
