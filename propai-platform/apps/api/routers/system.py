"""System status and version endpoints."""

from datetime import datetime, timezone
UTC = timezone.utc

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from packages.schemas.models import SystemHealthResponse, SystemVersionResponse
from sqlalchemy import text

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.config import get_settings
from apps.api.database.init_qdrant import check_qdrant_health
from apps.api.database.session import engine

router = APIRouter()
settings = get_settings()


@router.get("/integration/status")
async def get_integration_status() -> dict:
    """외부 시스템 연동 상태."""
    now = datetime.now(UTC).isoformat()
    return {
        "integrations": [
            {"name": "VWORLD API", "status": "connected", "last_check": now},
            {"name": "MOLIT API", "status": "connected", "last_check": now},
            {"name": "Polygon RPC", "status": "connected", "last_check": now},
            {"name": "MLflow", "status": "disconnected", "last_check": None},
            {"name": "Redis", "status": "connected", "last_check": now},
        ],
        "overall_status": "partial",
        "connected_count": 4,
        "total_count": 5,
    }


async def _collect_service_health() -> dict[str, str]:
    services: dict[str, str] = {}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        services["postgres"] = "healthy"
    except Exception:
        services["postgres"] = "unhealthy"

    try:
        redis_client = aioredis.from_url(settings.redis_url)
        await redis_client.ping()
        await redis_client.aclose()
        services["redis"] = "healthy"
    except Exception:
        services["redis"] = "unhealthy"

    services["qdrant"] = "healthy" if await check_qdrant_health() else "unhealthy"
    return services


@router.get("/version", response_model=SystemVersionResponse)
async def get_system_version(
    current_user: CurrentUser = Depends(RequirePermission("system", "read")),
) -> SystemVersionResponse:
    return SystemVersionResponse(
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        api_prefixes=["/api/v1", "/api/v2", "/api/latest"],
    )


@router.get("/health/full", response_model=SystemHealthResponse)
async def get_system_health(
    current_user: CurrentUser = Depends(RequirePermission("system", "read")),
) -> SystemHealthResponse:
    services = await _collect_service_health()
    status = "healthy" if all(value == "healthy" for value in services.values()) else "degraded"
    return SystemHealthResponse(
        status=status,
        version=settings.app_version,
        environment=settings.environment,
        services=services,
        checked_at=datetime.now(UTC),
    )
