"""ParametricCADService — 편집좌표 DXF 직변환 + 정식 DIMENSION 계약 테스트 (WP-04).

산출 DXF를 ezdxf로 재파싱해 엔티티·좌표·치수 측정값을 고정 수치로 검증한다.
"""

import io

import pytest

ezdxf = pytest.importorskip("ezdxf", reason="ezdxf 미설치 — DXF 테스트 스킵")

from app.services.cad import parametric_cad_service as pcs_module
from app.services.cad.parametric_cad_service import ParametricCADService


@pytest.fixture()
def svc():
    return ParametricCADService()


def _readback(dxf_bytes: bytes):
    """산출 DXF 바이트를 ezdxf 문서로 재파싱한다."""
    return ezdxf.read(io.StringIO(dxf_bytes.decode("utf-8")))


def _wall_polyline_points(doc):
    polys = doc.modelspace().query('LWPOLYLINE[layer=="WALL"]')
    assert len(polys) == 1
    return [(round(x, 6), round(y, 6)) for x, y in polys[0].get_points("xy")]


# CADEditor 저장 계약과 동일한 페이로드 형태 —
# 캔버스 px 좌표(y축 하향): 100×50px 직사각형, scale 10px/m → 10m×5m
RECT_POINTS = [
    {"id": "p1", "x": 0, "y": 0},
    {"id": "p2", "x": 100, "y": 0},
    {"id": "p3", "x": 100, "y": 50},
    {"id": "p4", "x": 0, "y": 50},
]
RECT_SURFACES = [{"id": "s1", "point_ids": ["p1", "p2", "p3", "p4"]}]

# y축 반전 + bbox 좌하단 원점 정규화 후 기대 좌표(m):
# (0,0)px→(0,5), (100,0)px→(10,5), (100,50)px→(10,0), (0,50)px→(0,0)
RECT_EXPECTED_M = [(0.0, 5.0), (10.0, 5.0), (10.0, 0.0), (0.0, 0.0)]


class TestCreateDxfFromEditedPoints:
    """신규 create_dxf_from_edited_points — 링 복원·px→m·Y반전·정식 치수."""

    def test_wall_lwpolyline_px_to_m_and_y_flip(self, svc: ParametricCADService):
        dxf = svc.create_dxf_from_edited_points(
            RECT_POINTS, RECT_SURFACES, scale_px_per_m=10,
        )
        doc = _readback(dxf)
        polys = doc.modelspace().query('LWPOLYLINE[layer=="WALL"]')
        assert len(polys) == 1
        assert polys[0].closed
        assert _wall_polyline_points(doc) == RECT_EXPECTED_M

    def test_each_edge_has_formal_dimension(self, svc: ParametricCADService):
        dxf = svc.create_dxf_from_edited_points(
            RECT_POINTS, RECT_SURFACES, scale_px_per_m=10,
        )
        doc = _readback(dxf)
        dims = doc.modelspace().query("DIMENSION")
        assert len(dims) == 4  # 변 4개 → 치수 4개
        assert all(d.dxf.layer == "DIM" for d in dims)
        measurements = sorted(round(d.get_measurement(), 6) for d in dims)
        assert measurements == [5.0, 5.0, 10.0, 10.0]

    def test_ring_restored_from_surface_point_ids(self, svc: ParametricCADService):
        # points 배열 순서를 뒤섞어도 surfaces[0].point_ids 순서로 링 복원
        shuffled = [RECT_POINTS[2], RECT_POINTS[0], RECT_POINTS[3], RECT_POINTS[1]]
        dxf = svc.create_dxf_from_edited_points(
            shuffled, RECT_SURFACES, scale_px_per_m=10,
        )
        assert _wall_polyline_points(_readback(dxf)) == RECT_EXPECTED_M

    def test_fallback_to_points_order_without_surfaces(self, svc: ParametricCADService):
        dxf = svc.create_dxf_from_edited_points(
            RECT_POINTS, None, scale_px_per_m=10,
        )
        assert _wall_polyline_points(_readback(dxf)) == RECT_EXPECTED_M

    def test_custom_scale_px_per_m(self, svc: ParametricCADService):
        # scale 20px/m → 100×50px = 5m×2.5m
        dxf = svc.create_dxf_from_edited_points(
            RECT_POINTS, RECT_SURFACES, scale_px_per_m=20,
        )
        doc = _readback(dxf)
        measurements = sorted(
            round(d.get_measurement(), 6)
            for d in doc.modelspace().query("DIMENSION")
        )
        assert measurements == [2.5, 2.5, 5.0, 5.0]

    def test_default_scale_is_10(self, svc: ParametricCADService):
        dxf = svc.create_dxf_from_edited_points(RECT_POINTS, RECT_SURFACES)
        assert _wall_polyline_points(_readback(dxf)) == RECT_EXPECTED_M

    def test_closed_duplicate_last_point_id_normalized(self, svc: ParametricCADService):
        surfaces = [{"id": "s1", "point_ids": ["p1", "p2", "p3", "p4", "p1"]}]
        dxf = svc.create_dxf_from_edited_points(RECT_POINTS, surfaces)
        assert _wall_polyline_points(_readback(dxf)) == RECT_EXPECTED_M

    def test_unknown_point_ids_ignored(self, svc: ParametricCADService):
        surfaces = [{"id": "s1", "point_ids": ["p1", "p2", "ghost", "p3", "p4"]}]
        dxf = svc.create_dxf_from_edited_points(RECT_POINTS, surfaces)
        assert _wall_polyline_points(_readback(dxf)) == RECT_EXPECTED_M

    def test_too_few_points_raises_value_error(self, svc: ParametricCADService):
        with pytest.raises(ValueError):
            svc.create_dxf_from_edited_points(RECT_POINTS[:2], None)

    def test_empty_points_raises_value_error(self, svc: ParametricCADService):
        with pytest.raises(ValueError):
            svc.create_dxf_from_edited_points([], RECT_SURFACES)

    def test_invalid_scale_raises_value_error(self, svc: ParametricCADService):
        with pytest.raises(ValueError):
            svc.create_dxf_from_edited_points(
                RECT_POINTS, RECT_SURFACES, scale_px_per_m=0,
            )

    def test_no_ezdxf_returns_placeholder(self, svc: ParametricCADService, monkeypatch):
        # 기존 생성 메서드들과 동일한 미설치 폴백 계약
        monkeypatch.setattr(pcs_module, "ezdxf", None)
        out = svc.create_dxf_from_edited_points(RECT_POINTS, RECT_SURFACES)
        assert out == b"DXF_PLACEHOLDER_NO_EZDXF"


