"""보고서 라우터.

SSE 스트리밍 보고서 생성.
"""

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends
from packages.schemas.models import InvestorReportRequest, InvestorReportResponse, InvestorReportVariantResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.design_ai_service import DesignAIService
from apps.api.services.investor_report_service import InvestorReportService

router = APIRouter()


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
