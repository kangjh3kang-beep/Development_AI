"""비동기 웹훅 이벤트 발송 태스크.

WebhookService.dispatch_event()를 arq 큐에서 실행한다.
"""

from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


async def dispatch_webhook_event(
    ctx: dict,
    event_type: str,
    payload: dict,
    tenant_id: str,
) -> dict:
    """웹훅 이벤트를 구독 중인 엔드포인트에 발송한다."""
    from apps.api.database.session import AsyncSessionLocal
    from apps.api.services.webhook_service import WebhookService

    logger.info("웹훅 발송 태스크 시작", event_type=event_type, tenant_id=tenant_id)

    async with AsyncSessionLocal() as db:
        service = WebhookService(db)
        deliveries = await service.dispatch_event(
            event_type=event_type,
            payload=payload,
            tenant_id=UUID(tenant_id),
        )
        await db.commit()

    result = {
        "event_type": event_type,
        "tenant_id": tenant_id,
        "deliveries_count": len(deliveries),
        "successful": sum(1 for d in deliveries if d.success),
    }
    logger.info("웹훅 발송 태스크 완료", **result)
    return result
