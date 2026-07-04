"""Phase 1 수용기준: (1)성장루프(2회차가 1회차 prior 사용) (2)결정론 무결성 불변 (3)멱등."""
import pytest

pytestmark = pytest.mark.asyncio


async def _db() -> bool:
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory, engine
        await engine.dispose()  # 교차-이벤트루프 풀 바인딩 초기화(테스트 격리 — 현재 루프에 재바인딩)
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def test_growth_loop_and_determinism():
    if not await _db():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행")
    from app.services.ledger import analysis_ledger_service as ledger
    tid, addr, pnu = "t-e2e-p1", "의정부동 224-e2e", "1115010300102240000"

    pl = {"kind": "design_audit", "schema_version": "design_audit/v1", "verdict": "conditional",
          "findings_brief": [{"check_id": "FAR-01", "status": "fail", "current": 250.0, "limit": 200.0}]}
    r1 = await ledger.append_analysis(
        analysis_type="design_audit", tenant_id=tid, pnu=pnu, address=addr, payload=pl)
    assert r1["ok"] is True
    # 멱등: 동일 payload 재append → unchanged
    r1b = await ledger.append_analysis(
        analysis_type="design_audit", tenant_id=tid, pnu=pnu, address=addr, payload=pl)
    assert r1b.get("unchanged") is True

    # 2회차 prior로 읽힘
    prior = await ledger.get_latest(analysis_type="design_audit", tenant_id=tid, pnu=pnu, address=addr)
    assert prior is not None and prior["payload"]["findings_brief"][0]["current"] == 250.0

    # 내용 변경 → 새 버전(체인 누적)
    pl2 = {**pl, "verdict": "부적합"}
    r2 = await ledger.append_analysis(
        analysis_type="design_audit", tenant_id=tid, pnu=pnu, address=addr, payload=pl2)
    assert r2["ok"] is True and r2["version"] == prior["version"] + 1

    # 결정론 무결성 — prior가 read·누적돼도 해시체인 불변(변조 없음)
    v = await ledger.verify_chain(analysis_type="design_audit", tenant_id=tid, pnu=pnu, address=addr)
    assert v.get("ok") is not False
    assert v.get("verified") is True
