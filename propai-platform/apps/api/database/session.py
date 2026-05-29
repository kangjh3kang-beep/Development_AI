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
from sqlalchemy.pool import NullPool

from apps.api.config import get_settings

settings = get_settings()

# Supabase PGBouncer 호환: prepared statements 완전 비활성화
_connect_args: dict = {
    "statement_cache_size": 0,
    "prepared_statement_cache_size": 0,
}


def _fix_supabase_url(url: str) -> str:
    """Supabase PGBouncer URL 호환 처리.

    1. 사용자명의 '.'을 URL 인코딩(%2E)으로 치환 (asyncpg 파서 호환)
    2. prepared_statement_cache_size=0 쿼리 파라미터 강제 추가 (PGBouncer 호환)
    """
    if "pooler.supabase.com" in url and "postgres." in url:
        import re
        url = re.sub(
            r"(postgresql\+asyncpg://)postgres\.([^:]+)",
            r"\1postgres%2E\2",
            url,
        )
    # PGBouncer 호환: prepared_statement_cache_size=0 쿼리 파라미터 추가
    if "?" not in url:
        url += "?prepared_statement_cache_size=0"
    elif "prepared_statement_cache_size" not in url:
        url += "&prepared_statement_cache_size=0"
    return url


# PGBouncer 환경: NullPool 사용 — prepared statement 충돌 완전 방지
# 매 요청마다 새 커넥션 생성/해제 (PGBouncer가 풀링 담당)
engine = create_async_engine(
    _fix_supabase_url(settings.database_url),
    poolclass=NullPool,
    echo=settings.debug,
    connect_args=_connect_args,
)

# TimescaleDB 엔진 (시계열 데이터용)
timescale_engine = create_async_engine(
    _fix_supabase_url(settings.timescale_url),
    poolclass=NullPool,
    echo=settings.debug,
    connect_args=_connect_args,
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
