"""v61 설계도면 라우터 테스트 — 경량 TestClient (전체 앱 비의존)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers.design_v61 import router

_app = FastAPI()
_app.include_router(router)
client = TestClient(_app)

PROJECT_ID = "test-project-001"


class TestGenerateFullSet:

    def test_generate_full_set(self):
        resp = client.post(f"/api/v1/design/{PROJECT_ID}/generate-full-set", json={
            "site_width_m": 60, "site_depth_m": 40,
            "building_width_m": 40, "building_depth_m": 20,
            "floor_count": 5, "floor_height_m": 3.0,
            "basement_floors": 1, "unit_width_m": 8.0,
            "setback_m": 3.0, "parking_count": 50,
            "project_name": "테스트빌딩",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == PROJECT_ID
        assert data["drawing_count"] >= 7

    def test_generate_full_set_defaults(self):
        resp = client.post(f"/api/v1/design/{PROJECT_ID}/generate-full-set", json={})
        assert resp.status_code == 200


class TestGetDrawingSVG:

    def test_get_existing_drawing(self):
        resp = client.get(f"/api/v1/design/{PROJECT_ID}/drawings/B-01/svg")
        assert resp.status_code == 200
        assert "svg" in resp.headers.get("content-type", "")

    def test_get_nonexistent_drawing(self):
        resp = client.get(f"/api/v1/design/{PROJECT_ID}/drawings/Z-99/svg")
        assert resp.status_code == 404


class TestSaveDrawing:

    def test_save_drawing(self):
        resp = client.post(f"/api/v1/design/{PROJECT_ID}/drawings/save", json={
            "drawing_code": "B-01",
            "drawing_type": "배치도",
            "svg_content": "<svg></svg>",
            "layers": [{"name": "A-WALL", "visible": True}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "saved"
        assert data["layer_count"] == 1


class TestSelectAlternative:

    def test_select_alternative(self):
        resp = client.post(f"/api/v1/design/{PROJECT_ID}/select-alternative", json={
            "alternatives": [
                {"name": "A", "profit_score": 80, "legal_score": 90,
                 "design_score": 70, "esg_score": 60},
                {"name": "B", "profit_score": 70, "legal_score": 85,
                 "design_score": 80, "esg_score": 75},
            ],
            "iterations": 1000,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["ranked"]) == 2
        assert data["winner"] is not None


class TestPermitDocs:

    def test_get_permit_docs(self):
        resp = client.get(f"/api/v1/design/{PROJECT_ID}/permit-docs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 37
