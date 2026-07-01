"""Alembic 마이그레이션 환경 설정.

비동기 엔진(asyncpg)과 SQLAlchemy ORM 모델을 연결한다.
RLS 정책과 TimescaleDB 하이퍼테이블은 마이그레이션 스크립트에서 수동 적용한다.
"""
import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path
from typing import Any

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.sql import text

from alembic import context

# 루트 폴더(propai-platform)를 sys.path에 추가하여 apps 모듈 임포트 가능하게 함
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from apps.api.config import get_settings
from apps.api.database.models import Base  # noqa: E402 — 모든 모델 임포트

# Alembic Config 객체
config = context.config

# 로깅 설정
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 메타데이터 — autogenerate 대상
target_metadata = Base.metadata

# DB URL을 환경 변수에서 동적으로 설정
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    """오프라인 모드: SQL 스크립트만 생성."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Any) -> None:
    """마이그레이션 실행 (동기 컨텍스트 내)."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """비동기 마이그레이션 실행."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        # PostGIS 확장 활성화 (v53 필수 사항)
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis_topology"))
        await connection.commit()

        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """온라인 모드: DB에 직접 적용."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
