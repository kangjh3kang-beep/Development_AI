import os

from sqlalchemy.ext.asyncio import create_async_engine

DB_PREFIX = os.getenv("DATABASE_URL", "postgresql+asyncpg://propai:secret@localhost:5432/propaidb")

# B08: AsyncPG 커넥션 풀 오버플로어 대응 (Pool/Max Overflow 상향)
# B09: statement_cache_size=0, prepared_statement_cache_size=0 강제 (PGBouncer 쿼리 충돌 방어)
engine = create_async_engine(
    DB_PREFIX,
    pool_size=100,
    max_overflow=50,
    pool_timeout=30.0,
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0
    }
)
