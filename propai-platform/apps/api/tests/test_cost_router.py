"""v61 공사비 라우터 테스트 — 경량 TestClient (전체 앱 비의존)."""

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.cost import router
from app.services.auth.auth_service import get_current_user


class _User:
    """get_current_user 의존성 override용 스텁(실 JWT·DB 불요)."""

    id = "00000000-0000-0000-0000-000000000001"
    tenant_id = "00000000-0000-0000-0000-000000000002"
    role = "user"
    is_active = True


_app = FastAPI()
_app.include_router(router)
# P0-4 보안: cost 라우터는 라우터 레벨 Depends(get_current_user)로 전 라우트 인증 강제.
# 테스트는 실 JWT·DB 없이 인증된 사용자를 주입(의존성 override)해 라우트 동작을 검증한다.
_app.dependency_overrides[get_current_user] = lambda: _User()
client = TestClient(_app)

PROJECT_ID = "test-project-cost"

IFC_ELEMENTS = [
    {"element_type": "IfcWall", "quantity": 100, "global_id": "w1",
     "name": "외벽", "unit": "m3"},
    {"element_type": "IfcSlab", "quantity": 200, "global_id": "s1",
     "name": "슬래브", "unit": "m3"},
    {"element_type": "IfcDoor", "quantity": 50, "global_id": "d1",
     "name": "현관문", "unit": "set"},
]

COST_ITEMS = [
    {"work_code": "A01", "item_name": "콘크리트", "spec": "25-240",
     "unit": "m3", "quantity": 500, "mat_unit": 82000,
     "labor_unit": 45000, "exp_unit": 15000},
    {"work_code": "A05", "item_name": "창호", "spec": "AL",
     "unit": "set", "quantity": 200, "mat_unit": 350000,
     "labor_unit": 80000, "exp_unit": 20000},
]


