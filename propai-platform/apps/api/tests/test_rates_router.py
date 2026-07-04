"""v61 법정요율 라우터 테스트 — 경량 TestClient (전체 앱 비의존)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.rates import router

_app = FastAPI()
_app.include_router(router)
client = TestClient(_app)


class TestCurrentRates:

    def test_get_current_rates(self):
        resp = client.get("/api/v1/rates/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data["year"] == 2026
        assert len(data["rates"]) == 12
        assert "pension_note" in data
        assert "pension_schedule" in data

    def test_rate_values(self):
        resp = client.get("/api/v1/rates/current")
        rates = resp.json()["rates"]
        assert rates["vat"] == 0.10
        assert rates["industrial_accident"] == 0.035


class TestRateHistory:

    def test_get_all_history(self):
        resp = client.get("/api/v1/rates/history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 12

    def test_get_filtered_history(self):
        resp = client.get("/api/v1/rates/history?rate_code=vat")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["rate_category"] == "vat"


class TestRefreshRates:

    def test_refresh(self):
        resp = client.post("/api/v1/rates/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "no_changes"
