"""v2 수지분석 라우터 테스트 — 경량 TestClient (전체 앱 비의존)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers.v2_feasibility import router

# 경량 테스트 앱: v2_feasibility 라우터만 등록
_app = FastAPI()
_app.include_router(router)
client = TestClient(_app)


class TestCalculateEndpoint:
    def test_basic_calculate(self):
        resp = client.post("/api/v2/feasibility/calculate", json={
            "development_type": "M06",
            "total_land_area_sqm": 50000,
            "total_gfa_sqm": 100000,
            "total_households": 1000,
            "avg_sale_price_per_pyeong": 15000000,
            "avg_area_pyeong": 30,
            "sido_name": "경기",
            "sigungu_name": "수원시",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["development_type"] == "M06"
        assert data["grade"] in "ABCDEF"
        assert data["total_revenue_won"] > 0

    def test_invalid_type(self):
        resp = client.post("/api/v2/feasibility/calculate", json={
            "development_type": "M99",
            "total_land_area_sqm": 50000,
            "total_gfa_sqm": 100000,
        })
        assert resp.status_code == 422

    def test_zero_area(self):
        resp = client.post("/api/v2/feasibility/calculate", json={
            "development_type": "M06",
            "total_land_area_sqm": 0,
            "total_gfa_sqm": 100000,
        })
        assert resp.status_code == 422


class TestCompareEndpoint:
    def test_compare_two(self):
        resp = client.post("/api/v2/feasibility/compare", json={
            "projects": [
                {
                    "development_type": "M01",
                    "total_land_area_sqm": 50000,
                    "total_gfa_sqm": 100000,
                    "total_households": 1000,
                    "avg_sale_price_per_pyeong": 15000000,
                    "avg_area_pyeong": 30,
                },
                {
                    "development_type": "M06",
                    "total_land_area_sqm": 50000,
                    "total_gfa_sqm": 100000,
                    "total_households": 1000,
                    "avg_sale_price_per_pyeong": 15000000,
                    "avg_area_pyeong": 30,
                },
            ]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 2
        assert "comparison" in data


class TestModulesEndpoint:
    def test_list_modules(self):
        resp = client.get("/api/v2/feasibility/modules")
        assert resp.status_code == 200
        assert len(resp.json()["modules"]) == 15


class TestMonteCarloEndpoint:
    def test_basic(self):
        resp = client.post("/api/v2/feasibility/monte-carlo", json={
            "variables": [
                {"name": "revenue", "mean": 1000, "std": 100},
                {"name": "cost", "mean": 800, "std": 50},
            ],
            "n_simulations": 1000,
            "seed": 42,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["n_simulations"] == 1000
        assert data["probability_positive"] > 0


class TestVCSEndpoints:
    def test_commit_and_log(self):
        pid = "test-project-001"
        resp = client.post(f"/api/v2/feasibility/repos/{pid}/commit", json={
            "message": "초기 커밋",
            "snapshot": {"revenue": 100, "cost": 80},
        })
        assert resp.status_code == 200
        sha = resp.json()["sha"]

        resp = client.get(f"/api/v2/feasibility/repos/{pid}/log")
        assert resp.status_code == 200
        assert len(resp.json()["commits"]) >= 1

    def test_rollback(self):
        pid = "test-rollback-001"
        r1 = client.post(f"/api/v2/feasibility/repos/{pid}/commit", json={
            "message": "v1", "snapshot": {"v": 1},
        })
        sha1 = r1.json()["sha"]
        client.post(f"/api/v2/feasibility/repos/{pid}/commit", json={
            "message": "v2", "snapshot": {"v": 2},
        })

        resp = client.post(f"/api/v2/feasibility/repos/{pid}/rollback", json={
            "target_sha": sha1,
        })
        assert resp.status_code == 200


class TestRecommendationsEndpoint:
    def test_basic(self):
        resp = client.post("/api/v2/feasibility/recommendations", json={
            "development_type": "M06",
            "total_land_area_sqm": 50000,
            "total_gfa_sqm": 100000,
            "total_households": 1000,
            "avg_sale_price_per_pyeong": 15000000,
            "avg_area_pyeong": 30,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "recommendations" in data
