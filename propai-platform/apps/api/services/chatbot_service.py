"""Deterministic chatbot session service for G95."""

from datetime import UTC, datetime

UTC = UTC
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.phase_g_chatbot import ChatbotMessage, ChatbotSession

_DOMAIN_ACTIONS = {
    "investment": [
        "refresh underwriting downside cases",
        "confirm debt sizing and covenant headroom",
        "prepare LP memo and key sensitivities",
    ],
    "construction": [
        "review schedule risk and critical path",
        "check contractor coverage and work packages",
        "reconcile capex with recent field issues",
    ],
    "design": [
        "validate massing assumptions and area efficiency",
        "review code constraints before concept freeze",
        "capture design revisions in the report set",
    ],
    "regulation": [
        "confirm zoning and permit prerequisites",
        "map open legal questions to source regulations",
        "prepare a regulator-facing compliance summary",
    ],
    "general": [
        "define the decision to make this week",
        "pull the missing source data before escalation",
        "summarize owners, risks, and next checkpoints",
    ],
}


class ChatbotService:
    """Persist chatbot conversations and generate deterministic replies."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _session_title(domain: str) -> str:
        return f"{domain.replace('_', ' ').title()} advisory"

    @staticmethod
    def _token_estimate(text: str) -> int:
        return max(1, len(text.split()) * 3)

    @staticmethod
    def _reply(domain: str, content: str) -> tuple[str, list[str]]:
        actions = _DOMAIN_ACTIONS.get(domain, _DOMAIN_ACTIONS["general"])
        excerpt = " ".join(content.split())[:180]
        reply = (
            f"Domain focus: {domain}. Prompt captured: {excerpt}. "
            f"Recommended next steps: {actions[0]}; {actions[1]}; {actions[2]}."
        )
        return reply, actions

    async def create_session(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        project_id: UUID | None,
        domain: str,
        title: str | None,
        model_name: str,
    ) -> ChatbotSession:
        session = ChatbotSession(
            tenant_id=tenant_id,
            user_id=user_id,
            project_id=project_id,
            domain=domain,
            title=title or self._session_title(domain),
            model_name=model_name,
            context_json={"domain": domain},
            last_activity_at=datetime.now(UTC),
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def list_sessions(self, *, tenant_id: UUID, user_id: UUID) -> list[ChatbotSession]:
        result = await self.db.execute(
            select(ChatbotSession)
            .where(
                ChatbotSession.tenant_id == tenant_id,
                ChatbotSession.user_id == user_id,
                ChatbotSession.is_archived.is_(False),
            )
            .order_by(ChatbotSession.last_activity_at.desc(), ChatbotSession.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_conversation(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        session_id: UUID,
    ) -> tuple[ChatbotSession, list[ChatbotMessage]] | None:
        session = await self.db.scalar(
            select(ChatbotSession).where(
                ChatbotSession.id == session_id,
                ChatbotSession.tenant_id == tenant_id,
                ChatbotSession.user_id == user_id,
            )
        )
        if session is None:
            return None

        messages_result = await self.db.execute(
            select(ChatbotMessage)
            .where(ChatbotMessage.session_id == session_id)
            .order_by(ChatbotMessage.sequence_number.asc(), ChatbotMessage.created_at.asc())
        )
        return session, list(messages_result.scalars().all())

    async def send_message(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        session_id: UUID,
        content: str,
    ) -> tuple[ChatbotSession, ChatbotMessage, ChatbotMessage]:
        conversation = await self.get_conversation(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        if conversation is None:
            raise ValueError("Chatbot session not found")

        session, _ = conversation
        user_token_count = self._token_estimate(content)
        assistant_content, actions = self._reply(session.domain, content)
        assistant_token_count = self._token_estimate(assistant_content)

        user_message = ChatbotMessage(
            session_id=session.id,
            role="user",
            content=content,
            token_count=user_token_count,
            sequence_number=session.message_count + 1,
        )
        assistant_message = ChatbotMessage(
            session_id=session.id,
            role="assistant",
            content=assistant_content,
            token_count=assistant_token_count,
            tool_calls_json={"suggested_actions": actions},
            sequence_number=session.message_count + 2,
        )
        session.message_count += 2
        session.total_tokens += user_token_count + assistant_token_count
        session.last_activity_at = datetime.now(UTC)
        session.context_json = {
            **(session.context_json or {}),
            "last_prompt": content[:200],
            "suggested_actions": actions,
        }

        self.db.add(user_message)
        self.db.add(assistant_message)
        await self.db.commit()
        await self.db.refresh(session)
        await self.db.refresh(user_message)
        await self.db.refresh(assistant_message)
        return session, user_message, assistant_message