class TestUploadIFC:

    def test_upload_ifc(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/upload-ifc", json={
            "elements": IFC_ELEMENTS,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["item_count"] > 0
        assert len(data["unique_work_codes"]) > 0


class TestCalculateCost:

    def test_calculate(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/calculate", json={
            "items": COST_ITEMS,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_project_cost"] > 0
        assert data["item_count"] == 2
        assert data["project_id"] == PROJECT_ID

    def test_calculate_with_custom_rates(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/calculate", json={
            "items": COST_ITEMS,
            "rates": {
                "indirect_labor_rate": 0.15,
                "industrial_accident": 0.04,
                "employment_insurance": 0.01,
                "health_insurance_emp": 0.04,
                "national_pension_emp": 0.05,
                "long_term_care": 0.005,
                "retirement_fund": 0.025,
                "safety_health": 0.025,
                "env_preserve": 0.002,
                "general_mgmt": 0.06,
                "profit": 0.15,
                "vat": 0.10,
            },
        })
        assert resp.status_code == 200


class TestCostUseLlmGate:
    """T3: use_llm 게이트 — 기본 false는 CostInterpreter(LLM) 0호출, true는 과금 게이트 적용."""

    def test_calculate_use_llm_false_never_calls_interpreter(self, monkeypatch):
        calls = {"n": 0}

        class _Boom:
            def __init__(self):
                calls["n"] += 1

            async def generate_interpretation(self, _payload):
                return {}

        monkeypatch.setattr(
            "app.services.ai.cost_interpreter.CostInterpreter", _Boom, raising=False,
        )
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/calculate", json={"items": COST_ITEMS})
        assert resp.status_code == 200
        assert calls["n"] == 0
        assert resp.json().get("ai_cost_analysis") is None

    def test_calculate_use_llm_true_invokes_interpreter(self, monkeypatch):
        calls = {"n": 0}

        class _Fake:
            def __init__(self):
                calls["n"] += 1

            async def generate_interpretation(self, _payload):
                return {"cost_analysis": "요약"}

        monkeypatch.setattr(
            "app.services.ai.cost_interpreter.CostInterpreter", _Fake, raising=False,
        )
        resp = client.post(
            f"/api/v1/cost/{PROJECT_ID}/calculate",
            json={"items": COST_ITEMS, "use_llm": True},
        )
        assert resp.status_code == 200
        assert calls["n"] == 1
        assert resp.json().get("ai_cost_analysis") == "요약"

    def test_calculate_use_llm_true_quota_402(self, monkeypatch):
        async def blocked(db, uid):
            return True

        async def not_team_over(db, uid):
            return False

        monkeypatch.setattr("app.core.billing_deps.get_current_user_id", lambda: "u1")
        monkeypatch.setattr("app.core.billing_deps.billing_service.is_blocked", blocked, raising=False)
        monkeypatch.setattr(
            "app.core.billing_deps.billing_service.team_limit_exceeded", not_team_over, raising=False,
        )
        resp = client.post(
            f"/api/v1/cost/{PROJECT_ID}/calculate",
            json={"items": COST_ITEMS, "use_llm": True},
        )
        assert resp.status_code == 402

    def test_boq_use_llm_true_quota_402(self, monkeypatch):
        async def blocked(db, uid):
            return True

        async def not_team_over(db, uid):
            return False

        monkeypatch.setattr("app.core.billing_deps.get_current_user_id", lambda: "u1")
        monkeypatch.setattr("app.core.billing_deps.billing_service.is_blocked", blocked, raising=False)
        monkeypatch.setattr(
            "app.core.billing_deps.billing_service.team_limit_exceeded", not_team_over, raising=False,
        )
        resp = client.post(
            f"/api/v1/cost/{PROJECT_ID}/boq",
            json={"total_gfa_sqm": 3000.0, "persist": False, "use_llm": True},
        )
        assert resp.status_code == 402


class TestSeniorQsConsultation:
    """P3: with_senior opt-in — /calculate·/estimate-overview 시니어 적산(QS) 자문 배선."""

    def test_calculate_with_senior_default_false_omits_consultation(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/calculate", json={"items": COST_ITEMS})
        assert resp.status_code == 200
        assert "senior_consultation" not in resp.json()

    def test_calculate_with_senior_true_flags_general_mgmt_over_cap(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/calculate", json={
            "items": COST_ITEMS,
            "rates": {
                "indirect_labor_rate": 0.1440, "industrial_accident": 0.0350,
                "employment_insurance": 0.0090, "health_insurance_emp": 0.03595,
                "national_pension_emp": 0.04750, "long_term_care": 0.004724,
                "retirement_fund": 0.02100, "safety_health": 0.02070,
                "env_preserve": 0.00160,
                "general_mgmt": 0.08,  # 법정 상한(6%) 초과 → BLOCK 기대
                "profit": 0.15, "vat": 0.10,
            },
            "with_senior": True,
        })
        assert resp.status_code == 200
        sc = resp.json()["senior_consultation"]
        assert sc["verdict"] == "BLOCK"
        ev = {e["rule_id"]: e for e in sc["evaluations"]}
        assert ev["qs.general_mgmt_cap"]["verdict"] == "BLOCK"
        assert ev["qs.profit_cap"]["verdict"] == "PASS"

    def test_estimate_overview_with_senior_default_false_omits_consultation(self):
        resp = client.post(
            "/api/v1/cost/estimate-overview",
            json={"building_type": "apartment", "total_gfa_sqm": 3000.0,
                  "floor_count_above": 10, "floor_count_below": 1, "structure_type": "RC"},
        )
        assert resp.status_code == 200
        assert "senior_consultation" not in resp.json()

    def test_estimate_overview_with_senior_true_attaches_consultation(self):
        resp = client.post(
            "/api/v1/cost/estimate-overview",
            json={"building_type": "apartment", "total_gfa_sqm": 3000.0,
                  "floor_count_above": 10, "floor_count_below": 1, "structure_type": "RC",
                  "with_senior": True},
        )
        assert resp.status_code == 200
        sc = resp.json()["senior_consultation"]
        assert sc is not None
        assert sc["verdict"] != "unavailable"
        assert sc["consultations"][0]["agent_key"] == "senior_quantity_surveyor"


class TestMonteCarlo:

    def test_monte_carlo(self):
        calc_resp = client.post(f"/api/v1/cost/{PROJECT_ID}/calculate", json={
            "items": COST_ITEMS,
        })
        base = calc_resp.json()

        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/monte-carlo", json={
            "base_result": base,
            "iterations": 1000,
            "seed": 42,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["p10"] <= data["p50"] <= data["p90"]


class TestBilling:

    def test_create_billing(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/billing/create", json={
            "billing_no": 1,
            "period_from": "2026-01-01",
            "period_to": "2026-03-31",
            "planned_value": 1000000000,
            "earned_value": 900000000,
            "actual_cost": 950000000,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["evm_spi"] == 0.9
        assert data["evm_cpi"] > 0

    def test_billing_summary(self):
        resp = client.get(f"/api/v1/cost/{PROJECT_ID}/billing/summary")
        assert resp.status_code == 200


class TestFeasibility:

    def test_cost_to_feasibility(self):
        resp = client.post(f"/api/v1/cost/{PROJECT_ID}/feasibility", json={
            "total_project_cost": 10000000000,
            "total_revenue": 15000000000,
            "project_months": 36,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["profit_rate_pct"] > 0
        assert data["gross_profit"] == 5000000000


class TestExportExcel:
    """T4: 영속 BOQ 실데이터 기반 내보내기 — 가짜 샘플(E01 유령코드 등) 금지."""

    def test_export_excel_no_estimate_returns_404(self):
        """영속 BOQ가 없으면 가짜 샘플 대신 404로 정직 응답한다."""
        with patch(
            "app.services.cost.cost_estimate_repository.list_estimates",
            new_callable=AsyncMock, return_value=[],
        ):
            resp = client.get(f"/api/v1/cost/{PROJECT_ID}/export-excel")
        assert resp.status_code == 404

    def test_export_excel_uses_persisted_boq(self):
        """estimate_id 미지정 시 최신 영속 BOQ의 실 항목으로 Excel을 생성한다(E01 유령코드 없음)."""
        fake_estimate = {
            "estimate_id": "est-1", "project_id": PROJECT_ID,
            "building_type": "apartment", "structure_type": "RC", "total_gfa_sqm": 1000.0,
            "summary": {"direct": 1_000_000, "indirect": 200_000, "total": 1_200_000,
                        "confidence_grade": "B"},
            "badges": {}, "qto_source": "derived", "created_at": "2026-01-01",
            "items": [
                {"code": "A01-03", "name": "콘크리트", "work_type": "철근콘크리트공사",
                 "quantity": 500.0, "unit": "m3", "unit_price": 247000.0, "amount": 123_500_000.0,
                 "price_source": "fallback", "price_basis_year": 2026, "qto_source": "derived",
                 "market_unit_price": None, "actual_unit_price": None},
            ],
        }
        with (
            patch(
                "app.services.cost.cost_estimate_repository.list_estimates",
                new_callable=AsyncMock, return_value=[{"estimate_id": "est-1"}],
            ),
            patch(
                "app.services.cost.cost_estimate_repository.get_estimate",
                new_callable=AsyncMock, return_value=fake_estimate,
            ),
        ):
            resp = client.get(f"/api/v1/cost/{PROJECT_ID}/export-excel")
        assert resp.status_code == 200
        ct = resp.headers["content-type"]
        assert "csv" in ct or "spreadsheet" in ct


class TestWorkBreakdownAdditive:
    """P2 T2/T4: 공종분류 SSOT(wb_code/wb_name) + 단가 3분해 additive 노출 — 기존 키 불변."""

    def test_estimate_overview_items_have_wb_code(self):
        resp = client.post(
            "/api/v1/cost/estimate-overview",
            json={"building_type": "apartment", "total_gfa_sqm": 3000.0,
                  "floor_count_above": 10, "floor_count_below": 1, "structure_type": "RC"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 8  # 표준 8공종(01~08) 불변
        by_name = {it["name"]: it for it in items}
        assert by_name["레미콘 타설"]["wb_code"] == "WB04"
        assert by_name["레미콘 타설"]["wb_name"] == "골조공사(RC·철골)"
        # 기존 키(가짜값 없이) 그대로 유지 — additive 계약 확인.
        assert "unit_cost_won" in by_name["레미콘 타설"]

    def test_boq_items_have_wb_code(self):
        resp = client.post(
            f"/api/v1/cost/{PROJECT_ID}/boq",
            json={"total_gfa_sqm": 3000.0, "persist": False, "use_llm": False},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        by_code = {it["code"]: it for it in items}
        assert by_code["01-콘크리트"]["wb_code"] == "WB04"
        assert by_code["07-기계설비"]["wb_code"] == "WB10"
        assert by_code["08-전기설비"]["wb_code"] == "WB11"

    def test_unit_prices_items_have_mat_labor_exp_decomposition(self):
        resp = client.get("/api/v1/cost/unit-prices")
        assert resp.status_code == 200
        items = resp.json()["items"]
        by_code = {it["code"]: it for it in items}
        concrete = by_code["concrete"]
        # repository.get_prices()가 이미 반환하던 값 — 라우트에서 노출만(additive).
        assert concrete["mat_unit"] == 85_000
        assert concrete["labor_unit"] == 35_000
        assert concrete["exp_unit"] == 12_000
        assert concrete["mat_unit"] + concrete["labor_unit"] + concrete["exp_unit"] == concrete["standard"]
