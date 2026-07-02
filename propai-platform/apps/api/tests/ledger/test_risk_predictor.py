"""Phase 4.2 #3 — 위험예측층(risk_predictor). 결정론 feature/휴리스틱 + pluggable 모델."""
import uuid

import pytest

from app.services.ledger import risk_predictor

pytestmark = pytest.mark.asyncio


def test_extract_features_pure():
    feats = risk_predictor.extract_features(
        history=[{"version": 3}, {"version": 2}, {"version": 1}],
        latest_risk={"risk_level": "high", "risks": [{"type": "status_fail"}, {"type": "stale"}]})
    assert feats["version_count"] == 3.0
    assert feats["current_risk_level"] == 3.0   # high=3
    assert feats["risk_signal_count"] == 2.0
    assert feats["has_recent"] == 1.0


def test_predict_heuristic_when_no_model():
    hi = risk_predictor.predict_risk_score({"version_count": 5.0, "current_risk_level": 3.0, "risk_signal_count": 3.0})
    lo = risk_predictor.predict_risk_score({"version_count": 1.0, "current_risk_level": 0.0, "risk_signal_count": 0.0})
    assert hi["model"] == "heuristic" and hi["score"] > lo["score"]
    assert hi["level"] == "high" and lo["level"] == "low"
    # 빈 feature도 결정론·예외 없음
    empty = risk_predictor.predict_risk_score(risk_predictor.extract_features(history=[], latest_risk=None))
    assert empty["model"] == "heuristic" and 0.0 <= empty["score"] <= 1.0


def test_load_model_graceful_none():
    assert risk_predictor._load_model() is None   # xgboost/모델 부재 → None(휴리스틱 폴백)


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


async def test_predict_chain_risk_integration():
    if not await _db():
        pytest.skip("DB 미가용")
    from app.services.ledger.ledger_adapters import record_specialist_result
    at, tid, pnu = "domain_agent_pred", f"t-rp-{uuid.uuid4().hex[:8]}", f"P{uuid.uuid4().hex[:10]}"
    try:
        await record_specialist_result(analysis_type=at, tenant_id=tid, pnu=pnu, source="t",
            payload={"kind": "domain_agent", "verdict": "부적합",
                     "findings_brief": [{"check_id": "X", "status": "fail", "current": 300.0, "limit": 250.0}]})
        pred = await risk_predictor.predict_chain_risk(analysis_type=at, tenant_id=tid, pnu=pnu)
        assert "score" in pred and pred["model"] in ("heuristic", "xgboost")
        assert pred["level"] in ("high", "medium", "low")
        assert pred["current_risk_level"] == "high"   # 부적합 → status_fail
    finally:
        await _cleanup(tid)
