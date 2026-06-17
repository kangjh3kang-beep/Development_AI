"""L6 — 정량 대시보드 데이터. 구획별 항목수 + 정량 지표 요약. NEEDS_REVIEW/BLOCKED 가시화."""
from __future__ import annotations

from app.contracts.report import ReportStatus, ReviewReport


def to_dashboard(report: ReviewReport) -> dict:
    counts = {s.value: len(report.section(s)) for s in ReportStatus}
    return {
        "section_counts": counts,
        "total": len(report.items),
        # 미확정/차단 항목은 별도 가시화(은폐 금지).
        "needs_attention": counts[ReportStatus.NEEDS_REVIEW.value] + counts[ReportStatus.BLOCKED.value],
        "discretion": counts[ReportStatus.DISCRETION_HELD.value],
    }
