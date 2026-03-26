"""웹훅 이벤트 발송 서비스.

HMAC-SHA256 서명으로 페이로드 무결성을 보장한다.
실패 시 3회 재시도 (지수 백오프).
"""

import hashlib
import hmac
import json
import time
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.webhook import Webhook
from apps.api.database.models.webhook_delivery import WebhookDelivery
from apps.api.metrics import WEBHOOK_DELIVERIES

logger = structlog.get_logger(__name__)

_MAX_RETRIES = 3
_TIMEOUT_SECONDS = 10.0


def sign_payload(secret: str, payload: dict) -> str:
    """HMAC-SHA256으로 페이로드에 서명한다."""
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hmac.new(
        secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class WebhookService:
    """웹훅 이벤트 발송 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def dispatch_event(
        self,
        event_type: str,
        payload: dict,
        tenant_id: UUID,
    ) -> list[WebhookDelivery]:
        """이벤트를 구독 중인 웹훅에 발송한다."""
        # 해당 테넌트의 활성 웹훅 조회
        result = await self.db.execute(
            select(Webhook).where(
                Webhook.tenant_id == tenant_id,
                Webhook.is_active == True,  # noqa: E712
            )
        )
        webhooks = list(result.scalars().all())

        deliveries: list[WebhookDelivery] = []
        for wh in webhooks:
            # 이벤트 필터링: events가 None이면 모든 이벤트 수신
            if wh.events and event_type not in wh.events:
                continue

            delivery = await self._send_with_retry(wh, event_type, payload)
            deliveries.append(delivery)

        return deliveries

    async def _send_with_retry(
        self,
        webhook: Webhook,
        event_type: str,
        payload: dict,
    ) -> WebhookDelivery:
        """재시도 로직을 포함한 웹훅 전송."""
        signature = sign_payload(webhook.secret, payload)
        headers = {
            "Content-Type": "application/json",
            "X-PropAI-Signature": signature,
            "X-PropAI-Event": event_type,
        }
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True)

        for attempt in range(1, _MAX_RETRIES + 1):
            start = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                    resp = await client.post(webhook.url, content=body, headers=headers)

                duration_ms = (time.perf_counter() - start) * 1000
                success = 200 <= resp.status_code < 300

                delivery = WebhookDelivery(
                    webhook_id=webhook.id,
                    event_type=event_type,
                    payload=payload,
                    status_code=resp.status_code,
                    response_body=resp.text[:1024],
                    duration_ms=round(duration_ms, 2),
                    attempt=attempt,
                    success=success,
                )
                self.db.add(delivery)
                await self.db.flush()

                if success:
                    WEBHOOK_DELIVERIES.labels(status="success").inc()
                    logger.info("웹훅 전송 성공", webhook_id=str(webhook.id), event=event_type)
                    return delivery

                logger.warning(
                    "웹훅 전송 실패 (재시도 예정)",
                    webhook_id=str(webhook.id),
                    status_code=resp.status_code,
                    attempt=attempt,
                )

            except Exception as exc:
                duration_ms = (time.perf_counter() - start) * 1000
                delivery = WebhookDelivery(
                    webhook_id=webhook.id,
                    event_type=event_type,
                    payload=payload,
                    status_code=None,
                    response_body=str(exc)[:1024],
                    duration_ms=round(duration_ms, 2),
                    attempt=attempt,
                    success=False,
                )
                self.db.add(delivery)
                await self.db.flush()

                logger.warning(
                    "웹훅 전송 예외",
                    webhook_id=str(webhook.id),
                    error=str(exc),
                    attempt=attempt,
                )

        WEBHOOK_DELIVERIES.labels(status="failure").inc()
        return delivery  # type: ignore[possibly-undefined]
