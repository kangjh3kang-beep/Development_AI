import uuid

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_DEBUG,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    # Supabase pgbouncer(transaction pooling) 호환:
    #  - statement_cache_size=0: asyncpg 자체 statement 캐시 비활성화.
    #  - ★prepared_statement_name_func: SQLAlchemy asyncpg는 고정 이름(__asyncpg_stmt_N__)
    #    prepared statement를 쓰는데, pgbouncer가 풀링한 커넥션을 트랜잭션 간 재사용하면
    #    같은 이름이 이미 존재해 DuplicatePreparedStatementError 발생(관리자 키 저장 실패·
    #    간헐적 DB오류의 직접원인). 매번 고유(uuid) 이름을 부여해 충돌을 원천 차단한다.
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4().hex}__",
    },
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# 별칭: 일부 서비스/태스크가 async_session_factory 이름으로 세션 팩토리를 사용한다.
async_session_factory = AsyncSessionLocal

class Base(DeclarativeBase):
    """⚠️레거시 Base — 동결(P1-7). 새 모델은 canonical(apps/api/database/models Base)로.

    실사용 alembic(alembic.ini → database/migrations)은 canonical metadata 만 보므로
    여기 얹힌 모델(app/models/* 71테이블)은 autogenerate 비추적이며, canonical 과 같은
    테이블명 이중 정의가 19건(스테일 포함: 예 auth.User organization_id vs 실스키마
    tenant_id)이다. 동결은 tests/test_dual_base_freeze.py 가 CI 로 강제한다.
    전면 통합(스테일 정리 포함)은 별도 트랙.
    """

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
