"""(P1 B-1 G6) POST /api/v1/development-methods/optimal-recommend — use_llm 게이트 회귀.

use_llm(신설 additive 필드, 기본 false)이 기존 응답을 절대 바꾸지 않는지(무회귀) +
false일 때 DevelopmentMethodInterpreter가 0회 호출되는지(cost.py TestCostUseLlmGate와
동일한 계약 스타일 — monkeypatch로 인터프리터를 대역 처리해 호출 횟수 확인)를 검증한다.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.development.integrated_recommender.orchestrator import IntegratedRecommender
from apps.api.database.session import get_db
from routers.development_methods import router

FAKE_RESULT = {
    "site": {"addresses": ["서울특별시 강남구 역삼동 123"], "parcel_count": 1, "primary_zone": "일반상업지역"},
    "gate": {"developability": "POSSIBLE", "resolvable": None},
    "integrated_area_sqm": 660.0,
    "baseline_far_pct": 800.0,
    "ranked": [{"method": "M06", "type_name": "오피스텔", "composite": 72.3}],
    "scenario_status": "actual",
    "land_price_reliable": True,
    "honest_disclosure": "",
    "note": "테스트",
    "evidence": None,
}


def _client(monkeypatch):
    async def _fake_recommend(self, addresses, parcel_subset_policy="전체"):  # noqa: ANN001, ARG001
        return dict(FAKE_RESULT)

    monkeypatch.setattr(IntegratedRecommender, "recommend", _fake_recommend, raising=True)

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/development-methods")

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
        "app.services.ai.development_method_interpreter.DevelopmentMethodInterpreter",
        _Boom, raising=False,
    )
    client = _client(monkeypatch)
    resp = client.post(
        "/api/v1/development-methods/optimal-recommend",
        json={"addresses": ["서울특별시 강남구 역삼동 123"]},
    )
    assert resp.status_code == 200
    assert calls["n"] == 0  # 인터프리터 0회 호출(무과금)
    body = resp.json()
    assert "ai_interpretation" not in body  # additive 키 미부착
    assert body == FAKE_RESULT  # 기존 응답 완전 불변(무회귀)


def test_use_llm_true_invokes_interpreter_and_attaches_ai_interpretation(monkeypatch):
    calls = {"n": 0}

    class _Fake:
        def __init__(self):
            calls["n"] += 1

        async def generate_interpretation(self, _data):
            return {"overall_recommendation": "요약"}

    monkeypatch.setattr(
        "app.services.ai.development_method_interpreter.DevelopmentMethodInterpreter",
        _Fake, raising=False,
    )
    client = _client(monkeypatch)
    resp = client.post(
        "/api/v1/development-methods/optimal-recommend",
        json={"addresses": ["서울특별시 강남구 역삼동 123"], "use_llm": True},
    )
    assert resp.status_code == 200
    assert calls["n"] == 1
    assert resp.json()["ai_interpretation"] == {"overall_recommendation": "요약"}
