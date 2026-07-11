"""(P1 B-1 G6) POST /api/v2/feasibility/development-finance — use_llm 게이트 회귀.

use_llm(신설 additive 필드, 기본 false)이 기존 응답(PF/브릿지/LTV/DSCR 산출)을 절대 바꾸지
않는지(무회귀) + false일 때 FinanceInterpreter가 0회 호출되는지를 검증한다
(app/routers/cost.py TestCostUseLlmGate와 동일한 계약 스타일).
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routers.v2_feasibility import router

BASE_BODY = {
    "total_project_cost_won": 10_000_000_000,
    "equity_ratio": 0.3,
    "land_cost_won": 3_000_000_000,
    "credit_grade": "A",
    "presale_ratio": 0.0,
    "bridge_months": 12,
    "pf_months": 30,
}


def _client():
    app = FastAPI()
    app.include_router(router)

    async def _odb():
        yield None

    app.dependency_overrides[get_db] = _odb
    return TestClient(app)


def test_use_llm_false_never_calls_interpreter_and_response_unchanged(monkeypatch):
    calls = {"n": 0}

    class _Boom:
        def __init__(self):
            calls["n"] += 1

        async def generate_interpretation(self, _data):
            return {}

    monkeypatch.setattr(
        "app.services.ai.finance_interpreter.FinanceInterpreter", _Boom, raising=False,
    )
    client = _client()
    resp = client.post("/api/v2/feasibility/development-finance", json=BASE_BODY)
    assert resp.status_code == 200
    assert calls["n"] == 0  # 인터프리터 0회 호출(무과금)
    body = resp.json()
    assert "ai_interpretation" not in body  # additive 키 미부착

    # use_llm 필드가 없던 기존 요청과 동일 산출(PF/브릿지/LTV/DSCR 키·값 무회귀).
    resp_legacy = client.post(
        "/api/v2/feasibility/development-finance",
        json={k: v for k, v in BASE_BODY.items()},
    )
    assert resp.json() == resp_legacy.json()
    assert body["ltv"] == body["total_debt_won"] / body["total_project_cost_won"]
    assert "pf_loan" in body and "bridge_loan" in body


def test_use_llm_true_invokes_interpreter_and_attaches_ai_interpretation(monkeypatch):
    calls = {"n": 0}

    class _Fake:
        def __init__(self):
            calls["n"] += 1

        async def generate_interpretation(self, _data):
            return {"structure_analysis": "요약"}

    monkeypatch.setattr(
        "app.services.ai.finance_interpreter.FinanceInterpreter", _Fake, raising=False,
    )
    client = _client()
    resp = client.post(
        "/api/v2/feasibility/development-finance",
        json={**BASE_BODY, "use_llm": True},
    )
    assert resp.status_code == 200
    assert calls["n"] == 1
    assert resp.json()["ai_interpretation"] == {"structure_analysis": "요약"}