class TestFormalDimensionsInDrawingSet:
    """C4 — _add_dimension_h/_v 내부 교체 후 정식 DIMENSION 포함·하위호환."""

    def test_detailed_floor_plan_has_dimension_entities(self, svc: ParametricCADService):
        dxf = svc.create_detailed_floor_plan_dxf(20, 12, floor_count=3)
        doc = _readback(dxf)
        dims = doc.modelspace().query("DIMENSION")
        assert len(dims) >= 2  # 최소 전체 폭 + 전체 깊이
        assert all(d.dxf.layer == "DIM" for d in dims)

    def test_detailed_floor_plan_overall_measurements(self, svc: ParametricCADService):
        dxf = svc.create_detailed_floor_plan_dxf(20, 12, floor_count=3)
        doc = _readback(dxf)
        measurements = {
            round(d.get_measurement(), 6)
            for d in doc.modelspace().query("DIMENSION")
        }
        assert 20.0 in measurements  # 건물 폭 (수평 치수)
        assert 12.0 in measurements  # 건물 깊이 (수직 치수)

    def test_section_drawing_floor_height_measurement(self, svc: ParametricCADService):
        dxf = svc.create_section_drawing_dxf(
            building_width_m=20, building_depth_m=12,
            floor_count=5, floor_height_m=3.0, basement_floors=1,
        )
        doc = _readback(dxf)
        measurements = {
            round(d.get_measurement(), 6)
            for d in doc.modelspace().query("DIMENSION")
        }
        assert 3.0 in measurements   # 층고 치수
        assert 20.0 in measurements  # 건물 폭

    @pytest.mark.parametrize(
        "name, build",
        [
            ("floor_plan", lambda s: s.create_floor_plan_dxf(30, 15, floor_count=5)),
            ("detailed_floor_plan",
             lambda s: s.create_detailed_floor_plan_dxf(30, 15, floor_count=7)),
            ("section", lambda s: s.create_section_drawing_dxf(20, 12, floor_count=5)),
            ("elevation",
             lambda s: s.create_elevation_drawing_dxf(30, 15, floor_count=7)),
            ("site_plan", lambda s: s.create_site_plan_dxf(40, 30, 25, 12)),
        ],
    )
    def test_five_drawing_types_still_reparse(self, svc: ParametricCADService, name, build):
        # 시그니처 유지 — 5종 도면 전부 기존 호출 무수정으로 유효 DXF 산출
        dxf = build(svc)
        assert isinstance(dxf, bytes)
        doc = _readback(dxf)
        assert len(doc.modelspace()) > 0
