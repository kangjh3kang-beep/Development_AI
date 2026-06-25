"""시장조사보고서 PDF 라우트(POST /api/v1/market/report/pdf) XML 이스케이프 통합 테스트.

라이브 라우트에서 '<' 가 섞인 주소/상호가 들어와도 reportlab ValueError(→HTTP500)가 나지 않고
application/pdf 200 + %PDF 바디로 응답하는지 검증한다(decision_brief 라우트 테스트 패턴 복제).

경량 TestClient — 인증·과금 게이트·MarketReportService.build_report(네트워크) 를 override/
monkeypatch 로 대체하고, 실제 to_pdf(reportlab) 렌더 + 라우트 계약(헤더·바디)만 결정론적으로
검증한다(라이브 공공API·DB·LLM 은 deploy-pending).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.market.market_report_service import MarketReportService
from apps.api.auth.jwt_handler import get_current_user
from apps.api.routers import market_report as market_router


class _User:
    id = "u1"
    tenant_id = "t1"
    role = "user"
    is_active = True


def _rep_with_xml() -> dict:
    """to_pdf 가 렌더할 rep — 주소·내러티브·출처에 reportlab 을 깨뜨리던 '<','&','</para>' 주입."""
    return {
        "address": "서울 <강남> & 역삼 </para> 1<2",
        "generated_at": "2026-06-25 <t> & x",
        "months": ["202604", "202605", "202606"],
        "coordinates": {},
        "narrative": {
            "summary": "시장 <요약> & 분석 </para>",
            "opportunities": ["기회 <요인> & 1"],
            "risks": ["리스크 <요인> & 1"],
            "price_trend": "동향 <상승> & 보합",
        },
        "zone_type": "일반상업 <지역> & x",
        "trade": {}, "rent": {}, "apt_trend": [],
        "raw_data": {}, "pricing_band": {},
    }


def _build_app(monkeypatch) -> FastAPI:
    # 과금 게이트(enforce_llm_quota)는 라우터 dependencies 에 박혀 있어 override 가 까다롭다 →
    #   use_llm=False 로 호출하고, 게이트 내부 차단 함수만 통과(False)로 monkeypatch 한다.
    from app.services.billing import billing_service

    async def _not_blocked(*_a, **_k):
        return False

    monkeypatch.setattr(billing_service, "is_blocked", _not_blocked, raising=False)
    monkeypatch.setattr(billing_service, "team_limit_exceeded", _not_blocked, raising=False)

    # build_report(네트워크: MOLIT·토지정보)를 XML 폭탄 rep 로 대체 — to_pdf 는 실제 렌더.
    async def _fake_build_report(self, *_a, **_k):
        return _rep_with_xml()

    monkeypatch.setattr(MarketReportService, "build_report", _fake_build_report)

    app = FastAPI()
    app.include_router(market_router.router)
    app.dependency_overrides[get_current_user] = lambda: _User()
    return app


def test_market_report_pdf_route_xml_address_no_500(monkeypatch):
    app = _build_app(monkeypatch)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/market/report/pdf",
        # pnu 로 lawd_cd 결정(네트워크 불요) — '<' 가 섞인 주소도 그대로 통과해야 한다.
        json={"address": "서울 <강남> & 역삼 </para> 1<2", "pnu": "1168010100", "use_llm": False},
    )
    # 과거: 주소의 '<' 가 reportlab Paragraph 를 깨 ValueError→500. 기대: 이스케이프해 200 PDF.
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
