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
