"""Phase 1: feasibility 'feasibility' write+read 쌍이 'feasibility_vcs'와 분리된 체인인지(실DB)."""
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


async def test_feasibility_chain_separate_from_vcs():
    if not await _db_available():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행")
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger.ledger_adapters import record_feasibility_commit, record_feasibility_result

    tid, pid = "t-feas-p1", "proj-feas-p1"
    await record_feasibility_result(
        result={"development_type": "다세대", "total_revenue_won": 5_000_000_000,
                "net_profit_won": 800_000_000, "profit_rate_pct": 16.0, "npv_won": 600_000_000, "grade": "B"},
        tenant_id=tid, project_id=pid)
    await record_feasibility_commit(
        commit={"sha": "abc", "parent_sha": None, "message": "m", "author": "u", "timestamp": "t"},
        tenant_id=tid, project_id=pid)

    # read 'feasibility' → 수지결과(성장루프 재무 체인)
    fin = await ledger.get_latest(analysis_type="feasibility", tenant_id=tid, project_id=pid)
    assert fin is not None and fin["payload"]["kind"] == "feasibility"
    assert fin["payload"]["grade"] == "B"

    # 'feasibility_vcs'는 분리된 체인(VCS 메타) — 서로 오염 안 함
    vcs = await ledger.get_latest(analysis_type="feasibility_vcs", tenant_id=tid, project_id=pid)
    assert vcs is not None and vcs["payload"]["kind"] == "feasibility_commit"
