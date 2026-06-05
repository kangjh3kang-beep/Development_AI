"""Flagship B — 이미지융합 AVM (PoC) 라우터.

POST /api/v1/avm-vision/analyze
계약: .claude/skills/propai-orchestrator/_workspace/11_flagshipB_contract.md
얇은 라우터 — 본체는 app/services/avm_vision/avm_vision_service.py.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class AvmVisionRequest(BaseModel):
    """이미지융합 AVM 분석 요청."""

    address: str | None = None
    pnu: str | None = None
    base_value_won: float | None = None
    base_value_per_sqm_won: float | None = None


@router.post("/analyze")
async def analyze(req: AvmVisionRequest):
    """항공 정사영상 + cv2 영상특징(불가 시 프록시) 융합 AVM 보정(실험적).

    - address/pnu 모두 없으면 422.
    - 기준값·좌표 모두 불가 시 ok:false(빈결과 금지).
    """
    if not req.address and not req.pnu:
        raise HTTPException(status_code=422, detail="address 또는 pnu가 필요합니다.")

    from app.services.avm_vision.avm_vision_service import analyze_avm_vision

    return await analyze_avm_vision(
        address=req.address,
        pnu=req.pnu,
        base_value_won=req.base_value_won,
        base_value_per_sqm_won=req.base_value_per_sqm_won,
    )
