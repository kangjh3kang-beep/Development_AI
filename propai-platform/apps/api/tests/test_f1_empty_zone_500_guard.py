"""F1(QA REQUEST CHANGES·차단) 빈 zone 단일필지 500 크래시 회귀 테스트.

재현 체인(QA 고정): comprehensive_analysis_service.py:427-428(sec1 effective_far_pct=None,
P0-1 무날조 정직 반환) → :538(공급면적 산정 호출부) → :941(_calc_supply_areas 내부
min(effective_far, typical_far))에서 get_permitted_types("")가 부분일치 검색
(`zone_type in key` — 빈 문자열은 모든 키와 매칭)으로 permitted가 비지 않게 반환돼
'미등재 용도지역 판정불가' 조기반환을 우회하고 None×int 비교로 TypeError(500)가 났다.

이 테스트는 zone_type=""(용도지역 미확인) 단일필지 analyze() 경로가 크래시 없이
supply_areas에 blocked_reason을 담아 정직 반환하는지 검증한다.
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


def _fake_base_empty_zone() -> dict:
    """QA 재현 케이스: 용도지역 미확인(zone_type="") 단일필지. effective_far 사전주입 없음
    (calc_effective_far가 직접 호출되어 P0-1 무날조 None 경로를 타게 한다).

    nearby_transactions/infrastructure/coordinates를 사전 채워 _research_transactions의
    실거래 외부호출(MOLIT)을 건너뛰게 한다(테스트 결정론·네트워크 지연 회피 — F1 게이트
    자체와 무관한 외부 API 왕복은 이 테스트의 관심사가 아니다).
    """
    return {
        "pnu": "0000000000000000000",
        "zone_type": "",
        "land_register": {"area_sqm": 500.0},
        "nearby_transactions": {"note": "stub — 테스트 결정론화"},
        "infrastructure": {},
        "coordinates": {},
        "warnings": [],
    }


async def test_empty_zone_single_parcel_analyze_no_crash_blocked_reason(monkeypatch):
    if not await _db_available():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행(skip≠검증)")
    from app.services.ai.market_interpreter import MarketInterpreter
    from app.services.ai.site_analysis_interpreter import SiteAnalysisInterpreter
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )

    svc = ComprehensiveAnalysisService()

    async def _fake_collect(self, address, pnu=None):
        return _fake_base_empty_zone()

    monkeypatch.setattr(type(svc.land_info), "collect_comprehensive", _fake_collect, raising=True)

    # AI 해석기(LLM 실호출)는 이 테스트의 관심사가 아니다(F1 게이트는 AI 해석 이전 단계에서
    # 결정된다) — 실LLM 키 미구성 환경에서 무한 대기하지 않도록 no-op으로 대체한다.
    async def _no_interpretation(self, result, prior_context=None):
        return None

    monkeypatch.setattr(SiteAnalysisInterpreter, "generate_interpretation", _no_interpretation, raising=True)
    monkeypatch.setattr(MarketInterpreter, "generate_interpretation", _no_interpretation, raising=True)

    # 크래시(500) 없이 완주해야 한다 — 예외가 나면 pytest가 즉시 실패로 잡아준다.
    result = await svc.analyze("빈용도지역-QA재현-F1", tenant_id="t-f1-empty-zone", project_id=None)

    assert result["effective_far"]["effective_far_pct"] is None
    supply = result["supply_areas"]
    assert isinstance(supply, list) and len(supply) == 1
    assert supply[0].get("blocked_reason"), "빈 zone 케이스는 blocked_reason이 정직 표기돼야 한다"
    assert "용도지역 미확인" in supply[0]["blocked_reason"]
    # 임의 세대수·GFA를 지어내지 않았는지 확인(가짜 dev_type/type_name 없음).
    assert supply[0].get("development_type") is None
