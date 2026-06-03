"""분석 검증(오류·할루시네이션) 라우터 — 전수 배치."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.services.verification.verifier_service import VerifierService
from apps.api.auth.jwt_handler import CurrentUser, get_current_user

router = APIRouter(prefix="/verify", tags=["분석 검증"])


class VerifyRequest(BaseModel):
    analysis_type: str = Field(description="permit|regulation|market|feasibility|site 등")
    source: dict[str, Any] | str = Field(default_factory=dict, description="원본 근거 데이터")
    output: dict[str, Any] | str = Field(default_factory=dict, description="검증 대상 분석 출력")


@router.post("/analysis", summary="분석 출력 오류·할루시네이션 검증")
async def verify_analysis(
    req: VerifyRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """분석 출력이 원본 데이터에 근거하는지 검증해 통과/주의/오류 판정과 플래그를 반환."""
    if not req.output:
        raise HTTPException(status_code=400, detail="검증 대상(output)이 필요합니다.")
    return await VerifierService().verify(req.analysis_type, req.source or {}, req.output)
