"""L6 — 심의위원 체크리스트 형식(항목/판정/근거/신뢰등급). 구획 보존(은폐 금지)."""
from __future__ import annotations

from app.contracts.report import ReviewReport


def to_checklist(report: ReviewReport) -> list[dict]:
    rows: list[dict] = []
    for item in report.items:
        rows.append({
            "item_id": item.item_id,
            "title": item.title,
            "verdict": item.verdict,
            "status": item.status.value,  # 구획 그대로 노출
            "basis_article": item.basis_article,
            "confidence_grade": item.confidence_grade,
            "has_evidence": item.evidence is not None,
            "snapshot_id": item.snapshot_id,
        })
    return rows
