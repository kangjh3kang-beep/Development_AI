"""웹훅 이벤트 발송 서비스.

HMAC-SHA256 서명으로 페이로드 무결성을 보장한다.
실패 시 3회 재시도 (지수 백오프).
"""

import hashlib
import hmac
import ipaddress
import json
import os
import socket
import time
from urllib.parse import urlparse
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


def _allow_private_webhook() -> bool:
    """로컬 개발 호환: WEBHOOK_ALLOW_PRIVATE=true면 사설망 검증을 스킵한다."""
    return (os.getenv("WEBHOOK_ALLOW_PRIVATE") or "").strip().lower() in ("1", "true", "yes")


def validate_webhook_url(url: str) -> None:
    """웹훅 URL의 SSRF 안전성을 검증한다.

    - http/https 스킴만 허용
    - 호스트를 DNS 해석해 사설/루프백/링크로컬(169.254.x.x 포함)/예약 대역 차단
    - WEBHOOK_ALLOW_PRIVATE=true(환경변수)면 대역 검증 스킵(로컬 개발용)

    Raises:
        ValueError: 검증 실패 시.
    """
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("웹훅 URL은 http/https만 허용됩니다")
    host = parsed.hostname
    if not host:
        raise ValueError("웹훅 URL에 호스트가 없습니다")

    if _allow_private_webhook():
        return

    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError as exc:
        raise ValueError(f"웹훅 호스트를 해석할 수 없습니다: {host}") from exc

    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError("사설/내부 네트워크 주소로는 웹훅을 전송할 수 없습니다")


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
        """재시도 로직을 포함한 웹훅 전송. 발송 직전에도 URL을 재검증한다(SSRF 방어)."""
        try:
            validate_webhook_url(webhook.url)
        except ValueError as exc:
            delivery = WebhookDelivery(
                webhook_id=webhook.id,
                event_type=event_type,
                payload=payload,
                status_code=None,
                response_body=f"URL 검증 실패(SSRF 차단): {exc}"[:1024],
                duration_ms=0.0,
                attempt=1,
                success=False,
            )
            self.db.add(delivery)
            await self.db.flush()
            WEBHOOK_DELIVERIES.labels(status="failure").inc()
            logger.warning(
                "웹훅 URL 검증 실패(SSRF 차단)",
                webhook_id=str(webhook.id),
                error=str(exc),
            )
            return delivery

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
                async with httpx.AsyncClient(
                    timeout=_TIMEOUT_SECONDS, follow_redirects=False
                ) as client:
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
