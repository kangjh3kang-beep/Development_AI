"""시니어 자문 라우터 — 엔드포인트 동작(최소앱 TestClient·auth override·무DB)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.auth.jwt_handler import get_current_user
from apps.api.database.session import get_db
from apps.api.routers import senior_agents as senior_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(senior_router.router, prefix="/api/v1")
    # auth·db 의존성 오버라이드(use_llm=False 경로는 db 미사용 — 더미 주입)
    app.dependency_overrides[get_current_user] = lambda: {"id": "t", "tenant_id": "t"}
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


def test_list_agents():
    r = _client().get("/api/v1/senior/agents")
    assert r.status_code == 200
    agents = r.json()["agents"]
    assert len(agents) == 7
    keys = {a["key"] for a in agents}
    assert {"senior_financial_advisor", "senior_urban_planner"} <= keys
    # 고위험 플래그 노출
    assert any(a["high_risk"] for a in agents)


def test_consult_single_high_risk():
    r = _client().post("/api/v1/senior/consult", json={
        "domain": "금융",
        "context": {"data_completeness": 0.8, "rule_fit": 0.9, "rag_strength": 0.7, "correction_rate": 0.1},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["agent_key"] == "senior_financial_advisor"
    assert body["high_risk"] is True
    # citation 게이트: 판단 전부 근거 동반
    assert body["decision_framework"] and all(d["basis"] for d in body["decision_framework"])
    assert "최종" in body["license_gate"]
    assert 0.0 <= body["confidence"] <= 1.0


def test_consult_unknown_returns_404():
    r = _client().post("/api/v1/senior/consult", json={"domain": "우주항공"})
    assert r.status_code == 404


def test_consult_multi_dedup():
    r = _client().post("/api/v1/senior/consult-multi",
                       json={"domains": ["도시계획", "금융", "urban", "우주"]})
    assert r.status_code == 200
    cons = r.json()["consultations"]
    assert [c["agent_key"] for c in cons] == ["senior_urban_planner", "senior_financial_advisor"]


def test_consult_requires_auth():
    # 오버라이드 없는 앱 → get_current_user 미충족(401/403)
    app = FastAPI()
    app.include_router(senior_router.router, prefix="/api/v1")
    r = TestClient(app).get("/api/v1/senior/agents")
    assert r.status_code in (401, 403)


# ── 리뷰 HIGH/MED: 입력검증(미처리 500·정보노출 차단) ──

def test_consult_matched_rule_ids_non_list_returns_422():
    # ★HIGH: 비-리스트 matched_rule_ids → 500 아닌 422(스택 노출 차단)
    r = _client().post("/api/v1/senior/consult",
                       json={"domain": "도시계획", "context": {"matched_rule_ids": 123}})
    assert r.status_code == 422


def test_consult_matched_rule_ids_non_string_elem_422():
    r = _client().post("/api/v1/senior/consult",
                       json={"domain": "도시계획", "context": {"matched_rule_ids": [1, 2]}})
    assert r.status_code == 422


def test_consult_matched_rule_ids_valid_filters():
    r = _client().post("/api/v1/senior/consult",
                       json={"domain": "도시계획",
                             "context": {"matched_rule_ids": ["urban.upzone_potential"]}})
    assert r.status_code == 200
    ids = [d["rule_id"] for d in r.json()["decision_framework"]]
    assert ids == ["urban.upzone_potential"]


def test_consult_domain_whitespace_stripped():
    r = _client().post("/api/v1/senior/consult", json={"domain": "  금융  "})
    assert r.status_code == 200
    assert r.json()["agent_key"] == "senior_financial_advisor"


def test_consult_domain_blank_422():
    r = _client().post("/api/v1/senior/consult", json={"domain": "   "})
    assert r.status_code == 422


def test_consult_multi_too_many_domains_422():
    r = _client().post("/api/v1/senior/consult-multi", json={"domains": ["금융"] * 21})
    assert r.status_code == 422


# ── use_llm: AI 서술(narrative) 경로 ──

def test_consult_default_no_llm_structured():
    # use_llm 미지정(기본 False) → narrative 없음(결정론). include_reasoning 미요청이라 reasoning None.
    r = _client().post("/api/v1/senior/consult", json={"domain": "금융"})
    assert r.status_code == 200
    assert r.json().get("reasoning") is None


def test_consult_use_llm_injects_narrative(monkeypatch):
    # use_llm=True → 추론 동반 강제 + narrative 주입(LLM·과금게이트 모킹).
    async def fake_narrative(prompt, *, use_llm):
        return "종합: 조건부 Go(모킹)"

    async def fake_enforce(db):
        return None

    monkeypatch.setattr(senior_router, "generate_senior_narrative", fake_narrative)
    monkeypatch.setattr("app.core.billing_deps.enforce_llm_quota", fake_enforce, raising=False)

    r = _client().post("/api/v1/senior/consult", json={"domain": "금융", "use_llm": True})
    assert r.status_code == 200
    reasoning = r.json()["reasoning"]
    assert reasoning is not None  # use_llm → include_reasoning 강제
    assert reasoning["mode"] == "llm" and reasoning["narrative"] == "종합: 조건부 Go(모킹)"


def test_consult_use_llm_graceful_when_narrative_none(monkeypatch):
    # LLM 미설정/실패(narrative None) → 결정론 구조 유지(서비스 중단 없음).
    async def none_narrative(prompt, *, use_llm):
        return None

    async def fake_enforce(db):
        return None

    monkeypatch.setattr(senior_router, "generate_senior_narrative", none_narrative)
    monkeypatch.setattr("app.core.billing_deps.enforce_llm_quota", fake_enforce, raising=False)

    r = _client().post("/api/v1/senior/consult", json={"domain": "금융", "use_llm": True})
    assert r.status_code == 200
    reasoning = r.json()["reasoning"]
    assert reasoning is not None and reasoning["mode"] == "structured" and reasoning["narrative"] is None
