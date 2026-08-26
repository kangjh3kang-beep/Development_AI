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


# ── 간략 수지 원장 배선 — **소스가 아니라 실제 라우트 응답**을 본다 ──────────────
#   ★소스에 `build_legacy_ledger(` 가 있는지 grep 하는 락은 호출을 주석 처리하고
#     import 를 남기는 변이에 뚫린다(이 저장소에서 2회 실증). 라우트를 태워 응답을 본다.
def test_rough_scenario_response_carries_legacy_ledger(monkeypatch):
    """★라우트 응답에 원장이 실린다 — 검산·커버리지까지 함께."""
    client = _make_client(monkeypatch, fake_scenario=_SCENARIO_ROI)
    resp = client.post("/api/v2/feasibility/rough-scenario", json={"address": _ADDR})
    assert resp.status_code == 200
    led = resp.json().get("legacy_ledger")
    assert led is not None, "원장이 응답에 없다 — 배선이 끊겼다"
    assert [s["key"] for s in led["sections"]] == ["revenue", "cost", "profit"]
    assert {c["key"] for c in led["checks"]} >= {
        "revenue_total", "cost_total", "pretax_profit", "charges_items_vs_total"
    }
    assert led["coverage"]["items"] > 0


def test_legacy_ledger_check_detects_engine_summary_drift_through_the_route(monkeypatch):
    """★★검산이 **라우트를 통과해서도** 살아 있다 — 엔진 합계를 어긋뜨리면 ERROR.

    두 모집단으로 가른다: 정상 시나리오는 `cost_total=OK`, 어긋난 시나리오는 `ERROR`.
    한쪽만 보면 *"항상 OK"* 인 검산기도 만점을 받는다.
    """
    # ★`_SCENARIO_ROI` 는 축 블록이 없어 원장이 **판정 불가(UNKNOWN)** 를 낸다 —
    #   그 픽스처로는 정상/어긋남이 둘 다 UNKNOWN 이라 **두 모집단이 안 갈린다**.
    #   판정이 가능한 시나리오를 따로 만든다(합계가 실제로 맞아떨어지게).
    judgeable = dict(_SCENARIO_ROI)
    judgeable["summary"] = dict(_SCENARIO_ROI["summary"])
    judgeable["revenue"] = {"total_won": 16_000_000_000, "sale_price_per_pyeong": 20_000_000,
                            "saleable_area_pyeong": 800.0, "basis": "실거래", "source": "molit"}
    judgeable["land_cost"] = {"total_won": 5_000_000_000, "per_sqm_won": 5_000_000,
                              "basis": "탁상감정", "evidence": None, "source": "desk"}
    judgeable["construction_cost"] = {"total_won": 6_000_000_000, "unit_per_sqm_won": 3_000_000,
                                      "basis": "국토부 SSOT", "source": "engine"}
    judgeable["cost_breakdown"] = {"land_won": 5_000_000_000, "construction_won": 6_000_000_000,
                                   "finance_won": 600_000_000, "other_won": 400_000_000,
                                   "charges_won": 0}
    judgeable["charges"] = {"total_won": 0, "construction_stage_won": 0, "sale_stage_won": 0,
                            "buyer_borne_total_won": 0, "items": [], "basis": "", "source": ""}

    ok_client = _make_client(monkeypatch, fake_scenario=judgeable)
    ok = ok_client.post("/api/v2/feasibility/rough-scenario", json={"address": _ADDR}).json()
    ok_v = {c["key"]: c["verdict"] for c in ok["legacy_ledger"]["checks"]}
    assert ok_v["revenue_total"] == "OK", f"전제가 깨졌다 — 정상이 OK 가 아니다: {ok_v}"

    drifted = dict(judgeable)
    drifted["summary"] = dict(judgeable["summary"])
    drifted["summary"]["total_revenue_won"] = 999_999_999_999
    bad_client = _make_client(monkeypatch, fake_scenario=drifted)
    bad = bad_client.post("/api/v2/feasibility/rough-scenario", json={"address": _ADDR}).json()
    bad_v = {c["key"]: c["verdict"] for c in bad["legacy_ledger"]["checks"]}

    assert ok_v["revenue_total"] != bad_v["revenue_total"], (
        "정상과 어긋남이 같은 판정을 냈다 — 검산이 입력을 안 읽는다"
    )
    assert bad_v["revenue_total"] == "ERROR"


def test_legacy_ledger_failure_does_not_break_the_response(monkeypatch):
    """표시층이 죽어도 개략수지 본체는 산다(원장 적재 실패 규율과 대칭)."""
    def _boom(_scenario):
        raise RuntimeError("원장 생성 실패 재현")

    monkeypatch.setattr(v2_feasibility, "build_legacy_ledger", _boom)
    client = _make_client(monkeypatch, fake_scenario=_SCENARIO_ROI)
    resp = client.post("/api/v2/feasibility/rough-scenario", json={"address": _ADDR})
    assert resp.status_code == 200
    body = resp.json()
    assert body["legacy_ledger"] is None
    assert body["summary"]["grade"] == "B", "본체가 손상됐다"
