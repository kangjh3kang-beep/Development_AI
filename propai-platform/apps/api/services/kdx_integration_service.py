"""KDX integration pipeline service."""

from datetime import datetime, timedelta, timezone, UTC
UTC = UTC
from uuid import UUID

import structlog
from packages.schemas.models import KDXMetricSnapshot, KDXOverviewResponse, KDXTelemetryLogResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.kdx_market_metric import KDXMarketMetric
from apps.api.database.models.kdx_telemetry_log import KDXTelemetryLog

logger = structlog.get_logger(__name__)


class KDXIntegrationService:
    """KDX 통합 데이터 파이프라인 처리를 담당하는 서비스 클래스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _connection_status(*, latest_seen_at: datetime | None) -> str:
        if latest_seen_at is None:
            return "idle"

        age_seconds = (datetime.now(UTC) - latest_seen_at).total_seconds()
        if age_seconds <= 300:
            return "stable"
        if age_seconds <= 1800:
            return "degraded"
        return "stale"

    @staticmethod
    def _throughput_tps(*, recent_log_count: int, recent_metric_count: int) -> int:
        return recent_log_count * 4 + recent_metric_count * 8

    @staticmethod
    def _latency_ms(*, latest_seen_at: datetime | None) -> int:
        if latest_seen_at is None:
            return 0
        return max(0, int((datetime.now(UTC) - latest_seen_at).total_seconds() * 1000))

    async def process_webhook(self, payload: dict, tenant_id: UUID) -> KDXTelemetryLog:
        """KDX에서 전송된 실시간 텔레메트리 웹훅을 수신 및 기록한다."""
        source = payload.get("source", "KDX-Webhook")
        event_type = payload.get("event_type", "unknown")

        telemetry_log = KDXTelemetryLog(
            tenant_id=tenant_id,
            source=source,
            event_type=event_type,
            payload=payload,
            status="processed",
        )
        self.db.add(telemetry_log)
        await self.db.flush()

        logger.info(
            "KDX 웹훅 처리 완료",
            log_id=str(telemetry_log.id),
            event=event_type,
            source=source
        )
        return telemetry_log

    async def record_market_metric(
        self,
        region_code: str,
        metric_type: str,
        value: float,
        currency: str,
        tenant_id: UUID
    ) -> KDXMarketMetric:
        """KDX 시장 지표를 시계열 지표 테이블에 적재한다."""
        metric = KDXMarketMetric(
            tenant_id=tenant_id,
            region_code=region_code,
            metric_type=metric_type,
            value=value,
            currency=currency,
        )
        self.db.add(metric)
        await self.db.flush()

        logger.debug(
            "KDX 시장지표 기록",
            metric_id=str(metric.id),
            region=region_code,
            val=value
        )
        return metric

    async def overview(
        self,
        *,
        tenant_id: UUID,
        region_code: str | None,
        log_limit: int = 5,
    ) -> KDXOverviewResponse:
        latest_metric = await self.db.scalar(
            select(KDXMarketMetric)
            .where(
                KDXMarketMetric.tenant_id == tenant_id,
                *((
                    KDXMarketMetric.region_code == region_code,
                ) if region_code else ()),
            )
            .order_by(KDXMarketMetric.created_at.desc())
            .limit(1)
        )

        logs = list(
            (
                await self.db.scalars(
                    select(KDXTelemetryLog)
                    .where(KDXTelemetryLog.tenant_id == tenant_id)
                    .order_by(KDXTelemetryLog.created_at.desc())
                    .limit(log_limit)
                )
            ).all()
        )

        recent_window = datetime.now(UTC) - timedelta(minutes=5)
        recent_log_count = int(
            (
                await self.db.scalar(
                    select(func.count(KDXTelemetryLog.id)).where(
                        KDXTelemetryLog.tenant_id == tenant_id,
                        KDXTelemetryLog.created_at >= recent_window,
                    )
                )
            )
            or 0
        )
        recent_metric_count = int(
            (
                await self.db.scalar(
                    select(func.count(KDXMarketMetric.id)).where(
                        KDXMarketMetric.tenant_id == tenant_id,
                        KDXMarketMetric.created_at >= recent_window,
                        *((
                            KDXMarketMetric.region_code == region_code,
                        ) if region_code else ()),
                    )
                )
            )
            or 0
        )

        latest_seen_at = (
            latest_metric.created_at
            if latest_metric is not None
            else (logs[0].created_at if logs else None)
        )

        return KDXOverviewResponse(
            connection_status=self._connection_status(latest_seen_at=latest_seen_at),
            throughput_tps=self._throughput_tps(
                recent_log_count=recent_log_count,
                recent_metric_count=recent_metric_count,
            ),
            data_sync_latency_ms=self._latency_ms(latest_seen_at=latest_seen_at),
            latest_metric=(
                KDXMetricSnapshot(
                    region_code=latest_metric.region_code,
                    metric_type=latest_metric.metric_type,
                    value=latest_metric.value,
                    currency=latest_metric.currency,
                    recorded_at=latest_metric.created_at,
                )
                if latest_metric is not None
                else None
            ),
            recent_logs=[
                KDXTelemetryLogResponse(
                    id=log.id,
                    source=log.source,
                    event_type=log.event_type,
                    status=log.status,
                    created_at=log.created_at,
                )
                for log in logs
            ],
        )
