"""부동산 등기부(소유관계) 라우터 — 단건/다필지 일괄 조회·다운로드."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.registry.registry_service import RegistryService

router = APIRouter(prefix="/registry", tags=["부동산 등기부"])


class RegistryBulkRequest(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list, description="[{pnu?, address?}]")
    addresses: list[str] | None = None  # 단축 입력


@router.get("/status", summary="등기부 API 연동 상태")
async def registry_status() -> dict[str, Any]:
    return RegistryService().status()


@router.post("/bulk", summary="다필지 등기부 일괄 조회/다운로드")
async def registry_bulk(req: RegistryBulkRequest) -> dict[str, Any]:
    """여러 필지의 등기부를 일괄 조회/발급한다(공급자 키 설정 시). 미설정 시 안내 반환."""
    items = list(req.items or [])
    if not items and req.addresses:
        items = [{"address": a} for a in req.addresses if a and a.strip()]
    return await RegistryService().bulk(items)


class RegistryAnalyzeRequest(BaseModel):
    address: str | None = None
    pnu: str | None = None
    registry_text: str | None = None  # 등기부등본 내용 직접 입력(연동 미설정 시)


@router.post("/analyze", summary="부동산 등기정보 권리분석(법무사·변호사 AI)")
async def registry_analyze(req: RegistryAnalyzeRequest) -> dict[str, Any]:
    """등기부(연동 조회 또는 직접 입력)를 법무사·변호사 관점에서 분석해 소유정보·소유기간·
    매입금액·보유지분·가등기·압류·근저당·매도청구 가능여부 등 권리관계를 제공한다."""
    from app.services.registry.registry_analysis_service import RegistryAnalysisService

    return await RegistryAnalysisService().analyze(
        address=req.address, pnu=req.pnu, registry_text=req.registry_text
    )
