"""히스토리 확산 — /feasibility/rough-scenario 원장 배선 라우터 테스트(경량 TestClient).

개략수지는 완전 무기록·무인증이었다(진단 결과). 이 테스트는:
  1) optional 인증(get_current_user_optional) 부착으로 비로그인도 200(투자분석 체험 무회귀).
  2) ★P3(R1 REVISE): 비로그인은 원장 기록을 완전히 skip한다(precheck.py와 대칭 — 과거엔
     로그인 여부와 무관하게 tenant_id=None으로 기록했으나, GET /analysis-ledger/history가
     JWT 필수라 익명 기록은 아무도 조회할 수 없는 write-only 고아 + NULL 쿼터 낭비였다).
  3) 로그인 시에만 summary에 profit_rate_pct(roi_pct 우선, 없으면
     cashflow.summary.profit_rate_pct 폴백)·npv_won·total_revenue_won·net_profit_won·grade가
     실려 DIFF_FIELD_MAP.feasibility와 정합.
  4) project_id는 의도적으로 미전달(address 스코프) — VCS-result(record_feasibility_result,
     project_id 스코프+address=None)의 "feasibility" 체인과 자동 분리된다.

build_rough_scenario/record_user_analysis는 monkeypatch로 대체해 외부 엔진 호출 없이
라우터의 인증분기 + 매핑 로직만 검증한다.
"""
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.routers import v2_feasibility
from app.services.auth.auth_service import get_current_user_optional

_ADDR = "서울특별시 강남구 역삼동 736"

_SCENARIO_ROI = {
    "address": _ADDR,
    "inputs": {"land_area_sqm": 1000.0, "dev_type": "M06", "gfa_sqm": 2000.0},
    "summary": {
        "total_cost_won": 12_000_000_000, "net_profit_won": 4_000_000_000,
        "roi_pct": 33.3, "npv_won": 3_000_000_000,
        "total_revenue_won": 16_000_000_000, "grade": "B",
    },
    "cashflow": {"monthly_rows": [{"month": 0}], "summary": {}},
    "overrides_applied": [], "degraded_notes": [],
}

# roi_pct 결측 — cashflow.summary.profit_rate_pct 폴백 검증용.
_SCENARIO_ROI_NONE = {
    "address": _ADDR,
    "inputs": {"land_area_sqm": 1000.0, "dev_type": "M06", "gfa_sqm": 2000.0},
    "summary": {
        "total_cost_won": 12_000_000_000, "net_profit_won": 4_000_000_000,
        "roi_pct": None, "npv_won": 3_000_000_000,
        "total_revenue_won": 16_000_000_000, "grade": "C",
    },
    "cashflow": {"monthly_rows": [{"month": 0}], "summary": {"profit_rate_pct": 25.0}},
    "overrides_applied": [], "degraded_notes": [],
}


class _FakeUser:
    def __init__(self, tenant_id):
        self.id = uuid.uuid4()
        self.tenant_id = tenant_id


def _make_client(monkeypatch, *, fake_scenario, record_calls=None, authed_tenant=None):
    async def _fake_build(**kwargs):
        return dict(fake_scenario)

    monkeypatch.setattr(v2_feasibility, "build_rough_scenario", _fake_build)

    if record_calls is not None:
        import app.services.ledger.ledger_adapters as ledger_adapters

        async def _fake_record(**kwargs):
            record_calls.append(kwargs)
            return {"ok": True, "content_hash": "fakehash-rough", "version": 1}

        monkeypatch.setattr(ledger_adapters, "record_user_analysis", _fake_record)

    app = FastAPI()
    app.include_router(v2_feasibility.router)

    async def _override_db():
        yield None

    app.dependency_overrides[get_db] = _override_db
    if authed_tenant is not None:
        app.dependency_overrides[get_current_user_optional] = lambda: _FakeUser(authed_tenant)
    return TestClient(app)


