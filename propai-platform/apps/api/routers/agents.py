"""에이전트 오케스트레이션 라우터.

7단계 파이프라인을 SSE 또는 WebSocket으로 스트리밍한다.
"""

import contextlib
from collections.abc import AsyncIterator
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from apps.api.agents.propai_orchestrator import PropAIOrchestrator
from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db
from apps.api.rate_limit import ai_limiter, limiter

logger = structlog.get_logger(__name__)
router = APIRouter()


class OrchestrateRequest(BaseModel):
    project_id: UUID


@router.post("/orchestrate")
@limiter.limit(ai_limiter)
async def orchestrate(
    request: Request,
    body: OrchestrateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """7단계 에이전트 파이프라인을 실행한다."""
    orchestrator = PropAIOrchestrator(db)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        async for event in orchestrator.run(
            project_id=body.project_id,
            tenant_id=current_user.tenant_id,
        ):
            yield {"event": event.event_type, "data": event.model_dump_json()}

    return EventSourceResponse(event_generator())


@router.websocket("/analyze/ws/{project_id}")
async def ws_orchestrate(websocket: WebSocket, project_id: UUID) -> None:
    """WebSocket 기반 에이전트 파이프라인 진행률 스트리밍.

    클라이언트 → 서버: {"action": "start", "token": "jwt_token"}
    서버 → 클라이언트: AgentStepEvent JSON
    """
    await websocket.accept()
    logger.info("WebSocket 연결", project_id=str(project_id))

    try:
        # 클라이언트에서 JWT 토큰 및 시작 요청 수신
        init_msg = await websocket.receive_json()
        token = init_msg.get("token", "")
        if not token:
            await websocket.send_json({"error": "JWT 토큰이 필요합니다"})
            await websocket.close(code=4001)
            return

        # JWT 검증
        from apps.api.auth.jwt_handler import decode_token

        try:
            payload = decode_token(token)
            tenant_id = UUID(payload.tenant_id)
        except Exception:
            await websocket.send_json({"error": "유효하지 않은 토큰입니다"})
            await websocket.close(code=4003)
            return

        # DB 세션 생성
        from apps.api.database.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            orchestrator = PropAIOrchestrator(db)

            await websocket.send_json({
                "event": "connected",
                "project_id": str(project_id),
            })

            # 오케스트레이터 실행 → WebSocket으로 브릿지
            async for event in orchestrator.run(
                project_id=project_id,
                tenant_id=tenant_id,
            ):
                await websocket.send_json({
                    "event": event.event_type,
                    "data": event.model_dump(),
                })

            await websocket.send_json({"event": "completed"})

    except WebSocketDisconnect:
        logger.info("WebSocket 연결 종료", project_id=str(project_id))
    except Exception:
        logger.exception("WebSocket 오류", project_id=str(project_id))
        with contextlib.suppress(Exception):
            await websocket.close(code=1011)
