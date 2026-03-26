"""AVM 배치 시세 추정 태스크.

여러 필지에 대해 일괄 AVM 추정을 수행한다.
야간 배치 / 대량 프로젝트 분석 시 사용.
"""

from typing import Any
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


async def run_avm_batch(
    ctx: dict[str, Any],
    tenant_id: str,
    parcel_ids: list[str],
) -> dict[str, Any]:
    """복수 필지에 대한 AVM 배치 추정.

    1. parcel_ids 목록으로 필지 데이터 조회
    2. 각 필지에 대해 AVMService.estimate() 호출
    3. 결과 일괄 DB 저장 + 요약 반환
    """
    from apps.api.database.session import AsyncSessionLocal
    from apps.api.services.avm_service import AVMService

    logger.info("AVM 배치 추정 시작", tenant_id=tenant_id, count=len(parcel_ids))

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    async with AsyncSessionLocal() as db:
        service = AVMService(db)

        for pid in parcel_ids:
            try:
                valuation = await service.estimate(
                    tenant_id=UUID(tenant_id),
                    parcel_id=UUID(pid),
                )
                results.append({
                    "parcel_id": pid,
                    "estimated_price": valuation.estimated_price,
                    "confidence_score": valuation.confidence_score,
                })
            except Exception as exc:
                logger.warning("AVM 추정 실패", parcel_id=pid, error=str(exc))
                errors.append({"parcel_id": pid, "error": str(exc)})

        await db.commit()

    logger.info(
        "AVM 배치 추정 완료",
        success=len(results),
        errors=len(errors),
    )
    return {
        "status": "completed",
        "tenant_id": tenant_id,
        "total": len(parcel_ids),
        "success": len(results),
        "errors": len(errors),
        "results": results,
    }
