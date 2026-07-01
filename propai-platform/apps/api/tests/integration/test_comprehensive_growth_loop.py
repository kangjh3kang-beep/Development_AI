"""Phase 1: 종합분석 성장루프 — 2회차가 1회차 원장 prior를 읽어 첨부하고, 새 버전을 write한다."""
import pytest

pytestmark = pytest.mark.asyncio


async def _db_available() -> bool:
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory, engine
        await engine.dispose()  # 교차-이벤트루프 풀 바인딩 초기화(테스트 격리 — 현재 루프에 재바인딩)
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _fake_base():
    return {
        "pnu": "1115010300102240000",
        "zone_type": "제2종일반주거지역",
        "land_register": {"area_sqm": 300.0},
        "effective_far": {"effective_far_pct": 200.0, "effective_bcr_pct": 60.0},
        "warnings": [],
    }


async def test_second_analysis_reads_prior_and_writes_new_version(monkeypatch):
    if not await _db_available():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행(skip≠검증, Task8 게이트)")
    from app.services.land_intelligence.comprehensive_analysis_service import ComprehensiveAnalysisService
    from app.services.ledger import analysis_ledger_service as ledger

    addr = "의정부동 224-phase1"
    tid = "t-phase1-comp"
    pnu = "1115010300102240000"
    svc = ComprehensiveAnalysisService()

    async def _fake_collect(self, address, pnu=None):
        return _fake_base()

    monkeypatch.setattr(type(svc.land_info), "collect_comprehensive", _fake_collect, raising=True)

    # 1회차 — 원장에 site_analysis write-back
    r1 = await svc.analyze(addr, tenant_id=tid, project_id=None)
    assert "prior_analysis" in r1
    prior = await ledger.get_latest(analysis_type="site_analysis", tenant_id=tid,
                                    pnu=pnu, address=addr, project_id=None)
    assert prior is not None and prior["version"] >= 1

    # 2회차 — prior가 read되어 result에 첨부, 새 버전(멱등이면 동일) write
    r2 = await svc.analyze(addr, tenant_id=tid, project_id=None)
    assert r2.get("prior_analysis") is not None  # 1회차가 prior로 읽힘
    assert r2["prior_analysis"]["analysis_type"] == "site_analysis"
    after = await ledger.get_latest(analysis_type="site_analysis", tenant_id=tid,
                                    pnu=pnu, address=addr, project_id=None)
    assert after["version"] >= prior["version"]
