"""KDX 통합 파이프라인 REST 및 WebSocket 라우터."""

import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID
UTC = timezone.utc

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from packages.schemas.models import KDXOverviewResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.auth.jwt_handler import decode_token
from apps.api.database.models.kdx_market_metric import KDXMarketMetric
from apps.api.database.models.kdx_telemetry_log import KDXTelemetryLog
from apps.api.database.session import AsyncSessionLocal
from apps.api.database.session import get_db
from apps.api.config import get_settings
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


def _pick_metric_value(latest_by_type: dict[str, KDXMarketMetric], *candidate_types: str) -> float:
    for metric_type in candidate_types:
        metric = latest_by_type.get(metric_type)
        if metric is not None and metric.value is not None:
            return float(metric.value)
    return 0.0


async def _build_market_tick_payload(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    region_code: str | None = None,
) -> dict:
    metrics = (
        await db.execute(
            select(KDXMarketMetric)
            .where(
                KDXMarketMetric.tenant_id == tenant_id,
                *((
                    KDXMarketMetric.region_code == region_code,
                ) if region_code else ()),
            )
            .order_by(KDXMarketMetric.created_at.desc())
            .limit(100)
        )
    ).scalars().all()
    latest_by_type: dict[str, KDXMarketMetric] = {}
    for metric in metrics:
        latest_by_type.setdefault(metric.metric_type, metric)

    latest_log = (
        await db.execute(
            select(KDXTelemetryLog)
            .where(KDXTelemetryLog.tenant_id == tenant_id)
            .order_by(KDXTelemetryLog.created_at.desc())
            .limit(1)
        )
    ).scalars().first()

    timestamp = datetime.now(UTC).timestamp()
    if latest_log and latest_log.created_at is not None:
        timestamp = latest_log.created_at.timestamp()

    return {
        "event_type": "market_tick",
        "seoul_index": _pick_metric_value(
            latest_by_type,
            "seoul_index",
            "price_index",
            "avg_price_per_sqm",
        ),
        "transaction_volume": _pick_metric_value(
            latest_by_type,
            "transaction_volume",
            "volume",
            "deal_count",
        ),
        "timestamp": timestamp,
    }


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
    token = websocket.query_params.get("token", "").strip()
    region_code = websocket.query_params.get("region_code")
    if not token:
        await websocket.close(code=1008, reason="missing token")
        return

    settings = get_settings()
    try:
        token_payload = decode_token(token, settings)
        if token_payload.token_type != "access":
            await websocket.close(code=1008, reason="invalid token type")
            return
        tenant_id = UUID(token_payload.tenant_id)
    except Exception:
        await websocket.close(code=1008, reason="invalid token")
        return

    await websocket.accept()
    try:
        while True:
            async with AsyncSessionLocal() as db:
                data = await _build_market_tick_payload(
                    db,
                    tenant_id=tenant_id,
                    region_code=region_code,
                )
            await websocket.send_text(json.dumps(data))
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        pass
