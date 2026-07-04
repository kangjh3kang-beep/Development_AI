"""v2 세금 라우터 테스트 — 경량 TestClient (전체 앱 비의존)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.v2_tax import router

# 경량 테스트 앱: v2_tax 라우터만 등록
_app = FastAPI()
_app.include_router(router)
client = TestClient(_app)


class TestCalculateAll:
    def test_basic(self):
        resp = client.post("/api/v2/tax/calculate-all", json={
            "purchase_won": 50000000000,
            "land_category": "land",
            "sido_name": "서울",
            "sigungu_name": "강남구",
            "total_households": 1000,
            "total_sale_amount_won": 500000000000,
            "total_gfa_sqm": 100000,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["grand_total_won"] > 0
        assert data["total_items_count"] >= 20


class TestApplicable:
    def test_m04(self):
        resp = client.get("/api/v2/tax/applicable/M04")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 20

    def test_m02_has_d05(self):
        resp = client.get("/api/v2/tax/applicable/M02")
        data = resp.json()
        assert "D05" in data["applicable_codes"]


class TestMatrix:
    def test_get_matrix(self):
        resp = client.get("/api/v2/tax/matrix")
        assert resp.status_code == 200
        assert resp.json()["count"] > 0


class TestRegionRates:
    def test_seoul(self):
        resp = client.get("/api/v2/tax/regions/서울")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sido_name"] == "서울"

    def test_gyeonggi(self):
        resp = client.get("/api/v2/tax/regions/경기")
        data = resp.json()
        assert len(data["sigungu_overrides"]) > 0


class TestRates:
    def test_forest(self):
        resp = client.get("/api/v2/tax/rates?land_category=forest")
        assert resp.status_code == 200
        assert resp.json()["base_rate"] == 0.022

    def test_default_land(self):
        resp = client.get("/api/v2/tax/rates")
        assert resp.status_code == 200
        assert "total_rate" in resp.json()


class TestMetroTransport:
    def test_basic(self):
        resp = client.get(
            "/api/v2/tax/metro-transport?sido_name=서울&sigungu_name=강남구"
        )
        assert resp.status_code == 200
        assert resp.json()["source"] in ("base", "override")


class TestCompare:
    def test_land_vs_farmland(self):
        resp = client.get(
            "/api/v2/tax/compare?land_category_a=land&land_category_b=farmland"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["difference_won"] >= 0


class TestDevelopmentTypes:
    def test_list(self):
        resp = client.get("/api/v2/tax/development-types")
        assert resp.status_code == 200
        assert len(resp.json()["types"]) == 15
