"""성장 뇌(MemoryHub) — 부팅 시 agent_memories 테이블 멱등 보장.

growth/schema_guard.ensure_schema 선례를 그대로 따른다(이 플랫폼은 alembic CLI 비번
interpolation 이슈로 신규 테이블을 부팅 schema_guard로 보장하는 게 표준). CREATE TABLE/
INDEX IF NOT EXISTS 만 사용(파괴적 변경 없음)·best-effort(실패해도 호출경로 불변).

⚠️ 컬럼은 app/models/memory.py(AgentMemory ORM)와 정합 유지. ★project_id는 FK 없이 uuid
컬럼으로만 생성(growth 테이블 선례 — 부팅 게이트는 FK 의존 실패를 피한다. app레벨 FK는 ORM에).
이 테이블이 없으면 expert_panel·specialist 의 자동 기억저장(ingest)이 db.add 단계서 실패한다.
"""

from __future__ import annotations

import contextlib
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 최초 1회만 실행하기 위한 프로세스 로컬 가드(growth schema_guard 선례).
_MEMORY_SCHEMA_READY = False

_AGENT_MEMORIES_DDL = """
CREATE TABLE IF NOT EXISTS agent_memories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid,
    session_id varchar(100),
    domain varchar(50) NOT NULL,
    source_type varchar(50) NOT NULL,
    summary text NOT NULL,
    qdrant_point_ids jsonb DEFAULT '[]'::jsonb,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
)
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_am_domain ON agent_memories (domain)",
    "CREATE INDEX IF NOT EXISTS idx_am_session ON agent_memories (session_id)",
    "CREATE INDEX IF NOT EXISTS idx_am_project ON agent_memories (project_id)",
    "CREATE INDEX IF NOT EXISTS idx_am_created ON agent_memories (created_at)",
]


async def ensure_memory_schema(db: AsyncSession, force: bool = False) -> bool:
    """agent_memories 테이블·인덱스를 멱등 보장한다. 성공 시 True.

    부팅 시 1회 호출(growth schema_guard 인접). 실패는 graceful(rollback 후 False) —
    Qdrant/임베딩 키가 없어도 DB 테이블만큼은 준비해 둔다(ingest write 측 unblock).
    """
    global _MEMORY_SCHEMA_READY
    if _MEMORY_SCHEMA_READY and not force:
        return True
    try:
        await db.execute(text(_AGENT_MEMORIES_DDL))
        for ddl in _INDEXES:
            await db.execute(text(ddl))
        await db.commit()
        _MEMORY_SCHEMA_READY = True
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("memory schema_guard 실패: %s", str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return False
