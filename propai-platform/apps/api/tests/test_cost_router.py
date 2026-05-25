"""v61 공사비 라우터 테스트 — 경량 TestClient (전체 앱 비의존)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers.cost import router

_app = FastAPI()
_app.include_router(router)
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

    def test_export_excel(self):
        resp = client.get(f"/api/v1/cost/{PROJECT_ID}/export-excel")
        assert resp.status_code == 200
