"""L6 — 산출물 계약. ReviewReport(구획별 항목 + 권고 + 감사). 분류 보존·근거 동반·재량 표기.

INV-28: L5 분류 병합/은폐 금지(구획 분리). INV-29: 근거 없는 항목 출력 금지(emit). INV-30: 재량영역 명시.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, computed_field

from app.core.errors import EvidenceMissing


class ReportStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCKED = "BLOCKED"
    DISCRETION_HELD = "DISCRETION_HELD"  # 재량영역/기준 미존재 — 판정 보류


# 집계 심각도 — '가장 제약 큰 항목이 전체 좌우'(대량필지 special_parcel 차용). BLOCKED 최우선.
# NEEDS_REVIEW(기준 존재·불확정) > DISCRETION_HELD(기준 미존재·보류) > CONFIRMED.
_STATUS_SEVERITY = {
    ReportStatus.BLOCKED: 3,
    ReportStatus.NEEDS_REVIEW: 2,
    ReportStatus.DISCRETION_HELD: 1,
    ReportStatus.CONFIRMED: 0,
}


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

    @computed_field
    @property
    def overall_status(self) -> ReportStatus | None:
        """전체 집계 — 가장 제약 큰(최악) 항목 status가 전체를 좌우(대량필지 'most-constrained governs' 차용).
        치명 BLOCKED 1건이 CONFIRMED들에 묻혀 '전체 적합'으로 오인되는 구조적 할루시네이션 차단. 구획(sections)은
        그대로 보존 — 본 필드는 병합/은폐가 아니라 worst-of 요약 포인터(INV-28 준수). 항목 없으면 None(요약 불가 정직)."""
        if not self.items:
            return None
        return max((it.status for it in self.items), key=lambda s: _STATUS_SEVERITY.get(s, 0))

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
