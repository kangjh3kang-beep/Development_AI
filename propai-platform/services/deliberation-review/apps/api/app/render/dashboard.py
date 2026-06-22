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
        # 집계 신호('가장 제약 큰 항목이 전체 좌우') — 대시보드 소비자가 worst-of를 재계산하지 않도록 노출. 항목 없으면 None.
        "overall_status": report.overall_status.value if report.overall_status else None,
    }
