"""전문가 패널 분석 라우터 — 다관점 분석·토론·검증."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.expert_panel.expert_panel_service import ExpertPanelService

router = APIRouter(prefix="/expert-panel", tags=["전문가 패널"])


class ExpertPanelRequest(BaseModel):
    analysis_type: str = Field(description="permit|regulation|market|feasibility|site")
    context: dict[str, Any] | str = Field(default_factory=dict, description="분석 결과/맥락")
    address: str = ""
    mode: str = "single"  # single | deep(정밀 다중 에이전트)


@router.post("/analyze", summary="전문가 패널 다관점 분석·검증")
async def analyze_panel(req: ExpertPanelRequest) -> dict[str, Any]:
    """분석유형별 관련 전문가 관점에서 분석·토론하고 통합 결론·검증을 제시한다."""
    if not req.context:
        raise HTTPException(status_code=400, detail="분석 맥락(context)이 필요합니다.")
    mode = "deep" if req.mode == "deep" else "single"
    return await ExpertPanelService().analyze(
        analysis_type=req.analysis_type, context=req.context, address=req.address, mode=mode
    )
