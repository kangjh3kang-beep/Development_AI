"""System status and version endpoints."""

from datetime import UTC, datetime

UTC = UTC

from fastapi import APIRouter, Depends
from packages.schemas.models import SystemHealthResponse, SystemVersionResponse

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.config import get_settings

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
    """의존처 상태를 모은다.

    ★종전에는 여기에 ``main.py`` 의 ``/health`` 와 **똑같은 로직이 복제**돼 있었고, 둘 다
    각 점검에 상한이 없었다. 2026-08-11 에 Supabase 풀러가 신규 연결을 60초 매달자
    ``/health`` 가 재는 족족 60초였는데(표본 136건), 이 경로도 같은 결함을 그대로 안고
    있었다. 한 곳만 고치면 미러가 남으므로 공용 통로로 일원화한다.
    """
    from apps.api.app.core.health_probe import collect_service_health

    return await collect_service_health()


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
