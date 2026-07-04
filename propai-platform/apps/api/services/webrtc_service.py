"""WebRTC 영상 감리 세션 관리 서비스 (G113).

WebRTC 세션 생명주기 관리:
- 세션 생성/조회/종료
- SDP Offer/Answer 처리
- ICE candidate 관리 (3회 재시도 + 지수 백오프)
- 활성 세션 목록 조회
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

UTC = UTC
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy import select

from apps.api.config import get_settings
from apps.api.database.models.webrtc_session import WebRTCSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

_ICE_MAX_RETRIES = 3
_ICE_BASE_DELAY_SEC = 0.5


class WebRTCService:
    """WebRTC 영상 감리 세션 관리 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    # ── SDP 처리 ──

    @staticmethod
    def sanitize_sdp(sdp_offer: str) -> str:
        """SDP 포맷 브라우저별 파편화 대응 (줄바꿈 CR+LF 표준 통일)."""
        normalized = sdp_offer.replace('\r\n', '\n').replace('\n', '\r\n')
        return normalized

    @staticmethod
    def generate_sdp_answer(session_id: UUID) -> str:
        """SDP Answer를 생성한다 (미디어 서버 미연동 시 기본 응답)."""
        return f"v=0\r\no=propai-webrtc {session_id} 2 IN IP4 0.0.0.0\r\ns=-\r\n"

    # ── 세션 관리 ──

    async def create_session(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        user_id: UUID,
    ) -> WebRTCSession:
        """새 WebRTC 감리 세션을 생성한다."""
        session = WebRTCSession(
            tenant_id=tenant_id,
            project_id=project_id,
            initiator_user_id=user_id,
            status="waiting",
            started_at=datetime.now(UTC),
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        logger.info("WebRTC 세션 생성", session_id=str(session.id), project_id=str(project_id))
        return session

    async def get_session(
        self,
        session_id: UUID,
        tenant_id: UUID,
    ) -> WebRTCSession | None:
        """세션을 조회한다."""
        result = await self.db.execute(
            select(WebRTCSession).where(
                WebRTCSession.id == session_id,
                WebRTCSession.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_active_sessions(
        self,
        tenant_id: UUID,
        project_id: UUID | None = None,
    ) -> list[WebRTCSession]:
        """활성 세션 목록을 조회한다."""
        stmt = select(WebRTCSession).where(
            WebRTCSession.tenant_id == tenant_id,
            WebRTCSession.status.in_(["waiting", "active"]),
        )
        if project_id is not None:
            stmt = stmt.where(WebRTCSession.project_id == project_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def handle_offer(
        self,
        *,
        session_id: UUID,
        tenant_id: UUID,
        sdp: str,
    ) -> tuple[WebRTCSession, str]:
        """SDP Offer를 수신하고 Answer를 반환한다."""
        session = await self.get_session(session_id, tenant_id)
        if session is None:
            raise ValueError("세션을 찾을 수 없습니다")

        session.sdp_offer = self.sanitize_sdp(sdp)
        session.status = "active"
        sdp_answer = self.generate_sdp_answer(session.id)
        session.sdp_answer = sdp_answer

        await self.db.commit()
        await self.db.refresh(session)
        logger.info("SDP Offer 처리 완료", session_id=str(session_id))
        return session, sdp_answer

    async def handle_ice_candidate(
        self,
        *,
        session_id: UUID,
        tenant_id: UUID,
        candidate: dict,
    ) -> tuple[bool, int]:
        """ICE candidate를 수신한다 (3회 재시도 + 지수 백오프)."""
        session = await self.get_session(session_id, tenant_id)
        if session is None:
            raise ValueError("세션을 찾을 수 없습니다")

        for attempt in range(1, _ICE_MAX_RETRIES + 1):
            try:
                existing = session.ice_candidates_json or {"candidates": []}
                existing["candidates"].append(candidate)
                session.ice_candidates_json = existing
                session.ice_retry_count = attempt
                await self.db.flush()
                logger.info("ICE candidate 전송 성공", session_id=str(session_id), attempt=attempt)
                await self.db.commit()
                return True, attempt
            except Exception as e:
                delay = _ICE_BASE_DELAY_SEC * (2 ** (attempt - 1))
                logger.warning("ICE candidate 전송 실패", attempt=attempt, error=str(e))
                if attempt < _ICE_MAX_RETRIES:
                    await asyncio.sleep(delay)

        logger.error("ICE candidate 전송 최종 실패", session_id=str(session_id))
        return False, _ICE_MAX_RETRIES

    async def end_session(
        self,
        session_id: UUID,
        tenant_id: UUID,
    ) -> WebRTCSession | None:
        """세션을 종료한다."""
        session = await self.get_session(session_id, tenant_id)
        if session is None:
            return None

        session.status = "ended"
        session.ended_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(session)
        logger.info("WebRTC 세션 종료", session_id=str(session_id))
        return session

    @staticmethod
    def calculate_session_duration(session: WebRTCSession) -> float | None:
        """세션 지속 시간을 초 단위로 반환한다."""
        if session.started_at and session.ended_at:
            return (session.ended_at - session.started_at).total_seconds()
        return None
