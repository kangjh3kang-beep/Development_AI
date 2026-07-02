"""P5 T1 — 원장 staleness/재분석 제안(staleness.py). 순수 임계 로직 + 실DB read."""
import uuid

import pytest

from app.services.ledger import staleness

pytestmark = pytest.mark.asyncio


def test_recommend_pure_logic():
    # 순수 임계 로직(무 DB): stale 또는 changed면 재분석 권장
    assert staleness._recommend(age_days=120, max_age_days=90, changed=False)["recommend_reanalysis"] is True
    assert staleness._recommend(age_days=10, max_age_days=90, changed=False)["recommend_reanalysis"] is False
    assert staleness._recommend(age_days=10, max_age_days=90, changed=True)["recommend_reanalysis"] is True
    r = staleness._recommend(age_days=200, max_age_days=90, changed=True)
    assert r["stale"] is True and r["changed"] is True
    assert "stale" in r["reasons"] and "changed" in r["reasons"]


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
        await db.execute(text("DELETE FROM analysis_ledger WHERE tenant_id=:t"), {"t": tid})
        await db.commit()


async def test_no_prior_returns_no_reanalysis():
    if not await _db():
        pytest.skip("DB 미가용")
    tid, pnu = f"t-{uuid.uuid4().hex[:8]}", f"P{uuid.uuid4().hex[:10]}"
    r = await staleness.check_staleness(analysis_type="site_analysis", tenant_id=tid, pnu=pnu)
    assert r["recommend_reanalysis"] is False and r["reason"] == "no_prior"


async def test_fresh_prior_with_change_recommends_reanalysis():
    if not await _db():
        pytest.skip("DB 미가용")
    from app.services.ledger import analysis_ledger_service as ledger
    tid, pnu = f"t-{uuid.uuid4().hex[:8]}", f"P{uuid.uuid4().hex[:10]}"
    try:
        await ledger.append_analysis(analysis_type="site_analysis", tenant_id=tid, pnu=pnu,
                                     payload={"effective_far": 200.0, "verdict": "적합"})
        r = await staleness.check_staleness(analysis_type="site_analysis", tenant_id=tid, pnu=pnu,
                                    current={"effective_far": 260.0, "verdict": "부적합"}, max_age_days=90)
        assert r["stale"] is False                  # 방금 적재(age≈0)
        assert r["changed"] is True                 # far 30%↑ + verdict flip
        assert r["recommend_reanalysis"] is True
        assert r["prior_version"] == 1 and r["age_days"] is not None
    finally:
        await _cleanup(tid)


async def test_history_trend_counts_versions():
    if not await _db():
        pytest.skip("DB 미가용")
    from app.services.ledger import analysis_ledger_service as ledger
    tid, pnu = f"t-{uuid.uuid4().hex[:8]}", f"P{uuid.uuid4().hex[:10]}"
    try:
        for far in (100.0, 150.0, 220.0):
            await ledger.append_analysis(analysis_type="site_analysis", tenant_id=tid, pnu=pnu,
                                         payload={"effective_far": far})
        rep = await staleness.staleness_report(analysis_type="site_analysis", tenant_id=tid, pnu=pnu)
        assert rep["versions"] == 3 and rep["latest_version"] == 3
    finally:
        await _cleanup(tid)
