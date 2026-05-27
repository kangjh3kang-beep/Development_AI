"""
데이터 무결성 API — 시스템의 데이터 신뢰도를 실시간 모니터링.
"""
from fastapi import APIRouter

from apps.api.app.services.data_validation.public_data_registry import PublicDataRegistry

router = APIRouter(prefix="/data-integrity", tags=["데이터 무결성"])


@router.get("/status")
async def get_data_status():
    """전체 데이터 소스 상태 조회."""
    registry = PublicDataRegistry.get_instance()
    all_status = registry.get_all_status()
    stale = registry.get_stale_sources()
    hardcoded_warnings = registry.get_hardcoded_warnings()

    healthy_count = sum(1 for s in all_status if s["is_healthy"])
    total_count = len(all_status)

    return {
        "overall_health": "healthy" if healthy_count == total_count else "degraded",
        "healthy_sources": healthy_count,
        "total_sources": total_count,
        "stale_sources": stale,
        "hardcoded_warnings": hardcoded_warnings,
        "sources": all_status,
    }


@router.get("/freshness/{source_name}")
async def check_freshness(source_name: str):
    """특정 데이터 소스의 신선도 확인."""
    registry = PublicDataRegistry.get_instance()
    source = registry.get_status(source_name)
    if not source:
        return {"error": f"'{source_name}' 데이터 소스를 찾을 수 없습니다."}
    return source.to_dict()


@router.post("/refresh/{source_name}")
async def trigger_refresh(source_name: str):
    """특정 데이터 소스 수동 갱신 트리거."""
    # This would trigger the ETL for the specific source
    return {"message": f"'{source_name}' 갱신이 요청되었습니다.", "status": "queued"}
