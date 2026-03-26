"""Chatbot router for G95."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from packages.schemas.models import (
    ChatbotConversationResponse,
    ChatbotMessageRequest,
    ChatbotMessageResponse,
    ChatbotReplyResponse,
    ChatbotSessionCreateRequest,
    ChatbotSessionResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.rate_limit import ai_limiter, limiter
from apps.api.services.chatbot_service import ChatbotService

router = APIRouter()


def _serialize_session(session) -> ChatbotSessionResponse:
    return ChatbotSessionResponse(
        session_id=session.id,
        project_id=session.project_id,
        domain=session.domain,
        title=session.title,
        message_count=session.message_count,
        total_tokens=session.total_tokens,
        model_name=session.model_name,
        last_activity_at=session.last_activity_at,
        created_at=session.created_at,
    )


def _serialize_message(message) -> ChatbotMessageResponse:
    return ChatbotMessageResponse(
        message_id=message.id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        token_count=message.token_count,
        sequence_number=message.sequence_number,
        created_at=message.created_at,
    )


@router.post("/sessions", response_model=ChatbotSessionResponse)
async def create_chatbot_session(
    body: ChatbotSessionCreateRequest,
    current_user: CurrentUser = Depends(RequirePermission("chatbot", "write")),
    db: AsyncSession = Depends(get_db),
) -> ChatbotSessionResponse:
    service = ChatbotService(db)
    session = await service.create_session(
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        project_id=body.project_id,
        domain=body.domain,
        title=body.title,
        model_name=body.model_name,
    )
    return _serialize_session(session)


@router.get("/sessions", response_model=list[ChatbotSessionResponse])
async def list_chatbot_sessions(
    current_user: CurrentUser = Depends(RequirePermission("chatbot", "read")),
    db: AsyncSession = Depends(get_db),
) -> list[ChatbotSessionResponse]:
    service = ChatbotService(db)
    sessions = await service.list_sessions(
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
    )
    return [_serialize_session(session) for session in sessions]


@router.get("/sessions/{session_id}", response_model=ChatbotConversationResponse)
async def get_chatbot_conversation(
    session_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("chatbot", "read")),
    db: AsyncSession = Depends(get_db),
) -> ChatbotConversationResponse:
    service = ChatbotService(db)
    conversation = await service.get_conversation(
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        session_id=session_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Chatbot session not found")

    session, messages = conversation
    return ChatbotConversationResponse(
        session=_serialize_session(session),
        messages=[_serialize_message(message) for message in messages],
    )


@router.post("/messages", response_model=ChatbotReplyResponse)
@limiter.limit(ai_limiter)
async def send_chatbot_message(
    request: Request,
    body: ChatbotMessageRequest,
    current_user: CurrentUser = Depends(RequirePermission("chatbot", "write")),
    db: AsyncSession = Depends(get_db),
) -> ChatbotReplyResponse:
    service = ChatbotService(db)
    try:
        session, user_message, assistant_message = await service.send_message(
            tenant_id=current_user.tenant_id,
            user_id=current_user.user_id,
            session_id=body.session_id,
            content=body.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ChatbotReplyResponse(
        session=_serialize_session(session),
        user_message=_serialize_message(user_message),
        assistant_message=_serialize_message(assistant_message),
    )
