"""L6 — 보고서 조회/생성 API. 항목 리스트 → 구획별 ReviewReport(분류 보존).

근거 없는 항목은 빌더의 emit가 거부(INV-29) → 400으로 표면화(무음 통과 금지).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.errors import EvidenceMissing
from app.contracts.report import ReviewReport
from app.render.checklist import to_checklist
from app.render.dashboard import to_dashboard
from app.services.report.report_builder import ReportBuilder

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


class BuildRequest(BaseModel):
    items: list[dict]
    snapshot_id: str = "snap-1"
    model_version: str = "v1"


class BuildResponse(BaseModel):
    report: ReviewReport
    checklist: list[dict]
    dashboard: dict


@router.post("/build", response_model=BuildResponse)
def build_report(req: BuildRequest) -> BuildResponse:
    try:
        report = ReportBuilder().build(
            req.items, snapshot_id=req.snapshot_id, model_version=req.model_version
        )
    except EvidenceMissing as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BuildResponse(
        report=report,
        checklist=to_checklist(report),
        dashboard=to_dashboard(report),
    )