def test_rough_scenario_anonymous_returns_200_and_skips_ledger(monkeypatch):
    """optional 인증 무회귀 — 비로그인도 200이며, 원장 기록은 완전히 skip된다(precheck.py와 대칭).

    ★P3(R1 REVISE) 회귀: 익명 기록(tenant_id=None)은 JWT 필수인 /history에서 아무도 조회할 수
    없는 write-only 고아였다 — record_user_analysis 자체가 호출되지 않아야 한다.
    """
    calls: list = []
    client = _make_client(monkeypatch, fake_scenario=_SCENARIO_ROI, record_calls=calls)
    resp = client.post("/api/v2/feasibility/rough-scenario", json={"address": _ADDR})
    assert resp.status_code == 200
    body = resp.json()
    assert "ledger_hash" not in body
    assert calls == []  # record_user_analysis 자체가 호출되지 않아야 함(비로그인 skip)


def test_rough_scenario_records_feasibility_keymap_fields(monkeypatch):
    calls: list = []
    tid = uuid.uuid4()
    client = _make_client(monkeypatch, fake_scenario=_SCENARIO_ROI, record_calls=calls, authed_tenant=tid)
    resp = client.post("/api/v2/feasibility/rough-scenario", json={"address": _ADDR})
    assert resp.status_code == 200
    assert resp.json().get("ledger_hash") == "fakehash-rough"

    assert len(calls) == 1
    kw = calls[0]
    assert kw["analysis_type"] == "feasibility"
    assert kw["tenant_id"] == str(tid)
    assert kw["address"] == _ADDR
    assert kw["source"] == "rough_scenario"
    assert "project_id" not in kw  # ★address/pnu 스코프 — project_id 의도적 미전달
    assert kw["parcel_count"] == 1
    assert kw["use_llm"] is False

    summ = kw["summary"]
    assert summ["profit_rate_pct"] == 33.3  # roi_pct 채택
    assert summ["npv_won"] == 3_000_000_000
    assert summ["total_revenue_won"] == 16_000_000_000
    assert summ["net_profit_won"] == 4_000_000_000
    assert summ["grade"] == "B"


def test_rough_scenario_profit_rate_pct_falls_back_to_cashflow_summary(monkeypatch):
    calls: list = []
    client = _make_client(
        monkeypatch, fake_scenario=_SCENARIO_ROI_NONE, record_calls=calls, authed_tenant=uuid.uuid4(),
    )
    resp = client.post("/api/v2/feasibility/rough-scenario", json={"address": _ADDR})
    assert resp.status_code == 200
    assert calls[0]["summary"]["profit_rate_pct"] == 25.0  # cashflow.summary 폴백
    assert calls[0]["summary"]["grade"] == "C"


def test_rough_scenario_ledger_failure_does_not_break_response(monkeypatch):
    """원장 적재 실패(예외)해도 개략수지 결과는 무손상 반환(best-effort try/except).

    로그인 사용자로 오버라이드해야 히스토리 기록 분기(현재는 로그인 시에만 진입)가 실제로
    실행되어 이 실패 경로를 검증한다 — 익명이면 P3 skip 분기에 걸려 record_user_analysis
    자체가 호출되지 않아 이 테스트의 의도(적재 실패 방어)를 놓친다.
    """
    async def _fake_build(**kwargs):
        return dict(_SCENARIO_ROI)

    monkeypatch.setattr(v2_feasibility, "build_rough_scenario", _fake_build)

    import app.services.ledger.ledger_adapters as ledger_adapters

    async def _boom(**kwargs):
        raise RuntimeError("ledger down")

    monkeypatch.setattr(ledger_adapters, "record_user_analysis", _boom)

    app = FastAPI()
    app.include_router(v2_feasibility.router)

    async def _override_db():
        yield None

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user_optional] = lambda: _FakeUser(uuid.uuid4())
    client = TestClient(app)

    resp = client.post("/api/v2/feasibility/rough-scenario", json={"address": _ADDR})
    assert resp.status_code == 200
    body = resp.json()
    assert "ledger_hash" not in body
    assert body["summary"]["total_cost_won"] == 12_000_000_000  # 결과 자체는 무손상
