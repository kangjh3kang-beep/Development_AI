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


from pydantic import BaseModel, Field


class DesignInput(BaseModel):
    """설계 AI 입력 스키마."""
    project_id: "UUID"
    tenant_id: "UUID"
    design_data: dict
    image_urls: list[str] = Field(default_factory=list)


class DesignOutput(BaseModel):
    """설계 AI 출력 스키마."""
    report_text: str
    sections: list[dict] = Field(default_factory=list)
    image_analysis: dict | None = None
    recommendations: list[str] = Field(default_factory=list)


# ── DesignAIService 확장 메서드 (monkey-patch 방지를 위해 클래스 외부에서 추가) ──


async def _analyze_design_image(self, image_url_or_base64: str) -> dict:
    """Claude Vision API로 설계 이미지를 분석한다.

    base64 인코딩된 이미지 또는 URL을 받아 건축 설계 이미지를 분석한다.
    Anthropic SDK가 없거나 API 호출 실패 시 폴백 응답을 반환한다.

    Args:
        image_url_or_base64: 이미지 URL 또는 base64 인코딩 문자열

    Returns:
        {"analysis": str, "model": str} 또는 {"analysis": str, "error": str}
    """
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self.settings.anthropic_api_key)

        # base64인지 URL인지 판별
        if image_url_or_base64.startswith("data:") or len(image_url_or_base64) > 500:
            image_content = {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": image_url_or_base64.split(",")[-1],
            }
        else:
            image_content = {"type": "url", "url": image_url_or_base64}

        message = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": image_content},
                    {"type": "text", "text": "이 건축 설계 이미지를 분석하세요. 건축 스타일, 재료, 공간 배치, 특이사항을 한국어로 설명하세요."},
                ],
            }],
        )
        return {"analysis": message.content[0].text, "model": "claude-sonnet-4-5-20250929"}
    except Exception as e:
        logger.warning("Vision 분석 실패", error=str(e))
        return {"analysis": "이미지 분석을 수행할 수 없습니다.", "error": str(e)}


async def _generate_design_structured(self, design_input: "DesignInput") -> "DesignOutput":
    """구조화된 설계 보고서를 생성한다.

    이미지가 포함된 경우 Vision 분석을 먼저 수행한 후
    기존 generate_design_sync로 텍스트 보고서를 생성하고,
    섹션 파싱 및 개선 권고를 추출한다.

    Args:
        design_input: DesignInput 모델

    Returns:
        DesignOutput 모델
    """
    # 이미지가 있으면 Vision 분석 수행
    image_analysis = None
    if design_input.image_urls:
        image_analysis = await self.analyze_design_image(design_input.image_urls[0])

    # 기존 generate_design_sync 호출
    report_text = await self.generate_design_sync(
        design_input.project_id, design_input.tenant_id, design_input.design_data
    )

    # 섹션 파싱 (## 헤더 기준)
    sections = []
    for part in report_text.split("## "):
        if part.strip():
            lines = part.strip().split("\n", 1)
            sections.append({
                "title": lines[0].strip(),
                "content": lines[1].strip() if len(lines) > 1 else "",
            })

    # 개선 권고 추출
    recommendations = [
        s["content"][:200]
        for s in sections
        if "권고" in s.get("title", "") or "개선" in s.get("title", "")
    ]

    return DesignOutput(
        report_text=report_text,
        sections=sections,
        image_analysis=image_analysis,
        recommendations=recommendations,
    )


# 클래스에 메서드 바인딩
DesignAIService.analyze_design_image = _analyze_design_image
DesignAIService.generate_design_structured = _generate_design_structured
