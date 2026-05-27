"""자동 용도지역 감지 라우터."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.zoning.auto_zoning_service import AutoZoningService

router = APIRouter()


class ZoningAnalyzeRequest(BaseModel):
    """용도지역 분석 요청."""

    address: str


@router.post("/analyze")
async def analyze_zoning(req: ZoningAnalyzeRequest):
    """주소 기반 자동 용도지역 감지 및 법적 한도 매핑."""
    service = AutoZoningService()
    return await service.analyze_by_address(req.address)
