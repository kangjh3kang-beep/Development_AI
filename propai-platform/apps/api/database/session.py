"""비동기 데이터베이스 세션 관리.

SQLAlchemy async 엔진 + asyncpg 기반.
멀티테넌트 RLS를 위해 세션마다 app.current_tenant를 설정한다.
"""

from collections.abc import AsyncGenerator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from apps.api.config import get_settings

settings = get_settings()

# 메인 PostgreSQL + PostGIS 엔진
# Supabase pgBouncer 사용 시 prepared statements 비활성화 필요
_connect_args = {}
if settings.db_use_pgbouncer:
    _connect_args["statement_cache_size"] = 0
    _connect_args["prepared_statement_cache_size"] = 0

engine = create_async_engine(
    settings.database_url,
    pool_size=min(settings.db_pool_size, 10),  # Supabase 무료 티어: 최대 15 커넥션
    max_overflow=min(settings.db_max_overflow, 5),
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    echo=settings.debug,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

# TimescaleDB 엔진 (시계열 데이터용)
timescale_engine = create_async_engine(
    settings.timescale_url,
    pool_size=5,
    max_overflow=5,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    echo=settings.debug,
    pool_pre_ping=True,
)

# 세션 팩토리
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

TimescaleSessionLocal = async_sessionmaker(
    bind=timescale_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """요청별 DB 세션을 제공한다. FastAPI Depends로 사용."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_tenant_db(tenant_id: UUID) -> AsyncGenerator[AsyncSession, None]:
    """테넌트 격리된 DB 세션을 제공한다.

    PostgreSQL RLS 정책이 app.current_tenant 설정값을 기준으로
    행 수준 격리를 수행한다.
    """
    async with AsyncSessionLocal() as session:
        try:
            # RLS 정책용 테넌트 ID 설정
            await session.execute(
                text("SET LOCAL app.current_tenant = :tenant_id"),
                {"tenant_id": str(tenant_id)},
            )
            yield session
        finally:
            await session.close()


async def get_timescale_db() -> AsyncGenerator[AsyncSession, None]:
    """TimescaleDB 세션을 제공한다. 시계열 데이터 전용."""
    async with TimescaleSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
