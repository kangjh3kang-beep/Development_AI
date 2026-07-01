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
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger import lineage
    from app.services.ledger.ledger_adapters import record_specialist_result

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
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger import lineage
    from apps.api.core.coordinator import AgentCoordinator

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


async def test_multi_domain_dispatch_all_cite_ledger():
    # Phase 3.2: permit·zoning·far 3도메인 모두 coordinator 디스패치로 원장 cite + far 2회차 모순/lineage.
    if not await _db():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행")
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger import lineage
    from apps.api.core.coordinator import AgentCoordinator

    tid, pnu = f"t-p32-{uuid.uuid4().hex[:8]}", f"P{uuid.uuid4().hex[:10]}"
    coord = AgentCoordinator()
    try:
        for domain, data in [
            ("permit", {"dev_type": "M06", "zone_type": "제2종일반주거지역"}),
            ("zoning", {"zone_type": "제2종일반주거지역"}),
            ("far", {"zone_type": "제2종일반주거지역"}),     # far=250
        ]:
            r = await coord.dispatch(domain, data, tenant_id=tid, pnu=pnu)
            assert r["ok"] and r["ledger"]["ok"]
            latest = await ledger.get_latest(analysis_type=f"domain_agent_{domain}", tenant_id=tid, pnu=pnu)
            assert latest is not None and latest["payload"]["domain"] == domain

        # far 2회차: 다른 용도지역(제1종전용 far=100) → 수치 델타(250→100) 모순 + lineage
        r2 = await coord.dispatch("far", {"zone_type": "제1종전용주거지역"}, tenant_id=tid, pnu=pnu)
        assert r2["contradictions"]["has_contradiction"] is True
        latest_far = await ledger.get_latest(analysis_type="domain_agent_far", tenant_id=tid, pnu=pnu)
        parents = await lineage.get_parents(child_hash=latest_far["content_hash"], tenant_id=tid)
        assert parents and parents[0]["max_severity"] == "high"
    finally:
        await _cleanup(tid)


async def test_domain_agents_record_enriched_with_findings_and_lineage():
    # #1 합류: record_domain_agent_task(domain_agents_service가 호출)가 도메인별 체인 +
    # findings_brief + prior 모순/lineage로 보강됨(서비스 자동 수혜).
    if not await _db():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행")
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger import lineage
    from app.services.ledger.ledger_adapters import record_domain_agent_task

    tid, pid = f"t-da-{uuid.uuid4().hex[:8]}", f"PRJ-{uuid.uuid4().hex[:8]}"
    try:
        r1 = await record_domain_agent_task(
            task={"domain": "finance", "task_type": "analysis", "status": "completed",
                  "confidence_score": 0.82, "recommendation": "proceed",
                  "requires_approval": False, "id": "T1"},
            tenant_id=tid, project_id=pid)
        assert r1["ok"] is True and r1["contradictions"]["has_contradiction"] is False
        latest1 = await ledger.get_latest(analysis_type="domain_agent_finance", tenant_id=tid, project_id=pid)
        assert latest1["payload"]["findings_brief"][0]["check_id"] == "RECOMMENDATION"

        # 2회차: 권고 플립(proceed→escalate) + confidence 하락 → 모순 + lineage
        r2 = await record_domain_agent_task(
            task={"domain": "finance", "task_type": "analysis", "status": "completed",
                  "confidence_score": 0.40, "recommendation": "escalate",
                  "requires_approval": True, "id": "T2"},
            tenant_id=tid, project_id=pid)
        assert r2["contradictions"]["has_contradiction"] is True
        latest2 = await ledger.get_latest(analysis_type="domain_agent_finance", tenant_id=tid, project_id=pid)
        parents = await lineage.get_parents(child_hash=latest2["content_hash"], tenant_id=tid)
        assert parents
    finally:
        await _cleanup(tid)
