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


# ── Phase 4.2 #1·#2: append 훅(이벤트 구동) + 알림 채널 ──

async def test_dispatch_risk_alert_notifies_high_only():
    R.clear_notifiers()
    captured: list = []
    R.register_notifier(lambda alert: captured.append(alert))
    try:
        hi = await R.dispatch_risk_alert(project_id="P", analysis_type="x",
            risk={"risk_level": "high", "risks": [{"type": "status_fail"}]})
        assert hi["dispatched"] == 1 and len(captured) == 1
        lo = await R.dispatch_risk_alert(project_id="P", analysis_type="x",
            risk={"risk_level": "none", "risks": []})
        assert lo.get("skipped") is True and len(captured) == 1   # low/none은 미발송(정직)
    finally:
        R.clear_notifiers()


async def test_on_analysis_appended_evaluates_and_notifies():
    if not await _db():
        pytest.skip("DB 미가용")
    from app.services.ledger.ledger_adapters import record_specialist_result
    R.clear_notifiers()
    captured: list = []
    R.register_notifier(lambda a: captured.append(a))
    at, tid, pnu = "domain_agent_hook", f"t-rm-{uuid.uuid4().hex[:8]}", f"P{uuid.uuid4().hex[:10]}"
    try:
        await record_specialist_result(analysis_type=at, tenant_id=tid, pnu=pnu, source="t",
            payload={"kind": "domain_agent", "verdict": "부적합",
                     "findings_brief": [{"check_id": "X", "status": "fail", "current": 300.0, "limit": 250.0}]})
        ev = await R.on_analysis_appended(analysis_type=at, tenant_id=tid, pnu=pnu)
        assert ev["risk_level"] == "high" and ev["notify"]["dispatched"] >= 1
        assert captured  # 고위험 → 알림 발송
    finally:
        R.clear_notifiers()
        await _cleanup(tid)


async def test_append_with_lineage_attaches_risk_automatically():
    # #1 배선: record_specialist_result(=_append_with_lineage) 결과에 risk 자동 부착(이벤트 구동)
    if not await _db():
        pytest.skip("DB 미가용")
    from app.services.ledger.ledger_adapters import record_specialist_result
    at, tid, pnu = "domain_agent_wire", f"t-rm-{uuid.uuid4().hex[:8]}", f"P{uuid.uuid4().hex[:10]}"
    try:
        wb = await record_specialist_result(analysis_type=at, tenant_id=tid, pnu=pnu, source="t",
            payload={"kind": "domain_agent", "verdict": "부적합",
                     "findings_brief": [{"check_id": "X", "status": "fail", "current": 300.0, "limit": 250.0}]})
        assert "risk" in wb and wb["risk"]["risk_level"] == "high"
    finally:
        await _cleanup(tid)


# ── #2 알림 임계값 env 튜닝(RISK_ALERT_MIN_LEVEL) — 순수 로직(무DB) ──

async def test_dispatch_default_medium_sends_high_and_medium(monkeypatch):
    from app.services.ledger import risk_monitor as R
    monkeypatch.delenv("RISK_ALERT_MIN_LEVEL", raising=False)
    R.clear_notifiers()
    got: list = []
    R.register_notifier(lambda a: got.append(a["risk_level"]))
    try:
        for lvl in ("high", "medium", "low", "none"):
            await R.dispatch_risk_alert(project_id="p", analysis_type="t",
                                        risk={"risk_level": lvl, "risks": []})
        assert got == ["high", "medium"]  # 기본 medium 이상만 발송
    finally:
        R.clear_notifiers()


async def test_dispatch_high_only_when_min_level_high(monkeypatch):
    # config.settings 는 lru_cache 라 monkeypatch 로 속성 직접 주입(런타임 게이트 검증)
    from app.core.config import settings
    from app.services.ledger import risk_monitor as R
    monkeypatch.setattr(settings, "RISK_ALERT_MIN_LEVEL", "high", raising=False)
    R.clear_notifiers()
    got: list = []
    R.register_notifier(lambda a: got.append(a["risk_level"]))
    try:
        for lvl in ("high", "medium", "low"):
            res = await R.dispatch_risk_alert(project_id="p", analysis_type="t",
                                              risk={"risk_level": lvl, "risks": []})
            if lvl != "high":
                assert res.get("skipped") and res.get("min_level") == "high"
        assert got == ["high"]  # high 만 발송(medium 소음 차단)
    finally:
        R.clear_notifiers()


def test_min_alert_level_unknown_falls_back_medium(monkeypatch):
    from app.core.config import settings
    from app.services.ledger import risk_monitor as R
    monkeypatch.setattr(settings, "RISK_ALERT_MIN_LEVEL", "garbage", raising=False)
    assert R._min_alert_level() == "medium"  # 알 수 없는 값 안전측 폴백


# ── 알림 본문 한국어 포맷(_format_alert_text) — 순수 결정론(무네트워크) ──

def test_format_alert_text_korean_high():
    txt = R._format_alert_text({
        "risk_level": "high", "analysis_type": "legal_review", "project_id": "PRJ-1",
        "risks": [{"type": "contradiction_high", "severity": "high",
                   "detail": "직전 대비 고심각 모순 2건", "recommend": "재검토/재분석"}]})
    assert txt.startswith("🚨 사통팔땅 위험알림 [심각]")
    assert "분석: legal_review" in txt and "프로젝트: PRJ-1" in txt
    assert "위험신호 1건" in txt
    assert "· 직전 대비 고심각 모순 2건 → 재검토/재분석" in txt


def test_format_alert_text_medium_caps_details():
    risks = [{"type": "stale", "detail": f"신호{i}"} for i in range(7)]
    txt = R._format_alert_text({"risk_level": "medium", "analysis_type": "t",
                                "project_id": None, "risks": risks})
    assert txt.startswith("⚠️ 사통팔땅 위험알림 [주의]")
    assert "위험신호 7건" in txt and "· 신호4" in txt
    assert "· 신호5" not in txt and "· 외 2건" in txt  # 상세 5건 캡 + 잔여 정직 표기


def test_format_alert_text_unknown_level_and_empty():
    txt = R._format_alert_text({"risk_level": "custom", "analysis_type": "t",
                                "project_id": "p", "risks": []})
    assert "[custom]" in txt and "위험신호 0건" in txt  # 미상 레벨은 원문 유지(무날조)
