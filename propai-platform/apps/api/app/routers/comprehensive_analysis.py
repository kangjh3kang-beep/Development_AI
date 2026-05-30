"""종합 부지분석 API 라우터.

주소 하나만 입력하면 7개 카테고리 자동 분석 보고서를 반환.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class ComprehensiveAnalysisRequest(BaseModel):
    address: str = Field(..., description="분석 대상 주소")


@router.post("/comprehensive")
async def run_comprehensive_analysis(req: ComprehensiveAnalysisRequest):
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )

    service = ComprehensiveAnalysisService()
    return await service.analyze(address=req.address)
