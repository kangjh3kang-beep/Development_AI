"""Phase 2 Lineage DAG — 분석 파생 그래프(어떤 prior에서 파생됐는지) 엣지 원장.

analysis_ledger와 동일한 lazy `_ensure` 패턴(alembic from-scratch 깨짐 회피).
순수 기록/조회 — 결정론 코어 불변, additive. 모순탐지 결과(개수·심각도)를 엣지에 동반.
"""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_LINEAGE_DDL = (
    "CREATE TABLE IF NOT EXISTS analysis_lineage ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  tenant_id text,"
    "  child_hash text NOT NULL,"
    "  child_type text NOT NULL,"
    "  parent_hash text NOT NULL,"
    "  parent_type text NOT NULL,"
    "  relation text NOT NULL DEFAULT 'derived_from',"
    "  contradiction_count int NOT NULL DEFAULT 0,"
    "  max_severity text,"
    "  created_at timestamptz DEFAULT now()"
    ")"
)
_LINEAGE_IDX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_lineage_edge "
    "ON analysis_lineage(child_hash, parent_hash, relation)",
    "CREATE INDEX IF NOT EXISTS idx_lineage_child ON analysis_lineage(tenant_id, child_hash)",
    "CREATE INDEX IF NOT EXISTS idx_lineage_parent ON analysis_lineage(tenant_id, parent_hash)",
)


async def _ensure(db) -> None:
    from sqlalchemy import text
    await db.execute(text(_LINEAGE_DDL))
    for ix in _LINEAGE_IDX:
        await db.execute(text(ix))


async def record_edge(
    *, child_hash: str, child_type: str, parent_hash: str, parent_type: str,
    tenant_id: str | None = None, relation: str = "derived_from",
    contradiction_count: int = 0, max_severity: str | None = None,
) -> dict[str, Any]:
    """파생 엣지 1건 기록(멱등 upsert). self-edge/빈 해시는 거부."""
    if not child_hash or not parent_hash:
        return {"ok": False, "message": "child_hash·parent_hash 필수"}
    if child_hash == parent_hash:
        return {"ok": False, "skipped": True, "message": "self-edge 금지"}
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure(db)
            await db.execute(text(
                "INSERT INTO analysis_lineage"
                "(tenant_id, child_hash, child_type, parent_hash, parent_type, relation,"
                " contradiction_count, max_severity)"
                " VALUES (:tid,:ch,:ct,:ph,:pt,:rel,:cc,:ms)"
                " ON CONFLICT (child_hash, parent_hash, relation) DO UPDATE SET"
                "   contradiction_count = EXCLUDED.contradiction_count,"
                "   max_severity = EXCLUDED.max_severity"),
                {"tid": tenant_id, "ch": child_hash, "ct": child_type, "ph": parent_hash,
                 "pt": parent_type, "rel": relation, "cc": int(contradiction_count),
                 "ms": max_severity})
            await db.commit()
            return {"ok": True, "child_hash": child_hash, "parent_hash": parent_hash,
                    "relation": relation}
    except Exception as e:  # noqa: BLE001
        logger.warning("lineage 엣지 기록 실패", err=str(e)[:160])
        return {"ok": False, "message": str(e)[:160]}


async def get_parents(*, child_hash: str, tenant_id: str | None = None) -> list[dict[str, Any]]:
    """직계 부모(파생 원천) 엣지 목록."""
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure(db)
            tenant_sql = "tenant_id = :tid" if tenant_id else "tenant_id IS NULL"
            rows = (await db.execute(text(
                f"SELECT parent_hash, parent_type, relation, contradiction_count, max_severity,"
                f" created_at FROM analysis_lineage "
                f"WHERE {tenant_sql} AND child_hash = :ch ORDER BY created_at"),
                {"tid": tenant_id, "ch": child_hash})).all()
            return [{"parent_hash": r[0], "parent_type": r[1], "relation": r[2],
                     "contradiction_count": int(r[3]), "max_severity": r[4],
                     "created_at": str(r[5])} for r in rows]
    except Exception as e:  # noqa: BLE001
        logger.warning("lineage 부모 조회 실패", err=str(e)[:160])
        return []


async def get_lineage(*, content_hash: str, tenant_id: str | None = None,
                      max_depth: int = 5) -> dict[str, Any]:
    """조상(파생 원천)을 max_depth까지 BFS로 수집 — 파생 계보 그래프."""
    ancestors: list[dict[str, Any]] = []
    seen: set[str] = set()
    frontier = [content_hash]
    depth = 0
    while frontier and depth < max_depth:
        nxt: list[str] = []
        for h in frontier:
            for edge in await get_parents(child_hash=h, tenant_id=tenant_id):
                ph = edge["parent_hash"]
                ancestors.append({"child_hash": h, **edge})
                if ph not in seen:
                    seen.add(ph)
                    nxt.append(ph)
        frontier = nxt
        depth += 1
    return {"content_hash": content_hash, "depth": depth, "ancestors": ancestors}
