"""comprehensive 부지분석의 SpecialistAgent 배선(귀속 게이트·zoning 주입) 단위테스트.

broad 경로(comprehensive.analyze)는 귀속 컨텍스트(project_id/tenant_id)가 있을 때만 zoning을
디스패치해 NULL-tenant 원장 오염을 막는다. include_specialists=False·zone_type 부재 시 미디스패치.
analyze의 무거운 I/O는 monkeypatch로 스텁하고, run_specialist_domains는 스파이로 대체한다.
"""

from __future__ import annotations

import pytest

import app.services.agents.specialist_dispatch as sd_mod
from app.services.land_intelligence.comprehensive_analysis_service import (
    ComprehensiveAnalysisService,
)

_BASE = {
    "zone_type": "일반상업지역",
    "pnu": "1168010100101230000",
    "effective_far": {"effective_far_pct": 700, "effective_bcr_pct": 60},
}


def _stub_io(monkeypatch, svc, *, spy):
    """analyze의 I/O 의존(데이터수집·섹션계산·원장)을 경량 스텁으로 대체."""
    async def _collect(_addr):
        return dict(_BASE)

    async def _aempty(*_a, **_k):
        return {}

    async def _no_prior(**_k):
        return None

    async def _append(**_k):
        return {"ok": False}

    monkeypatch.setattr(svc.land_info, "collect_comprehensive", _collect)
    monkeypatch.setattr(svc, "_calc_supply_areas", lambda *a, **k: [])
    monkeypatch.setattr(svc, "_calc_land_prices", lambda *a, **k: {})
    monkeypatch.setattr(svc, "_calc_sale_prices", lambda *a, **k: [])
    monkeypatch.setattr(svc, "_research_transactions", _aempty)
    monkeypatch.setattr(svc, "_analyze_location", _aempty)
    monkeypatch.setattr(svc, "_research_dev_plans", lambda *a, **k: {})
    monkeypatch.setattr(svc, "_calc_upzoning", lambda *a, **k: {})
    monkeypatch.setattr("app.services.ledger.prior_context.load_prior", _no_prior)
    monkeypatch.setattr("app.services.ledger.analysis_ledger_service.append_analysis", _append)
    monkeypatch.setattr(
        "app.services.ledger.contradiction.detect_contradictions",
        lambda *a, **k: {"contradictions": [], "max_severity": "none"},
    )
    monkeypatch.setattr(sd_mod, "run_specialist_domains", spy)


@pytest.mark.asyncio
async def test_dispatch_only_with_attribution_context(monkeypatch):
    svc = ComprehensiveAnalysisService()
    calls: list = []

    async def _spy(domains, **ctx):
        calls.append((domains, ctx))
        return [{"domain": "zoning", "status": "ok", "findings": [{"claim": "z"}]}]

    _stub_io(monkeypatch, svc, spy=_spy)

    # (1) 귀속 컨텍스트 O → zoning+far 결정론 디스패치 + result.specialists 주입(permit 없음=Top3 부재).
    r1 = await svc.analyze("서울특별시 강남구 역삼동 123", project_id="p1", tenant_id="t1")
    assert len(calls) == 1
    assert set(calls[0][0].keys()) == {"zoning", "far"}  # comprehensive=결정론 zoning+far(무과금)
    assert calls[0][0]["far"]["zone_type"] == "일반상업지역"  # far에 zone·base·area 전달
    assert calls[0][1]["pnu"] == _BASE["pnu"]  # pnu 전파(원장 체인 일관)
    assert r1.get("specialists") and r1["specialists"][0]["domain"] == "zoning"

    # (2) include_specialists=False → 미디스패치·specialists 키 미생성.
    calls.clear()
    r2 = await svc.analyze("서울특별시 강남구 역삼동 123", project_id="p1", include_specialists=False)
    assert calls == []
    assert "specialists" not in r2

    # (3) 귀속 컨텍스트 X(익명) → 미디스패치(NULL-tenant 원장 오염 방지).
    calls.clear()
    r3 = await svc.analyze("서울특별시 강남구 역삼동 123")
    assert calls == []
    assert "specialists" not in r3


@pytest.mark.asyncio
async def test_no_dispatch_when_zone_missing(monkeypatch):
    svc = ComprehensiveAnalysisService()
    calls: list = []

    async def _spy(domains, **ctx):
        calls.append(domains)
        return []

    async def _collect_no_zone(_addr):
        return {"pnu": "123", "effective_far": {"effective_far_pct": 0, "effective_bcr_pct": 0}}

    _stub_io(monkeypatch, svc, spy=_spy)
    monkeypatch.setattr(svc.land_info, "collect_comprehensive", _collect_no_zone)

    r = await svc.analyze("어딘가 미상 주소", project_id="p1", tenant_id="t1")
    assert calls == []  # zone_type 없으면 미디스패치(가짜 입력 금지)
    assert "specialists" not in r
