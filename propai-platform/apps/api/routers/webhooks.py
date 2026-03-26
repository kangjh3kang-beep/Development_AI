"""웹훅 라우터.

CRUD + 전송 이력 조회 + 테스트 발송.
"""

import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from packages.schemas.models import (
    WebhookCreateRequest,
    WebhookDeliveryResponse,
    WebhookResponse,
    WebhookUpdateRequest,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.models.webhook import Webhook
from apps.api.database.models.webhook_delivery import WebhookDelivery
from apps.api.database.session import get_db
from apps.api.services.webhook_service import WebhookService

router = APIRouter()


def _to_response(wh: Webhook) -> WebhookResponse:
    """Webhook ORM → WebhookResponse."""
    return WebhookResponse(
        id=wh.id,
        tenant_id=wh.tenant_id,
        url=wh.url,
        events=wh.events,
        is_active=wh.is_active,
        description=wh.description,
        created_at=wh.created_at,
        updated_at=wh.updated_at,
    )


async def _get_webhook_or_404(
    webhook_id: UUID, tenant_id: UUID, db: AsyncSession,
) -> Webhook:
    """웹훅을 조회하고, 없으면 404를 반환한다."""
    result = await db.execute(
        select(Webhook).where(
            Webhook.id == webhook_id,
            Webhook.tenant_id == tenant_id,
        )
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="웹훅을 찾을 수 없습니다",
        )
    return webhook


@router.get("", response_model=list[WebhookResponse])
async def list_webhooks(
    current_user: CurrentUser = Depends(RequirePermission("webhooks", "read")),
    db: AsyncSession = Depends(get_db),
) -> list[WebhookResponse]:
    """웹훅 목록을 조회한다."""
    result = await db.execute(
        select(Webhook)
        .where(Webhook.tenant_id == current_user.tenant_id)
        .order_by(Webhook.created_at.desc())
    )
    webhooks = list(result.scalars().all())
    return [_to_response(wh) for wh in webhooks]


@router.post("", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    body: WebhookCreateRequest,
    current_user: CurrentUser = Depends(RequirePermission("webhooks", "write")),
    db: AsyncSession = Depends(get_db),
) -> WebhookResponse:
    """웹훅을 생성한다. secret은 자동 생성."""
    webhook = Webhook(
        tenant_id=current_user.tenant_id,
        url=body.url,
        secret=secrets.token_hex(32),
        events=body.events,
        description=body.description,
    )
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)
    return _to_response(webhook)


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("webhooks", "read")),
    db: AsyncSession = Depends(get_db),
) -> WebhookResponse:
    """웹훅 상세 정보를 조회한다."""
    webhook = await _get_webhook_or_404(webhook_id, current_user.tenant_id, db)
    return _to_response(webhook)


@router.put("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: UUID,
    body: WebhookUpdateRequest,
    current_user: CurrentUser = Depends(RequirePermission("webhooks", "write")),
    db: AsyncSession = Depends(get_db),
) -> WebhookResponse:
    """웹훅을 수정한다."""
    webhook = await _get_webhook_or_404(webhook_id, current_user.tenant_id, db)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(webhook, field, value)

    await db.commit()
    await db.refresh(webhook)
    return _to_response(webhook)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("webhooks", "delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """웹훅을 삭제한다 (물리 삭제)."""
    webhook = await _get_webhook_or_404(webhook_id, current_user.tenant_id, db)
    await db.delete(webhook)
    await db.commit()


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryResponse])
async def list_deliveries(
    webhook_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("webhooks", "read")),
    db: AsyncSession = Depends(get_db),
) -> list[WebhookDeliveryResponse]:
    """웹훅 전송 이력을 조회한다 (최근 50건)."""
    # 웹훅 소유권 확인
    await _get_webhook_or_404(webhook_id, current_user.tenant_id, db)

    result = await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(50)
    )
    deliveries = list(result.scalars().all())
    return [
        WebhookDeliveryResponse(
            id=d.id,
            webhook_id=d.webhook_id,
            event_type=d.event_type,
            status_code=d.status_code,
            success=d.success,
            attempt=d.attempt,
            duration_ms=d.duration_ms,
            created_at=d.created_at,
        )
        for d in deliveries
    ]


@router.post("/{webhook_id}/test", response_model=WebhookDeliveryResponse)
async def test_webhook(
    webhook_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("webhooks", "write")),
    db: AsyncSession = Depends(get_db),
) -> WebhookDeliveryResponse:
    """테스트 이벤트를 발송한다."""
    await _get_webhook_or_404(webhook_id, current_user.tenant_id, db)

    service = WebhookService(db)
    deliveries = await service.dispatch_event(
        event_type="webhook.test",
        payload={"message": "PropAI 웹훅 테스트 이벤트입니다"},
        tenant_id=current_user.tenant_id,
    )
    await db.commit()

    if not deliveries:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="테스트 이벤트 전송 실패",
        )

    d = deliveries[0]
    return WebhookDeliveryResponse(
        id=d.id,
        webhook_id=d.webhook_id,
        event_type=d.event_type,
        status_code=d.status_code,
        success=d.success,
        attempt=d.attempt,
        duration_ms=d.duration_ms,
        created_at=d.created_at,
    )
