"""Phase 0 — async 엔진/세션(asyncpg)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.settings import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True, future=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
