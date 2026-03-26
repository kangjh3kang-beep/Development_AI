"""설계 AI 보고서 생성 서비스.

LLM 기반 설계 검토 보고서를 SSE 스트리밍 및 동기 호출로 생성한다.
StreamingReportEvent 스키마를 사용한다 (부록 B).

흐름:
1. 프로젝트/설계 데이터 수집
2. LLM에 설계 검토 요청
3. 청크 단위 SSE 스트리밍 또는 동기 전체 반환
4. AI 비용 자동 기록
"""

from collections.abc import AsyncIterator
from uuid import UUID

import structlog
from packages.schemas.events import StreamingReportEvent
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.services.ai_usage_tracker import track_ai_usage

logger = structlog.get_logger(__name__)

_DESIGN_PROMPT_TEMPLATE = """부동산 설계 전문가로서 다음 프로젝트의 설계 검토 보고서를 마크다운으로 작성하세요.

## 프로젝트 정보
{design_data}

## 보고서 구성
1. 설계 개요
2. 공간 구성 분석
3. 법규 적합성 (용적률, 건폐율, 일조권)
4. 에너지 효율 검토
5. 개선 권고 사항
6. 종합 평가

모든 내용을 한국어로 작성하세요."""


class DesignAIService:
    """설계 AI 보고서 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    async def stream_design_report(
        self,
        project_id: UUID,
        tenant_id: UUID,
        design_data: dict,
    ) -> AsyncIterator[StreamingReportEvent]:
        """설계 검토 보고서를 SSE 스트리밍으로 생성한다."""
        from langchain_anthropic import ChatAnthropic

        logger.info("설계 보고서 스트리밍 시작", project_id=str(project_id))

        llm = ChatAnthropic(
            model="claude-sonnet-4-5-20250929",
            api_key=self.settings.anthropic_api_key,
            temperature=0.3,
            streaming=True,
        )

        prompt = _DESIGN_PROMPT_TEMPLATE.format(design_data=design_data)

        chunk_index = 0
        buffer = ""
        total_tokens = 0

        async for chunk in llm.astream(prompt):
            content = chunk.content if hasattr(chunk, "content") else str(chunk)
            if not content:
                continue

            buffer += content
            total_tokens += len(content.split())

            # 문장 단위로 끊어서 전송
            if len(buffer) >= 100 or buffer.endswith(("\n", ".", "다.", "요.")):
                yield StreamingReportEvent(
                    chunk_index=chunk_index,
                    content=buffer,
                    is_final=False,
                )
                chunk_index += 1
                buffer = ""

        # 잔여 버퍼 전송
        if buffer:
            yield StreamingReportEvent(
                chunk_index=chunk_index,
                content=buffer,
                is_final=False,
            )
            chunk_index += 1

        # 최종 이벤트
        yield StreamingReportEvent(
            chunk_index=chunk_index,
            content="",
            is_final=True,
        )

        # AI 비용 기록
        await track_ai_usage(
            db=self.db,
            tenant_id=tenant_id,
            service="design_ai",
            model="claude-sonnet-4-5-20250929",
            input_tokens=len(prompt.split()),
            output_tokens=total_tokens,
            project_id=project_id,
        )

        logger.info("설계 보고서 스트리밍 완료", chunks=chunk_index)

    async def generate_design_sync(
        self,
        project_id: UUID,
        tenant_id: UUID,
        design_data: dict,
    ) -> str:
        """설계 검토 보고서를 동기로 전체 생성하여 반환한다."""
        from langchain_anthropic import ChatAnthropic

        logger.info("설계 보고서 동기 생성 시작", project_id=str(project_id))

        llm = ChatAnthropic(
            model="claude-sonnet-4-5-20250929",
            api_key=self.settings.anthropic_api_key,
            temperature=0.3,
        )

        prompt = _DESIGN_PROMPT_TEMPLATE.format(design_data=design_data)

        try:
            response = await llm.ainvoke(prompt)
            report_text = response.content

            # AI 비용 기록
            input_tokens = len(prompt.split())
            output_tokens = len(report_text.split())

            await track_ai_usage(
                db=self.db,
                tenant_id=tenant_id,
                service="design_ai",
                model="claude-sonnet-4-5-20250929",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                project_id=project_id,
            )

            logger.info("설계 보고서 동기 생성 완료", chars=len(report_text))
            return str(report_text)

        except Exception:
            logger.warning("설계 보고서 생성 실패")
            return "설계 보고서를 생성할 수 없습니다. 전문가 검토를 권장합니다."
