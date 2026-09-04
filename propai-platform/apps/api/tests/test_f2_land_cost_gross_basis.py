"""F2(QA REQUEST CHANGES) 토지 취득원가는 gross 기준 복원 — 회귀 테스트.

도로 혼입 다필지(자연녹지 8066㎡ + 도로 1785㎡) 통합분석에서:
  - 토지가액(land_prices.total_official_value_won 등) = gross(9,851㎡) × 단가
    (도로 필지도 실제로는 매입 대상이므로 usable로 축소하면 취득원가 과소표시 — 무날조 위반 방향).
  - GFA(supply_areas 각 항목 total_gfa_sqm) = usable(8,066㎡) × 실효 far
    (건축 불가 지목은 개발규모 산정에서 계속 제외 — P0-2 무회귀).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def _db_available() -> bool:
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory, engine
        await engine.dispose()
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _fake_base() -> dict:
    return {
        "pnu": "4146025021100010000",
        "zone_type": "자연녹지지역",
        "land_register": {"area_sqm": 8066.0, "official_price_per_sqm": 1_000_000},
        "official_prices": [{"price_per_sqm": 1_000_000}],
        "nearby_transactions": {"note": "stub"},
        "infrastructure": {},
        "coordinates": {},
        "warnings": [],
    }


def _parcels_road_mixed() -> list[dict]:
    return [
        {
            "pnu": "A", "zone_type": "자연녹지지역", "area_sqm": 8066.0, "land_category": "대",
            "farPct": 100.0, "bcrPct": 20.0, "farLegalPct": 100.0, "bcrLegalPct": 20.0,
        },
        {
            "pnu": "B", "zone_type": "자연녹지지역", "area_sqm": 1785.0, "land_category": "도로",
            "farPct": 100.0, "bcrPct": 20.0, "farLegalPct": 100.0, "bcrLegalPct": 20.0,
        },
    ]


async def test_land_cost_uses_gross_gfa_uses_usable(monkeypatch):
    if not await _db_available():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행(skip≠검증)")
    from app.services.ai.market_interpreter import MarketInterpreter
    from app.services.ai.site_analysis_interpreter import SiteAnalysisInterpreter
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )

    svc = ComprehensiveAnalysisService()

    async def _fake_collect(self, address, pnu=None):
        return _fake_base()

    monkeypatch.setattr(type(svc.land_info), "collect_comprehensive", _fake_collect, raising=True)

    async def _no_interpretation(self, result, prior_context=None):
        return None

    monkeypatch.setattr(SiteAnalysisInterpreter, "generate_interpretation", _no_interpretation, raising=True)
    monkeypatch.setattr(MarketInterpreter, "generate_interpretation", _no_interpretation, raising=True)

    result = await svc.analyze(
        "도로혼입-QA재현-F2", tenant_id="t-f2-gross", project_id=None,
        parcels=_parcels_road_mixed(),
    )

    gross_sqm = result["land_area_basis"]["gross_sqm"]
    usable_sqm = result["land_area_basis"]["usable_sqm"]
    assert gross_sqm == 9851.0, gross_sqm
    assert usable_sqm == 8066.0, usable_sqm
    # 개발규모(land_area_sqm)는 usable 유지(P0-2 무회귀).
    assert result["land_area_sqm"] == 8066.0

    # 토지가액 = gross(9,851) × 단가(1,000,000) — usable(8,066) 아님.
    land_prices = result["land_prices"]
    assert land_prices["total_official_value_won"] == 1_000_000 * 9851.0, land_prices
    assert land_prices["total_official_value_won"] != 1_000_000 * 8066.0

    # GFA = usable(8,066) × 실효far(100%) 기준 — 개발규모 산정은 계속 usable.
    supply = result["supply_areas"]
    assert isinstance(supply, list) and supply
    gfa_candidates = [s.get("total_gfa_sqm") for s in supply if s.get("total_gfa_sqm")]
    assert gfa_candidates, supply
    # 실효far=100%가 dev_type별 typical_far(대개 더 높음)보다 낮으므로 applied_far=100 채택.
    assert any(abs(g - 8066.0) < 1.0 for g in gfa_candidates), gfa_candidates
