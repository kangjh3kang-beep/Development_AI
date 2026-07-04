"""Phase 2 T2 — lineage 엣지(lineage.py) 통합테스트(실 Postgres, 미가용 시 skip).

Phase 1 통합테스트 패턴(engine.dispose()로 교차-이벤트루프 풀 재바인딩 후 inline DB체크).
유니크 해시로 테스트 간 격리 — tenant_id None 기본.
"""
import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def _db() -> bool:
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory, engine
        await engine.dispose()  # 교차-이벤트루프 풀 바인딩 초기화(테스트 격리 — 현재 루프 재바인딩)
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


async def test_record_edge_and_get_parents():
    if not await _db():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행")
    from app.services.ledger import lineage
    ch, ph = f"c{uuid.uuid4().hex}", f"p{uuid.uuid4().hex}"
    r = await lineage.record_edge(child_hash=ch, child_type="design_audit",
                                  parent_hash=ph, parent_type="design_audit",
                                  contradiction_count=2, max_severity="high")
    assert r["ok"] is True
    parents = await lineage.get_parents(child_hash=ch)
    assert any(p["parent_hash"] == ph and p["max_severity"] == "high" for p in parents)


async def test_record_edge_idempotent_upsert():
    if not await _db():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행")
    from app.services.ledger import lineage
    ch, ph = f"c{uuid.uuid4().hex}", f"p{uuid.uuid4().hex}"
    await lineage.record_edge(child_hash=ch, child_type="t", parent_hash=ph, parent_type="t",
                              contradiction_count=1, max_severity="low")
    await lineage.record_edge(child_hash=ch, child_type="t", parent_hash=ph, parent_type="t",
                              contradiction_count=3, max_severity="high")  # upsert
    parents = await lineage.get_parents(child_hash=ch)
    edges = [p for p in parents if p["parent_hash"] == ph]
    assert len(edges) == 1 and edges[0]["contradiction_count"] == 3   # 중복행 없이 갱신


async def test_self_edge_rejected():
    if not await _db():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행")
    from app.services.ledger import lineage
    h = f"h{uuid.uuid4().hex}"
    r = await lineage.record_edge(child_hash=h, child_type="t", parent_hash=h, parent_type="t")
    assert r["ok"] is False


async def test_get_lineage_walks_ancestors():
    if not await _db():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행")
    from app.services.ledger import lineage
    a, b, c = (f"h{uuid.uuid4().hex}" for _ in range(3))  # c→b→a
    await lineage.record_edge(child_hash=b, child_type="t", parent_hash=a, parent_type="t")
    await lineage.record_edge(child_hash=c, child_type="t", parent_hash=b, parent_type="t")
    g = await lineage.get_lineage(content_hash=c)
    anc = {e["parent_hash"] for e in g["ancestors"]}
    assert a in anc and b in anc
