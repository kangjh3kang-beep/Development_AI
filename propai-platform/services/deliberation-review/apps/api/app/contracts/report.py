"""L6 — 산출물 계약. ReviewReport(구획별 항목 + 권고 + 감사). 분류 보존·근거 동반·재량 표기.

INV-28: L5 분류 병합/은폐 금지(구획 분리). INV-29: 근거 없는 항목 출력 금지(emit). INV-30: 재량영역 명시.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.core.errors import EvidenceMissing


class ReportStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCKED = "BLOCKED"
    DISCRETION_HELD = "DISCRETION_HELD"  # 재량영역/기준 미존재 — 판정 보류


class ReportItem(BaseModel):
    item_id: str | None = None
    title: str | None = None
    verdict: str | None = None
    status: ReportStatus = ReportStatus.NEEDS_REVIEW
    evidence: dict | None = None  # 조문/calc_trace/method_trace/사례 출처
    confidence_grade: str | None = None
    recommendation: str | None = None
    basis_article: str | None = None
    snapshot_id: str | None = None
    model_version: str | None = None
    input_hash: str | None = None


class ReviewReport(BaseModel):
    items: list[ReportItem] = Field(default_factory=list)
    sections: dict[str, list[ReportItem]] = Field(default_factory=dict)

    def section(self, status: object) -> list[ReportItem]:
        key = status.value if isinstance(status, ReportStatus) else str(status)
        return self.sections.get(key, [])

    def find(self, item_id: str) -> ReportItem | None:
        return next((it for it in self.items if it.item_id == item_id), None)


def emit(item: ReportItem) -> ReportItem:
    """근거 없는 항목 출력 금지(INV-29)."""
    if item.evidence is None:
        raise EvidenceMissing(f"report item '{item.item_id}' has no evidence")
    return item
