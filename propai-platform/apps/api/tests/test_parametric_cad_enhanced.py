"""ParametricCADService 고도화 메서드 테스트."""

import pytest

ezdxf = pytest.importorskip("ezdxf", reason="ezdxf 미설치 — DXF 테스트 스킵")

from app.services.cad.parametric_cad_service import ParametricCADService


@pytest.fixture()
def svc():
    return ParametricCADService()


class TestBasicFloorPlan:
    """기존 기본 평면도."""

    def test_returns_bytes(self, svc: ParametricCADService):
        dxf = svc.create_floor_plan_dxf(30, 15, floor_count=5)
        assert isinstance(dxf, bytes)
        assert len(dxf) > 100


class TestDetailedFloorPlan:
    """상세 평면도 DXF."""

    def test_returns_bytes(self, svc: ParametricCADService):
        dxf = svc.create_detailed_floor_plan_dxf(
            building_width_m=30, building_depth_m=15,
            floor_count=7, core_count=2,
        )
        assert isinstance(dxf, bytes)
        assert len(dxf) > 500

    def test_contains_dxf_header(self, svc: ParametricCADService):
        dxf = svc.create_detailed_floor_plan_dxf(20, 12, floor_count=3)
        text = dxf.decode("utf-8", errors="ignore")
        assert "SECTION" in text
        assert "ENTITIES" in text

    def test_different_core_counts(self, svc: ParametricCADService):
        dxf1 = svc.create_detailed_floor_plan_dxf(30, 15, core_count=1)
        dxf2 = svc.create_detailed_floor_plan_dxf(30, 15, core_count=3)
        # 더 많은 코어 → 약간 더 큰 DXF
        assert isinstance(dxf1, bytes)
        assert isinstance(dxf2, bytes)


class TestSectionDrawing:
    """단면도 DXF."""

    def test_returns_bytes(self, svc: ParametricCADService):
        dxf = svc.create_section_drawing_dxf(
            building_width_m=20, building_depth_m=12,
            floor_count=5, floor_height_m=3.0,
            basement_floors=1,
        )
        assert isinstance(dxf, bytes)
        assert len(dxf) > 500

    def test_no_basement(self, svc: ParametricCADService):
        dxf = svc.create_section_drawing_dxf(
            building_width_m=20, building_depth_m=12,
            floor_count=3, basement_floors=0,
        )
        assert isinstance(dxf, bytes)

    def test_many_floors(self, svc: ParametricCADService):
        dxf = svc.create_section_drawing_dxf(
            building_width_m=20, building_depth_m=12,
            floor_count=20, basement_floors=3,
        )
        assert isinstance(dxf, bytes)
        assert len(dxf) > 1000


class TestElevationDrawing:
    """입면도 DXF."""

    def test_front_view(self, svc: ParametricCADService):
        dxf = svc.create_elevation_drawing_dxf(
            building_width_m=30, building_depth_m=15,
            floor_count=7, view="front",
        )
        assert isinstance(dxf, bytes)
        assert len(dxf) > 500

    def test_side_view(self, svc: ParametricCADService):
        dxf = svc.create_elevation_drawing_dxf(
            building_width_m=30, building_depth_m=15,
            floor_count=7, view="side",
        )
        assert isinstance(dxf, bytes)


class TestSitePlan:
    """배치도 DXF."""

    def test_returns_bytes(self, svc: ParametricCADService):
        dxf = svc.create_site_plan_dxf(
            site_width_m=40, site_depth_m=30,
            building_width_m=25, building_depth_m=12,
        )
        assert isinstance(dxf, bytes)
        assert len(dxf) > 500

    def test_with_parking(self, svc: ParametricCADService):
        dxf = svc.create_site_plan_dxf(
            site_width_m=50, site_depth_m=40,
            building_width_m=30, building_depth_m=15,
            parking_count=50,
        )
        assert isinstance(dxf, bytes)

    def test_with_custom_setback(self, svc: ParametricCADService):
        dxf = svc.create_site_plan_dxf(
            site_width_m=40, site_depth_m=30,
            building_width_m=20, building_depth_m=10,
            setback_m={"north": 6.0, "south": 3.0, "east": 2.0, "west": 2.0},
        )
        assert isinstance(dxf, bytes)


class TestAutoCorrect:
    """기존 법규 보정."""

    def test_returns_corrections(self, svc: ParametricCADService):
        dxf = svc.create_floor_plan_dxf(30, 15)
        result_dxf, corrections = svc.auto_correct_legal_violations(
            dxf, max_far=200, max_bcr=60, site_area_sqm=500,
        )
        assert isinstance(result_dxf, bytes)
        assert len(corrections) == 3
        assert "건폐율" in corrections[0]
