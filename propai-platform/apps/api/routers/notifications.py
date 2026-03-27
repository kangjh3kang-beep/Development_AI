"""Notification endpoints."""

import secrets
from datetime import datetime, timezone
UTC = timezone.utc

from fastapi import APIRouter, Depends, status
from packages.schemas.models import AlimTalkRequest, NotificationResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.models.notification_message import NotificationMessage
from apps.api.database.session import get_db

router = APIRouter()


def _to_response(message: NotificationMessage) -> NotificationResponse:
    return NotificationResponse(
        id=message.id,
        project_id=message.project_id,
        channel=message.channel,
        recipient_phone=message.recipient_phone,
        template_code=message.template_code,
        status=message.status,
        external_ref=message.external_ref,
        sent_at=message.sent_at,
        created_at=message.created_at,
    )


@router.post("/alimtalk", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
async def send_alimtalk(
    body: AlimTalkRequest,
    current_user: CurrentUser = Depends(RequirePermission("notifications", "write")),
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    message = NotificationMessage(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        channel="alimtalk",
        recipient_phone=body.recipient_phone,
        template_code=body.template_code,
        message=body.message,
        payload_json=body.payload,
        status="sent",
        external_ref=f"alim_{secrets.token_hex(8)}",
        sent_at=datetime.now(UTC),
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return _to_response(message)
