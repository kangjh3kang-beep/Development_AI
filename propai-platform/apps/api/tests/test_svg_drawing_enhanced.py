"""SVGDrawingService 고도화 메서드 테스트."""

import pytest

svgwrite = pytest.importorskip("svgwrite", reason="svgwrite 미설치 — SVG 테스트 스킵")

from app.services.drawing.svg_drawing_service import SVGDrawingService


@pytest.fixture()
def svc():
    return SVGDrawingService()


class TestExistingSitePlan:
    def test_returns_svg_string(self, svc: SVGDrawingService):
        svg = svc.generate_site_plan(40, 30, 25, 12)
        assert isinstance(svg, str)
        assert "<svg" in svg.lower() or "svg" in svg.lower()


class TestExistingFloorPlan:
    def test_returns_svg_string(self, svc: SVGDrawingService):
        svg = svc.generate_floor_plan(500, "84A", 2, 50)
        assert isinstance(svg, str)


class TestDetailedFloorPlan:
    def test_returns_svg(self, svc: SVGDrawingService):
        svg = svc.generate_detailed_floor_plan(30, 15, floor_label="기준층")
        assert isinstance(svg, str)
        assert len(svg) > 500

    def test_contains_wall_elements(self, svc: SVGDrawingService):
        svg = svc.generate_detailed_floor_plan(30, 15)
        assert "rect" in svg or "line" in svg

    def test_different_cores(self, svc: SVGDrawingService):
        svg1 = svc.generate_detailed_floor_plan(30, 15, core_count=1)
        svg2 = svc.generate_detailed_floor_plan(30, 15, core_count=3)
        assert isinstance(svg1, str)
        assert isinstance(svg2, str)


class TestSectionDrawing:
    def test_returns_svg(self, svc: SVGDrawingService):
        svg = svc.generate_section_drawing(20, 5, 3.0, basement_floors=1)
        assert isinstance(svg, str)
        assert len(svg) > 500

    def test_no_basement(self, svc: SVGDrawingService):
        svg = svc.generate_section_drawing(20, 3, 3.0, basement_floors=0)
        assert isinstance(svg, str)


class TestElevationDrawing:
    def test_front_view(self, svc: SVGDrawingService):
        svg = svc.generate_elevation_drawing(30, 7, view="front")
        assert isinstance(svg, str)
        assert len(svg) > 500

    def test_side_view(self, svc: SVGDrawingService):
        svg = svc.generate_elevation_drawing(15, 7, view="side")
        assert isinstance(svg, str)


class TestParkingLayout:
    def test_returns_svg(self, svc: SVGDrawingService):
        svg = svc.generate_parking_layout(50)
        assert isinstance(svg, str)
        assert len(svg) > 200

    def test_mechanical_parking(self, svc: SVGDrawingService):
        svg = svc.generate_parking_layout(30, parking_type="기계식")
        assert isinstance(svg, str)

    def test_small_count(self, svc: SVGDrawingService):
        svg = svc.generate_parking_layout(3)
        assert isinstance(svg, str)
