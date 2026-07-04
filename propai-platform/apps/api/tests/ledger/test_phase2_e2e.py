"""Phase 2 e2e — comprehensive 배선(모순 표면화 + lineage write-back)을 실DB로 검증.

Phase 1 패턴: engine.dispose() 루프격리 + collect_comprehensive monkeypatch(경량 호출).
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


async def test_comprehensive_surfaces_contradiction_and_records_lineage(monkeypatch):
    if not await _db():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행")
    from app.services.land_intelligence.comprehensive_analysis_service import ComprehensiveAnalysisService
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger import lineage

    pnu = f"111501030010{uuid.uuid4().hex[:7]}"
    addr = f"의정부동 224-{uuid.uuid4().hex[:6]}"
    tid = f"t-p2-comp-{uuid.uuid4().hex[:8]}"
    svc = ComprehensiveAnalysisService()
    far = {"v": 200.0}

    async def _fake_collect(self, address, pnu_arg=None):
        return {"pnu": pnu, "zone_type": "제2종일반주거지역",
                "land_register": {"area_sqm": 300.0},
                "effective_far": {"effective_far_pct": far["v"], "effective_bcr_pct": 60.0},
                "warnings": []}

    monkeypatch.setattr(type(svc.land_info), "collect_comprehensive", _fake_collect, raising=True)

    try:
        # 1회차 — prior 없음 → 모순 없음
        r1 = await svc.analyze(addr, tenant_id=tid, project_id=None)
        assert r1["contradictions"]["has_contradiction"] is False

        # 2회차 — FAR 200→260(30%↑) → 모순(high) + lineage 엣지
        far["v"] = 260.0
        r2 = await svc.analyze(addr, tenant_id=tid, project_id=None)
        assert r2["contradictions"]["has_contradiction"] is True
        assert r2["contradictions"]["max_severity"] == "high"

        latest = await ledger.get_latest(analysis_type="site_analysis", tenant_id=tid,
                                         pnu=pnu, address=addr, project_id=None)
        parents = await lineage.get_parents(child_hash=latest["content_hash"], tenant_id=tid)
        assert parents and parents[0]["max_severity"] == "high"
        assert parents[0]["contradiction_count"] >= 1
    finally:
        await _cleanup(tid)


async def test_feasibility_writeback_contradiction_and_lineage():
    if not await _db():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행")
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger import lineage
    from app.services.ledger.ledger_adapters import record_feasibility_result

    tid = f"t-p2-feas-{uuid.uuid4().hex[:8]}"
    pid = f"proj-{uuid.uuid4().hex[:8]}"
    try:
        # 1회차 — prior 없음 → 모순 없음
        r1 = await record_feasibility_result(
            result={"development_type": "다세대", "total_revenue_won": 5_000_000_000,
                    "net_profit_won": 800_000_000, "profit_rate_pct": 18.0,
                    "npv_won": 600_000_000, "grade": "B"},
            tenant_id=tid, project_id=pid)
        assert r1["contradictions"]["has_contradiction"] is False

        # 2회차 — profit_rate 18→11(7%p, 절대임계 5%p 초과) 등 → 모순 + lineage 엣지
        r2 = await record_feasibility_result(
            result={"development_type": "다세대", "total_revenue_won": 4_000_000_000,
                    "net_profit_won": 300_000_000, "profit_rate_pct": 11.0,
                    "npv_won": 200_000_000, "grade": "D"},
            tenant_id=tid, project_id=pid)
        assert r2["contradictions"]["has_contradiction"] is True

        latest = await ledger.get_latest(analysis_type="feasibility", tenant_id=tid, project_id=pid)
        parents = await lineage.get_parents(child_hash=latest["content_hash"], tenant_id=tid)
        assert parents and parents[0]["contradiction_count"] >= 1
    finally:
        await _cleanup(tid)


async def test_contradiction_detection_does_not_mutate_ledger_chain_or_verdict():
    # T6 불변: 모순탐지/lineage는 read·부가 기록 전용 — 원장 체인 무결성·결정론 판정 절대 불변.
    if not await _db():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행")
    from app.services.ledger import analysis_ledger_service as ledger
    tid = f"t-p2-inv-{uuid.uuid4().hex[:8]}"
    pnu = f"111501030010{uuid.uuid4().hex[:7]}"
    try:
        await ledger.append_analysis(analysis_type="site_analysis", tenant_id=tid, pnu=pnu,
                                     payload={"far": 100.0, "verdict": "적합"})
        await ledger.append_analysis(analysis_type="site_analysis", tenant_id=tid, pnu=pnu,
                                     payload={"far": 150.0, "verdict": "부적합"})
        vr = await ledger.verify_chain(analysis_type="site_analysis", tenant_id=tid, pnu=pnu)
        assert vr["verified"] is True and vr["length"] == 2
        latest = await ledger.get_latest(analysis_type="site_analysis", tenant_id=tid, pnu=pnu)
        assert latest["payload"]["verdict"] == "부적합"   # 결정론 판정 불변(탐지기 비개입)
    finally:
        await _cleanup(tid)
