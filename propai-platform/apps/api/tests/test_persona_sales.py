"""분양대행 페르소나 오케스트레이션 단위테스트(R9).

외부 서비스(suggest_base_price·expert_panel)는 monkeypatch로 대체해 DB·외부API 없이
체크리스트 판정·검증루프(trust 흡수·전문가패널 캐시)·핸드오프 스키마·무과금을 검증한다.
"""

from __future__ import annotations

import pytest

from app.services.persona import cache
from app.services.persona.registry import PERSONA_REGISTRY, get_persona, list_personas
from app.services.persona.runner import run_persona


class _FakeDB:
    """address 직접 전달 경로만 쓰므로 DB 미접촉(execute 호출되면 실패시킴)."""

    async def execute(self, *a, **k):  # pragma: no cover — 호출되면 안 됨
        raise AssertionError("DB 접근이 없어야 한다(address 직접 전달)")


_SUGGEST_LIVE = {
    "data_source": "live",
    "address": "서울특별시 강남구 역삼동 123",
    "lawd_cd": "1168010100",
    "trust": {"verdict": "pass", "confidence": 0.82, "used_sources": ["동_실거래"]},
    "tiers": [
        {"tier": "conservative", "per_pyeong_10k": 5000},
        {"tier": "base", "per_pyeong_10k": 5500},
        {"tier": "aggressive", "per_pyeong_10k": 6000},
    ],
    "cost_validation": {"conservative_viable": True,
                        "viable_price_floor_per_pyeong_10k": 4000, "cost_basis": "표준단가(SSOT)"},
    "market_reference": {"dong": {"n": 42}, "sigungu": {"n": 120}},
    "note": "적정분양가 산출 완료",
}


def test_registry_has_two_personas():
    assert set(PERSONA_REGISTRY) == {"sales_agent", "urban_planner"}
    assert get_persona("sales_agent").name_ko == "분양대행 전문가"
    meta = list_personas()
    assert len(meta) == 2
    sa = next(m for m in meta if m["key"] == "sales_agent")
    assert len(sa["checklist"]) == 4
    assert sa["billing_key"] == "persona_sales_agent"


async def test_sales_live_confirmed_no_llm(monkeypatch):
    async def fake_suggest(db, site_id, bcode=None, **k):
        return dict(_SUGGEST_LIVE)

    monkeypatch.setattr("app.services.sales.pricing.suggest.suggest_base_price", fake_suggest)

    out = await run_persona("sales_agent", _FakeDB(),
                            {"site_id": "11111111-1111-1111-1111-111111111111",
                             "address": "서울특별시 강남구 역삼동 123"},
                            use_llm=False)
    # 핸드오프 스키마
    assert out["persona_key"] == "sales_agent"
    assert out["status"] == "confirmed"          # 전부 pass
    assert len(out["checklist"]) == 4
    price = next(c for c in out["checklist"] if c["step"] == "price")
    assert price["status"] == "pass"
    # 무과금(use_llm=False)
    assert out["billing"]["use_llm"] is False
    assert out["billing"]["estimated_fee_krw"] == 0
    # 검증루프: trust 흡수, 전문가패널은 use_llm=False라 미호출
    assert out["verification"]["trust"]["verdict"] == "pass"
    assert "expert_panel" not in out["verification"]
    # 산출물 키
    assert out["artifacts"]["price_tiers"]


async def test_sales_missing_data_is_partial(monkeypatch):
    async def fake_suggest(db, site_id, bcode=None, **k):
        return {"data_source": "unavailable", "note": "주변 실거래 없음"}

    monkeypatch.setattr("app.services.sales.pricing.suggest.suggest_base_price", fake_suggest)

    out = await run_persona("sales_agent", _FakeDB(),
                            {"site_id": "11111111-1111-1111-1111-111111111111",
                             "address": "어딘가"}, use_llm=False)
    assert out["status"] == "partial"            # missing 존재
    price = next(c for c in out["checklist"] if c["step"] == "price")
    assert price["status"] == "missing"
    assert any("가짜값" in n or "신뢰도" in n for n in out["honesty_notes"])


async def test_sales_no_site_id_honesty(monkeypatch):
    out = await run_persona("sales_agent", _FakeDB(), {"address": "어딘가"}, use_llm=False)
    assert out["status"] == "partial"
    assert any("site_id" in n for n in out["honesty_notes"])


async def test_expert_panel_called_once_and_cached(monkeypatch):
    calls = {"n": 0}

    async def fake_suggest(db, site_id, bcode=None, **k):
        return dict(_SUGGEST_LIVE)

    class _FakePanel:
        async def analyze(self, atype, ctx, address="", mode="single"):
            calls["n"] += 1
            return {"consensus": "ok", "experts": [{"role": "분양"}], "roster": ["분양"], "mode": mode}

    class _FakeMarketReportService:
        """시장보고서를 격리(hermetic) — _SUGGEST_LIVE.lawd_cd 폴백으로 build_report 경로가
        실제 진입하므로 외부 의존(MOLIT·DB)을 끊고 고정 보고서를 반환한다."""

        async def build_report(self, address, lawd, pnu, use_llm=False, options=None):
            return {"narrative": "테스트 내러티브", "trade": {}, "zone_type": "제2종일반주거지역"}

    monkeypatch.setattr("app.services.sales.pricing.suggest.suggest_base_price", fake_suggest)
    monkeypatch.setattr(
        "app.services.expert_panel.expert_panel_service.ExpertPanelService", _FakePanel)
    monkeypatch.setattr(
        "app.services.market.market_report_service.MarketReportService",
        _FakeMarketReportService)
    # cache 초기화(페르소나당 1회·재사용 검증).
    cache._STORE.clear()

    ctx = {"site_id": "11111111-1111-1111-1111-111111111111",
           "project_id": "p-1", "address": "서울특별시 강남구 역삼동 123"}
    out1 = await run_persona("sales_agent", _FakeDB(), ctx, use_llm=True)
    assert out1["verification"]["expert_panel"]["consensus"] == "ok"
    assert calls["n"] == 1                        # 페르소나당 1회
    # 동일 (key,project,addr) → 캐시 재사용(추가 호출 0)
    out2 = await run_persona("sales_agent", _FakeDB(), ctx, use_llm=True)
    assert calls["n"] == 1
    assert out2["verification"]["expert_panel"].get("cached") is True


async def test_unknown_persona_raises():
    with pytest.raises(ValueError):
        await run_persona("nope", _FakeDB(), {}, use_llm=False)
