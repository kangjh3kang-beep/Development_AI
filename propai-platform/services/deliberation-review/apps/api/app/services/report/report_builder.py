"""L6 — 보고서 빌더. 전 계층 산출(Finding/SimMetric/PrecedentStat/Verification)을 항목별 집계.

L5 분류(CONFIRMED/NEEDS_REVIEW/BLOCKED)를 구획으로 분리 보존(병합/은폐 금지, INV-28).
기준 미존재/재량 항목 → DISCRETION_HELD(INV-30). 모든 항목 근거 동반(emit) + 감사 결속.
"""
from __future__ import annotations

from app.contracts.report import ReportItem, ReportStatus, ReviewReport, emit
from app.services.report.audit_binder import AuditBinder

_STATUS_MAP = {
    "CONFIRMED": ReportStatus.CONFIRMED,
    "NEEDS_REVIEW": ReportStatus.NEEDS_REVIEW,
    "BLOCKED": ReportStatus.BLOCKED,
    "DISCRETION": ReportStatus.DISCRETION_HELD,
    "DISCRETION_HELD": ReportStatus.DISCRETION_HELD,
}


class ReportBuilder:
    def __init__(self, binder: AuditBinder | None = None) -> None:
        self.binder = binder or AuditBinder()

    def _classify(self, raw: dict) -> ReportStatus:
        if raw.get("no_criterion") or raw.get("discretion"):
            return ReportStatus.DISCRETION_HELD
        return _STATUS_MAP.get(str(raw.get("status")), ReportStatus.NEEDS_REVIEW)

    def build(
        self,
        items: list[dict],
        snapshot_id: str = "snap-1",
        model_version: str = "v1",
    ) -> ReviewReport:
        built: list[ReportItem] = []
        sections: dict[str, list[ReportItem]] = {s.value: [] for s in ReportStatus}

        for raw in items:
            status = self._classify(raw)
            # 재량영역은 판정 보류 — 단정 verdict 무효화(INV-30).
            verdict = None if status == ReportStatus.DISCRETION_HELD else raw.get("verdict")
            item = ReportItem(
                item_id=raw.get("item_id"),
                title=raw.get("title"),
                verdict=verdict,
                status=status,
                evidence=raw.get("evidence"),
                confidence_grade=raw.get("confidence_grade"),
                recommendation=raw.get("recommendation"),
                basis_article=raw.get("basis_article"),
            )
            item = self.binder.bind(item, snapshot_id, model_version, raw)
            emit(item)  # 근거 강제(INV-29)
            built.append(item)
            sections[status.value].append(item)

        return ReviewReport(items=built, sections=sections)
