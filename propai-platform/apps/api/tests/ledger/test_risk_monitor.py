"""Phase 4 — 능동 위험감지(risk_monitor). 순수 분류 + 실DB 체인평가/프로젝트 스캔."""
import uuid

import pytest

from app.services.ledger import risk_monitor as R

pytestmark = pytest.mark.asyncio


def test_classify_risks_pure_detects_all():
    risks = R.classify_risks(
        latest={"verdict": "부적합", "findings_brief": [{"check_id": "X", "status": "fail"}]},
        contradictions={"max_severity": "high", "counts": {"high": 2}},
        age_days=200, max_age_days=90)
    types = {r["type"] for r in risks}
    assert {"contradiction_high", "status_fail", "stale"} <= types
    assert all(r["severity"] in ("high", "medium", "low") for r in risks)


def test_classify_risks_clean_is_empty():
    risks = R.classify_risks(
        latest={"verdict": "적합", "findings_brief": [{"check_id": "X", "status": "pass"}]},
        contradictions={"max_severity": None, "counts": {}}, age_days=1, max_age_days=90)
    assert risks == []


async def _db() -> bool:
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory, engine
        await engine.dispose()
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


async def _cleanup(tid: str) -> None:
    from sqlalchemy import text
    from app.core.database import async_session_factory
    async with async_session_factory() as db:
        await db.execute(text("DELETE FROM analysis_lineage WHERE tenant_id=:t"), {"t": tid})
        await db.execute(text("DELETE FROM analysis_ledger WHERE tenant_id=:t"), {"t": tid})
        await db.commit()


async def test_evaluate_chain_risk_detects_contradiction_and_status():
    if not await _db():
        pytest.skip("DB 미가용")
    from app.services.ledger.ledger_adapters import record_specialist_result
    at = "domain_agent_risktest"
    tid, pnu = f"t-rm-{uuid.uuid4().hex[:8]}", f"P{uuid.uuid4().hex[:10]}"
    try:
        await record_specialist_result(analysis_type=at, tenant_id=tid, pnu=pnu, source="t",
            payload={"kind": "domain_agent", "verdict": "적합", "summary": {"far": 200.0},
                     "findings_brief": [{"check_id": "X", "status": "pass", "current": 200.0, "limit": 250.0}]})
        await record_specialist_result(analysis_type=at, tenant_id=tid, pnu=pnu, source="t",
            payload={"kind": "domain_agent", "verdict": "부적합", "summary": {"far": 260.0},
                     "findings_brief": [{"check_id": "X", "status": "fail", "current": 260.0, "limit": 250.0}]})
        ev = await R.evaluate_chain_risk(analysis_type=at, tenant_id=tid, pnu=pnu)
        types = {r["type"] for r in ev["risks"]}
        assert "contradiction_high" in types and "status_fail" in types
        assert ev["risk_level"] == "high"
    finally:
        await _cleanup(tid)


async def test_scan_project_risks_aggregates():
    if not await _db():
        pytest.skip("DB 미가용")
    from app.services.ledger.ledger_adapters import record_specialist_result
    tid, pid = f"t-rm-{uuid.uuid4().hex[:8]}", f"PRJ-{uuid.uuid4().hex[:8]}"
    try:
        for at in ("domain_agent_a", "domain_agent_b"):
            await record_specialist_result(analysis_type=at, tenant_id=tid, project_id=pid, source="t",
                payload={"kind": "domain_agent", "verdict": "적합",
                         "findings_brief": [{"check_id": "X", "status": "pass", "current": 100.0, "limit": 250.0}]})
            await record_specialist_result(analysis_type=at, tenant_id=tid, project_id=pid, source="t",
                payload={"kind": "domain_agent", "verdict": "부적합",
                         "findings_brief": [{"check_id": "X", "status": "fail", "current": 300.0, "limit": 250.0}]})
        scan = await R.scan_project_risks(tenant_id=tid, project_id=pid)
        assert scan["chains_at_risk"] == 2 and scan["risk_level"] == "high"
    finally:
        await _cleanup(tid)
