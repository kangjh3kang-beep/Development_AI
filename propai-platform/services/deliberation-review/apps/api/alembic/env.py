"""Phase 0 — Alembic env(async/asyncpg). review 스키마 + PostGIS 베이스."""
from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.db.base import SCHEMA, Base
import app.models  # noqa: F401 — 프로브 모델 등록
import app.db.models  # noqa: F401 — R0 모델 등록(메타데이터 채움)
from app.settings import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata


def _configure(connection=None, url=None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        version_table_schema=SCHEMA,
        include_schemas=True,
        compare_type=True,
    )


def run_migrations_offline() -> None:
    _configure(url=settings.database_url)
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        {"sqlalchemy.url": settings.database_url}, prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
