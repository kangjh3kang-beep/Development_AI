"""과제 D — 하위 패널 정직화 회귀 테스트.

1) development_plans.land_use_regulations 중복 제거(순서 보존) + land_use_regulations_detail
   (verified 법령링크만 채택, 매핑 없으면 link=None — 임의 URL 조립 금지).
2) market_interpretation_status — 실패 시 사유를 정직 병기(기존 market_interpretation=None은 불변).
"""
from __future__ import annotations

import pytest


# ────────────────────────────────────────────
# _research_dev_plans — 순수 동기 함수(DB·네트워크 불필요)
# ────────────────────────────────────────────
def _svc():
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )
    return ComprehensiveAnalysisService()


def test_land_use_regulations_deduped_preserving_order():
    """VWorld가 동일 designation을 중복 반환해도 land_use_regulations는 첫 등장 순서로 1건만."""
    base = {
        "special_districts": [],
        "land_use_plan": {
            "districts": [
                {"district_name": "개발제한구역"},
                {"district_name": "고도지구"},
                {"district_name": "개발제한구역"},  # 중복
            ]
        },
    }
    out = _svc()._research_dev_plans(base)
    assert out["land_use_regulations"] == ["개발제한구역", "고도지구"]  # 순서 보존 + 중복 제거
    # regulation_notes·risk_factors도 중복 제거된 목록 기준으로 파생(기존 로직 그대로 재사용).
    assert len(out["regulation_notes"]) == 2
    assert sum(1 for f in out["risk_factors"] if "개발제한구역" in f) == 1


def test_land_use_regulations_detail_verified_link_for_greenbelt():
    """개발제한구역 → 기존 legal_reference_registry(greenbelt 키)의 verified 링크가 채택된다."""
    base = {
        "special_districts": [],
        "land_use_plan": {"districts": [{"district_name": "개발제한구역"}]},
    }
    out = _svc()._research_dev_plans(base)
    detail = out["land_use_regulations_detail"]
    assert detail == [{"name": "개발제한구역", "link": detail[0]["link"]}]
    assert detail[0]["link"], "개발제한구역은 greenbelt 키로 매핑되어 링크가 있어야 함"
    assert detail[0]["link"].startswith("https://www.law.go.kr/")


def test_land_use_regulations_detail_unmapped_zone_link_is_null():
    """법령 레지스트리에 매핑 키가 없는 규제명은 link=None(임의 URL 조립 금지)."""
    base = {
        "special_districts": [],
        "land_use_plan": {"districts": [{"district_name": "존재하지않는가상구역명"}]},
    }
    out = _svc()._research_dev_plans(base)
    detail = out["land_use_regulations_detail"]
    assert detail == [{"name": "존재하지않는가상구역명", "link": None}]


def test_land_use_regulations_detail_empty_when_no_regulations():
    out = _svc()._research_dev_plans({"special_districts": []})
    assert out["land_use_regulations"] == []
    assert out["land_use_regulations_detail"] == []


# ────────────────────────────────────────────
# market_interpretation_status — analyze() 전체 경로(DB 필요·단일필지)
# ────────────────────────────────────────────
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
        "address": "market-status-qa",
        "zone_type": "제2종일반주거지역",
        "land_register": {"area_sqm": 500.0, "official_price_per_sqm": 1_000_000},
        "official_prices": [{"price_per_sqm": 1_000_000}],
        "nearby_transactions": {"note": "stub"},
        "infrastructure": {},
        "coordinates": {},
        "warnings": [],
    }


@pytest.mark.asyncio
async def test_market_interpretation_status_ok_on_success(monkeypatch):
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

    async def _ok_market_interpretation(self, result, prior_context=None):
        return {"summary": "시장분석 정상 생성"}

    monkeypatch.setattr(SiteAnalysisInterpreter, "generate_interpretation", _no_interpretation, raising=True)
    monkeypatch.setattr(MarketInterpreter, "generate_interpretation", _ok_market_interpretation, raising=True)

    result = await svc.analyze("시장분석정상-QA", tenant_id="t-market-ok", project_id=None)
    assert result["market_interpretation"] == {"summary": "시장분석 정상 생성"}
    assert result["market_interpretation_status"] == {"status": "ok"}


@pytest.mark.asyncio
async def test_market_interpretation_status_unavailable_on_failure(monkeypatch):
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

    async def _boom(self, result, prior_context=None):
        raise RuntimeError("llm timeout(qa 재현)")

    monkeypatch.setattr(SiteAnalysisInterpreter, "generate_interpretation", _no_interpretation, raising=True)
    monkeypatch.setattr(MarketInterpreter, "generate_interpretation", _boom, raising=True)

    result = await svc.analyze("시장분석실패-QA", tenant_id="t-market-fail", project_id=None)
    assert result["market_interpretation"] is None  # 기존 동작 불변
    status = result["market_interpretation_status"]
    assert status["status"] == "unavailable"
    assert "RuntimeError" in status["reason"]
    assert "llm timeout" in status["reason"]
