"""종합 부지분석 API 라우터.

주소 하나만 입력하면 7개 카테고리 자동 분석 보고서를 반환.
LLM 프로바이더를 선택하여 AI 해석에 사용할 모델을 지정할 수 있다.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.services.auth.auth_service import get_current_user

# P2-2 보안: 종합분석 LLM 호출 라우트 인증 강제(무인증·무쿼터 LLM 호출 → 미과금 비용남용 차단).
# (사용자별 LLM 쿼터 enforce는 후속 — 우선 익명 호출 차단 + 호출자 귀속.)
router = APIRouter(dependencies=[Depends(get_current_user)])


class ComprehensiveAnalysisRequest(BaseModel):
    address: str = Field(..., description="분석 대상 주소")
    llm_provider: str | None = Field(
        None, description="LLM 프로바이더 (anthropic/openai/google). 미지정 시 기본값 사용."
    )
    llm_model: str | None = Field(
        None, description="LLM 모델 ID (예: claude-sonnet-4-20250514, gpt-4o-mini). 미지정 시 프로바이더 기본 모델 사용."
    )


@router.post("/comprehensive")
async def run_comprehensive_analysis(req: ComprehensiveAnalysisRequest):
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )

    service = ComprehensiveAnalysisService()
    return await service.analyze(
        address=req.address,
        llm_provider=req.llm_provider,
        llm_model=req.llm_model,
    )


@router.get("/llm-providers")
async def list_llm_providers():
    """사용 가능한 LLM 프로바이더 목록 반환.

    API 키가 환경변수에 설정된 프로바이더만 반환한다.
    """
    from app.services.ai.llm_provider import get_available_providers

    return {"providers": get_available_providers()}
