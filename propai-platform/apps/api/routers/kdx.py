"""KDX 통합 파이프라인 REST 및 WebSocket 라우터."""

import asyncio
import json
import random

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from packages.schemas.models import KDXOverviewResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.kdx_integration_service import KDXIntegrationService

router = APIRouter()


class WebhookPayload(BaseModel):
    source: str
    event_type: str
    data: dict


class MetricPayload(BaseModel):
    region_code: str
    metric_type: str
    value: float
    currency: str = "KRW"


@router.post("/webhook")
async def receive_kdx_webhook(
    payload: WebhookPayload,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(RequirePermission("kdx", "write")),
):
    """KDX 웹훅 페이로드 수신 및 로깅 에이전트 엔드포인트."""
    service = KDXIntegrationService(db)
    telemetry = await service.process_webhook(payload.model_dump(), current_user.tenant_id)
    return {"status": "success", "log_id": str(telemetry.id)}


@router.post("/metrics")
async def record_kdx_metric(
    payload: MetricPayload,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(RequirePermission("kdx", "write")),
):
    """KDX 시장 지표 시계열 기록 엔드포인트."""
    service = KDXIntegrationService(db)
    metric = await service.record_market_metric(
        region_code=payload.region_code,
        metric_type=payload.metric_type,
        value=payload.value,
        currency=payload.currency,
        tenant_id=current_user.tenant_id,
    )
    return {"status": "success", "metric_id": str(metric.id)}


@router.get("/overview", response_model=KDXOverviewResponse)
async def get_kdx_overview(
    region_code: str | None = None,
    current_user: CurrentUser = Depends(RequirePermission("kdx", "read")),
    db: AsyncSession = Depends(get_db),
) -> KDXOverviewResponse:
    """KDX 모니터링 대시보드용 읽기 모델을 반환한다."""
    service = KDXIntegrationService(db)
    return await service.overview(
        tenant_id=current_user.tenant_id,
        region_code=region_code,
    )


@router.websocket("/stream")
async def kdx_websocket_endpoint(websocket: WebSocket):
    """프론트엔드 대시보드를 위한 KDX 실시간 시세 / 거래량 스트리밍 소켓."""
    await websocket.accept()
    try:
        while True:
            # TODO: 향후 레디스 PubSub 구독으로 연결
            data = {
                "event_type": "market_tick",
                "seoul_index": round(random.uniform(90.0, 110.0), 2),
                "transaction_volume": random.randint(10, 100),
                "timestamp": __import__("time").time()
            }
            await websocket.send_text(json.dumps(data))
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        pass
