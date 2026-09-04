"""Alembic 마이그레이션 환경 설정.

비동기 엔진(asyncpg)과 SQLAlchemy ORM 모델을 연결한다.
RLS 정책과 TimescaleDB 하이퍼테이블은 마이그레이션 스크립트에서 수동 적용한다.
"""
import asyncio
import logging
import re
import sys
import uuid as _uuid
from logging.config import fileConfig
from pathlib import Path
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.sql import text

# 루트 폴더(propai-platform)를 sys.path에 추가하여 apps 모듈 임포트 가능하게 함
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from apps.api.config import get_settings
from apps.api.database.models import Base  # noqa: E402 — 모든 모델 임포트

_logger = logging.getLogger("alembic.env")

# Alembic Config 객체
config = context.config

# 로깅 설정
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 메타데이터 — autogenerate 대상
target_metadata = Base.metadata


def _normalize_db_url(url: str) -> str:
    """Supabase PGBouncer(트랜잭션 풀러, 6543) 호환 — database/session.py._fix_supabase_url와 동일.

    ★배포 시 컨테이너가 이 URL로 마이그레이션을 돌린다. 정규화 없이는 asyncpg가 'postgres.<proj>'
    사용자명의 '.'을 파싱하지 못하거나 prepared statement가 풀러에서 충돌해 마이그레이션이 실패한다.
    """
    if "pooler.supabase.com" in url and "postgres." in url:
        url = re.sub(
            r"(postgresql\+asyncpg://)postgres\.([^:]+)", r"\1postgres%2E\2", url
        )
    if "?" not in url:
        url += "?prepared_statement_cache_size=0"
    elif "prepared_statement_cache_size" not in url:
        url += "&prepared_statement_cache_size=0"
    return url


# DB URL을 환경 변수에서 동적으로 설정(Supabase 풀러 호환 정규화)
# ★configparser 이스케이프: URL의 '%'(인코딩된 사용자명 %2E·비밀번호 %XX 등)를 '%%'로 escape
#   하지 않으면 alembic Config(configparser)가 인터폴레이션 문법으로 오인해 즉시 실패한다.
#   set 시 %%로 저장 → get 시 %로 복원 → asyncpg가 최종 디코드(표준 관행).
settings = get_settings()
config.set_main_option(
    "sqlalchemy.url", _normalize_db_url(settings.database_url).replace("%", "%%")
)


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
        # PGBouncer 트랜잭션 풀러 호환(session.py와 동일): 고정이름 prepared statement 충돌 방지.
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__alembic_{_uuid.uuid4().hex}__",
        },
    )

    async with connectable.connect() as connection:
        # PostGIS 확장 — 이미 설치된 환경(Supabase 등)에선 no-op. 권한/미지원으로 실패해도
        # 마이그레이션 자체를 막지 않도록 비치명 처리(공간 마이그레이션은 자체적으로 요구사항 검증).
        for _ext in ("postgis", "postgis_topology"):
            try:
                await connection.execute(text(f"CREATE EXTENSION IF NOT EXISTS {_ext}"))
                await connection.commit()
            except Exception as exc:  # noqa: BLE001
                await connection.rollback()
                _logger.warning("확장 %s 생성 건너뜀(비치명): %s", _ext, str(exc)[:120])

        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """온라인 모드: DB에 직접 적용."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
