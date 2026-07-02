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

    P2-14 레이트리밋: ① IP당 동시 연결/분당 시도 상한(accept 전 거부 — 비인증 점유 차단)
    ② 초기 인증 메시지 10초 타임아웃(무한 대기 점유 차단) ③ 테넌트당 분당 실행 상한
    (연결당 7단계 오케스트레이터=LLM 비용 보호). slowapi 는 WS 미지원이라 전용 리미터.
    """
    import asyncio

    from apps.api.rate_limit import ws_analyze_limiter, ws_client_ip

    # 리버스프록시 배포에선 WS_TRUST_XFF=true 로 X-Forwarded-For 첫 홉 사용(미설정=직결 IP,
    # 스푸핑 방어 기본값 — ws_client_ip docstring 참조).
    client_ip = ws_client_ip(
        websocket.headers.get("x-forwarded-for"),
        websocket.client.host if websocket.client else None)
    if not ws_analyze_limiter.try_connect(client_ip):
        # accept 전 거부 — 핸드셰이크 단계에서 차단(자원 미소모).
        await websocket.close(code=4429)
        logger.warning("WS 연결 레이트리밋 거부", ip=client_ip, project_id=str(project_id))
        return

    await websocket.accept()
    logger.info("WebSocket 연결", project_id=str(project_id))

    try:
        # 클라이언트에서 JWT 토큰 및 시작 요청 수신(10초 내 미도착 시 점유 차단)
        try:
            init_msg = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
        except TimeoutError:
            await websocket.close(code=4408)
            return
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

        # 테넌트 실행 예산(분당) — 오케스트레이터는 고비용(LLM)이라 별도 상한.
        if not ws_analyze_limiter.try_run(str(tenant_id)):
            await websocket.send_json({"error": "실행 횟수 제한을 초과했습니다. 잠시 후 다시 시도하세요."})
            await websocket.close(code=4429)
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
    finally:
        # 동시 연결 슬롯 반환(정상/오류/타임아웃 모든 경로).
        ws_analyze_limiter.release(client_ip)
