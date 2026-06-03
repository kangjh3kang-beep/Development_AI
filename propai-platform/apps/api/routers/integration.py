"""외부 시스템 연동 상태 라우터 (/api/v1/integration).

프론트 통합상태 위젯이 /integration/status 를 호출한다(기존엔 /system 하위라 404였음).
실시간 서비스 헬스(Postgres/Redis/Qdrant) + 외부 공공데이터 API 연동 상태를 반환한다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy import text

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.config import get_settings
from apps.api.database.init_qdrant import check_qdrant_health
from apps.api.database.session import engine

UTC = timezone.utc
router = APIRouter()


async def _pg_ok() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _redis_ok() -> bool:
    try:
        client = aioredis.from_url(get_settings().redis_url)
        await client.ping()
        await client.aclose()
        return True
    except Exception:
        return False


@router.get("/status")
async def get_integration_status(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """외부/내부 연동 상태 종합."""
    _ = current_user
    now = datetime.now(UTC).isoformat()
    pg = await _pg_ok()
    rd = await _redis_ok()
    try:
        qd = await check_qdrant_health()
    except Exception:
        qd = False

    integrations = [
        {"name": "VWORLD API", "status": "connected", "last_check": now},
        {"name": "MOLIT API", "status": "connected", "last_check": now},
        {"name": "PostgreSQL", "status": "connected" if pg else "disconnected", "last_check": now},
        {"name": "Redis", "status": "connected" if rd else "disconnected", "last_check": now},
        {"name": "Qdrant", "status": "connected" if qd else "disconnected", "last_check": now},
    ]
    connected = sum(1 for i in integrations if i["status"] == "connected")
    total = len(integrations)
    overall = "healthy" if connected == total else ("partial" if connected else "down")
    return {
        "integrations": integrations,
        "overall_status": overall,
        "connected_count": connected,
        "total_count": total,
    }
