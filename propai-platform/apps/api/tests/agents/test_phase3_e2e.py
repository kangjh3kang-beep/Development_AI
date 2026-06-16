"""Phase 3 e2e — record_specialist_result(T2) + coordinator→specialist→원장(T5) 실DB 검증.

Phase 1/2 패턴: engine.dispose() 루프격리 + inline DB체크 + 유니크 tenant 정리.
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


async def _cleanup(tid: str) -> None:
    from sqlalchemy import text
    from app.core.database import async_session_factory
    async with async_session_factory() as db:
        await db.execute(text("DELETE FROM analysis_lineage WHERE tenant_id = :t"), {"t": tid})
        await db.execute(text("DELETE FROM analysis_ledger WHERE tenant_id = :t"), {"t": tid})
        await db.commit()


async def test_record_specialist_result_writes_findings_and_lineage():
    if not await _db():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행")
    from app.services.ledger.ledger_adapters import record_specialist_result
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger import lineage

    tid, pnu = f"t-p3-{uuid.uuid4().hex[:8]}", f"P{uuid.uuid4().hex[:10]}"
    try:
        p1 = {"kind": "domain_agent", "schema_version": "domain_agent/v2", "domain": "permit",
              "task_type": "feasibility", "summary": {"far": 200.0},
              "findings_brief": [{"check_id": "PERMIT", "status": "pass", "current": 200.0, "limit": 250.0}],
              "claims": []}
        r1 = await record_specialist_result(analysis_type="domain_agent_permit", payload=p1,
                                            tenant_id=tid, pnu=pnu, source="specialist_permit")
        assert r1["contradictions"]["has_contradiction"] is False
        p2 = {**p1, "summary": {"far": 260.0},
              "findings_brief": [{"check_id": "PERMIT", "status": "fail", "current": 260.0, "limit": 250.0}]}
        r2 = await record_specialist_result(analysis_type="domain_agent_permit", payload=p2,
                                            tenant_id=tid, pnu=pnu, source="specialist_permit")
        assert r2["contradictions"]["has_contradiction"] is True          # status flip + far 30%
        latest = await ledger.get_latest(analysis_type="domain_agent_permit", tenant_id=tid, pnu=pnu)
        parents = await lineage.get_parents(child_hash=latest["content_hash"], tenant_id=tid)
        assert parents and parents[0]["max_severity"] == "high"
    finally:
        await _cleanup(tid)


async def test_w4_closed_specialist_dispatch_cites_ledger_with_lineage():
    # T5: coordinator.dispatch → SpecialistAgent → 계층1 도구 → 원장 cite(+lineage+contradiction). W4 닫힘.
    if not await _db():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행")
    from apps.api.core.coordinator import AgentCoordinator
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger import lineage

    tid, pnu = f"t-p3e2e-{uuid.uuid4().hex[:8]}", f"P{uuid.uuid4().hex[:10]}"
    coord = AgentCoordinator()
    try:
        # 1회차: M06(일반분양) 허용 → pass, prior 없음
        r1 = await coord.dispatch("permit", {"dev_type": "M06", "zone_type": "제2종일반주거지역"},
                                  tenant_id=tid, pnu=pnu)
        assert r1["ok"] and r1["ledger"]["ok"] and r1["findings"][0]["status"] == "pass"
        # 2회차: M09(지식산업센터) 불허 → fail (status flip 모순 + lineage)
        r2 = await coord.dispatch("permit", {"dev_type": "M09", "zone_type": "제2종일반주거지역"},
                                  tenant_id=tid, pnu=pnu)
        assert r2["findings"][0]["status"] == "fail"
        assert r2["contradictions"]["has_contradiction"] is True
        latest = await ledger.get_latest(analysis_type="domain_agent_permit", tenant_id=tid, pnu=pnu)
        parents = await lineage.get_parents(child_hash=latest["content_hash"], tenant_id=tid)
        assert parents                       # W4: 계층3가 원장에 cite + 파생 엣지
        vr = await ledger.verify_chain(analysis_type="domain_agent_permit", tenant_id=tid, pnu=pnu)
        assert vr["verified"] is True        # 무결성 불변
    finally:
        await _cleanup(tid)
