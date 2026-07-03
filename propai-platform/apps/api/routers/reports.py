"""보고서 라우터.

SSE 스트리밍 보고서 생성.
"""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from packages.schemas.models import InvestorReportRequest, InvestorReportResponse, InvestorReportVariantResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.design_ai_service import DesignAIService
from apps.api.services.investor_report_service import InvestorReportService

router = APIRouter()


class ReportGenerateRequest(BaseModel):
    project_id: str
    format: str = "pdf"   # pdf | pptx | docx — 통합 보고서 생성엔진이 존중


@router.post("/generate", summary="프로젝트 통합 보고서 — PDF·PPTX·DOCX(분석 원장 기반·재실행 없음)")
async def generate_report_pdf(
    req: ReportGenerateRequest,
    current: CurrentUser = Depends(get_current_user),
) -> Response:
    """프로젝트의 최신 통합 분석(원장)으로 보고서 생성. format 으로 PDF/PPTX/DOCX 선택.

    통합 보고서 생성엔진(app.services.report.render): 단일 정본모델(PipelineReport 재사용) →
    3개 렌더러(같은 데이터·같은 디자인). 신규 엔진 실패 시 라이브 PDF 무회귀를 위해 레거시 PDF 폴백.
    """
    from app.services.ledger import analysis_ledger_service as ledger

    tid = str(getattr(current, "tenant_id", "") or "") or None
    latest = await ledger.get_latest(analysis_type="pipeline", tenant_id=tid, project_id=req.project_id)
    payload = (latest or {}).get("payload") if isinstance(latest, dict) else None
    if not payload or not isinstance(payload, dict):
        return Response(
            content='{"ok":false,"message":"통합 분석 결과가 없습니다. 프로젝트에서 전체 분석을 먼저 실행하세요."}',
            media_type="application/json", status_code=404,
        )
    result_dict: dict[str, Any] = dict(payload)
    stages = result_dict.get("stages")
    if isinstance(stages, list):
        result_dict["stages"] = {s.get("stage"): s for s in stages if isinstance(s, dict) and s.get("stage")}

    # AI 상세 해석 포함(캐시 우선, 미스는 생성 — 타임아웃 내 완료분)
    narratives: dict[str, Any] = {}
    try:
        from app.routers.pipeline import _gather_report_narratives
        narratives = await _gather_report_narratives(result_dict)
    except Exception:  # noqa: BLE001
        narratives = {}

    fmt = (req.format or "pdf").strip().lower()
    try:
        # 통합 보고서 생성엔진: 정본모델 조립 → 포맷 렌더
        from app.services.report.render import build_report_model_from_pipeline, render_report

        model = build_report_model_from_pipeline(result_dict, narratives)
        data, media_type, ext = render_report(model, fmt)
    except Exception:  # noqa: BLE001  # 신규 엔진 실패 시 라이브 PDF 무회귀(레거시 폴백)
        if fmt != "pdf":
            raise
        from app.services.report.pipeline_report_pdf import build_pipeline_report_pdf
        from app.services.report.pipeline_report_service import PipelineReportService

        report = PipelineReportService().generate(result_dict)
        data = build_pipeline_report_pdf(report.model_dump(), narratives=narratives)
        media_type, ext = "application/pdf", "pdf"

    return Response(
        content=data, media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="propai_report_{req.project_id}.{ext}"'},
    )


@router.get("/stream/{project_id}")
async def stream_report(
    project_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("reports", "read")),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """프로젝트 종합 보고서를 SSE 스트리밍으로 생성한다.

    클라이언트는 EventSource API로 실시간 마크다운 청크를 수신한다.
    """
    service = DesignAIService(db)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        """보고서 청크를 SSE 이벤트로 생성."""
        design_data = {"project_id": str(project_id), "type": "comprehensive_report"}
        chunk_index = 0

        async for event in service.stream_design_report(
            project_id=project_id,
            tenant_id=current_user.tenant_id,
            design_data=design_data,
        ):
            chunk_index += 1
            yield {
                "event": "report_chunk",
                "data": event.content,
            }

        yield {
            "event": "report_complete",
            "data": f'{{"total_chunks": {chunk_index}}}',
        }

    return EventSourceResponse(event_generator())


@router.post("/investor/generate", response_model=InvestorReportResponse)
async def generate_investor_report(
    body: InvestorReportRequest,
    current_user: CurrentUser = Depends(RequirePermission("reports", "read")),
    db: AsyncSession = Depends(get_db),
) -> InvestorReportResponse:
    """Generate a multilingual investor report."""
    service = InvestorReportService(db)
    variants = await service.generate(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        project_name=body.project_name,
        asset_type=body.asset_type,
        target_languages=body.target_languages,
        investment_highlights=body.investment_highlights,
        risks=body.risks,
        include_sections=body.include_sections,
    )
    return InvestorReportResponse(
        project_id=body.project_id,
        report_type="investor",
        variants=[
            InvestorReportVariantResponse(
                report_id=report.id,
                target_language=report.target_language,
                title=report.title,
                quality_score=report.quality_score,
                translated_text=report.translated_text,
            )
            for report in variants
        ],
        generated_sections=body.include_sections,
    )
