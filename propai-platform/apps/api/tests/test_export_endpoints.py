"""DXF/Excel 내보내기 엔드포인트 통합 테스트."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.drawing import router as drawing_router
from app.routers.cost import router as cost_router

_app = FastAPI()
_app.include_router(drawing_router)
_app.include_router(cost_router)
client = TestClient(_app)


class TestDxfExportTypes:
    """DXF 내보내기 도면 유형별 테스트."""

    def _export(self, drawing_type: str):
        return client.post("/api/v1/drawing/export-dxf", json={
            "building_width_m": 30,
            "building_depth_m": 15,
            "floor_count": 5,
            "floor_height_m": 3.0,
            "unit_width_m": 8.0,
            "corridor_width_m": 1.8,
            "basement_floors": 1,
            "site_width_m": 60,
            "site_depth_m": 40,
            "setback_m": 3.0,
            "parking_count": 50,
            "drawing_type": drawing_type,
        })

    def test_floor_plan(self):
        r = self._export("floor_plan")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/dxf"
        assert "floor_plan.dxf" in r.headers["content-disposition"]
        assert len(r.content) > 0

    def test_detailed(self):
        r = self._export("detailed")
        assert r.status_code == 200
        assert "detailed.dxf" in r.headers["content-disposition"]

    def test_section(self):
        r = self._export("section")
        assert r.status_code == 200
        assert "section.dxf" in r.headers["content-disposition"]

    def test_elevation_front(self):
        r = self._export("elevation_front")
        assert r.status_code == 200
        assert "elevation_front.dxf" in r.headers["content-disposition"]

    def test_elevation_side(self):
        r = self._export("elevation_side")
        assert r.status_code == 200
        assert "elevation_side.dxf" in r.headers["content-disposition"]

    def test_site_plan(self):
        r = self._export("site_plan")
        assert r.status_code == 200
        assert "site_plan.dxf" in r.headers["content-disposition"]

    def test_default_drawing_type(self):
        """drawing_type 미지정 시 기본값 floor_plan."""
        r = client.post("/api/v1/drawing/export-dxf", json={
            "building_width_m": 20,
            "building_depth_m": 12,
        })
        assert r.status_code == 200


class TestCostExcelExport:
    """원가계산서 Excel 내보내기 테스트."""

    def test_export_excel_returns_file(self):
        r = client.get("/api/v1/cost/test-project/export-excel")
        assert r.status_code == 200
        ct = r.headers["content-type"]
        assert "csv" in ct or "spreadsheet" in ct
        assert "content-disposition" in r.headers
        assert len(r.content) > 0

    def test_export_excel_filename(self):
        r = client.get("/api/v1/cost/proj-123/export-excel")
        assert "proj-123" in r.headers["content-disposition"]
