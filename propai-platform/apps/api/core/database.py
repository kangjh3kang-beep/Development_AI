import os

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

DB_PREFIX = os.getenv("DATABASE_URL", "postgresql+asyncpg://propai:secret@localhost:5432/propaidb")

# PGBouncer 환경: NullPool + statement_cache_size=0 — prepared statement 충돌 완전 방지
engine = create_async_engine(
    DB_PREFIX,
    poolclass=NullPool,
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0
    }
)
