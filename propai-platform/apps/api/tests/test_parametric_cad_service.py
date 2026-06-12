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


# ════════════════════════════════════════════════════════
# CAD2.0 shapes 모드 (U1) — 레이어맵·kind별 엔티티·outline 한정 치수
# ════════════════════════════════════════════════════════

# CAD2.0 셰이프 페이로드(px, 캔버스 y축 하향, scale 10px/m)
SHAPES_FIXTURE = [
    {"kind": "polygon", "layer": "outline",
     "points": [{"x": 0, "y": 0}, {"x": 200, "y": 0},
                {"x": 200, "y": 120}, {"x": 0, "y": 120}]},
    {"kind": "rect", "layer": "wall", "x": 20, "y": 20, "w": 60, "h": 40},
    {"kind": "line", "layer": "wall", "x1": 100, "y1": 20, "x2": 180, "y2": 20},
    {"kind": "circle", "layer": "wall", "cx": 150, "cy": 90, "r": 15},
    {"kind": "label", "layer": "note", "x": 10, "y": 110, "text": "거실"},
]


class TestShapesModeDxf:
    """create_dxf_from_edited_points shapes 가산 파라미터 — None이면 기존 경로 불변."""

    def _doc(self, svc, shapes=SHAPES_FIXTURE, scale=10):
        return _readback(
            svc.create_dxf_from_edited_points([], None, scale, shapes=shapes)
        )

    def test_shapes_none_keeps_legacy_path(self, svc: ParametricCADService):
        # shapes=None 명시 호출 == 기존 points 직변환 결과(회귀 0)
        dxf = svc.create_dxf_from_edited_points(
            RECT_POINTS, RECT_SURFACES, scale_px_per_m=10, shapes=None,
        )
        assert _wall_polyline_points(_readback(dxf)) == RECT_EXPECTED_M

    def test_empty_shapes_falls_back_to_legacy_path(self, svc: ParametricCADService):
        # shapes=[](빈 배열)도 기존 points 경로(저장본에 shapes 미기록과 동일 취급)
        dxf = svc.create_dxf_from_edited_points(
            RECT_POINTS, RECT_SURFACES, scale_px_per_m=10, shapes=[],
        )
        assert _wall_polyline_points(_readback(dxf)) == RECT_EXPECTED_M

    def test_outline_polygon_on_wall_layer_closed(self, svc: ParametricCADService):
        doc = self._doc(svc)
        walls = doc.modelspace().query('LWPOLYLINE[layer=="WALL"]')
        assert len(walls) == 1
        assert walls[0].closed
        pts = [(round(x, 6), round(y, 6)) for x, y in walls[0].get_points("xy")]
        # px→m(scale 10)+Y반전: (0,0)→(0,12), (200,0)→(20,12), (200,120)→(20,0), (0,120)→(0,0)
        assert pts == [(0.0, 12.0), (20.0, 12.0), (20.0, 0.0), (0.0, 0.0)]

    def test_wall_rect_on_wall_interior_layer(self, svc: ParametricCADService):
        doc = self._doc(svc)
        inner = doc.modelspace().query('LWPOLYLINE[layer=="WALL_INTERIOR"]')
        assert len(inner) == 1
        assert inner[0].closed
        pts = [(round(x, 6), round(y, 6)) for x, y in inner[0].get_points("xy")]
        assert pts == [(2.0, 10.0), (8.0, 10.0), (8.0, 6.0), (2.0, 6.0)]

    def test_line_kind_to_line_entity(self, svc: ParametricCADService):
        doc = self._doc(svc)
        lines = doc.modelspace().query('LINE[layer=="WALL_INTERIOR"]')
        assert len(lines) == 1
        start, end = lines[0].dxf.start, lines[0].dxf.end
        assert (round(start.x, 6), round(start.y, 6)) == (10.0, 10.0)
        assert (round(end.x, 6), round(end.y, 6)) == (18.0, 10.0)

    def test_circle_kind_to_circle_entity(self, svc: ParametricCADService):
        doc = self._doc(svc)
        circles = doc.modelspace().query("CIRCLE")
        assert len(circles) == 1
        c = circles[0]
        assert (round(c.dxf.center.x, 6), round(c.dxf.center.y, 6)) == (15.0, 3.0)
        assert round(c.dxf.radius, 6) == 1.5  # 15px ÷ 10px/m

    def test_label_kind_to_text_entity(self, svc: ParametricCADService):
        doc = self._doc(svc)
        texts = doc.modelspace().query('TEXT[layer=="TEXT"]')
        assert len(texts) == 1
        assert texts[0].dxf.text == "거실"
        ins = texts[0].dxf.insert
        assert (round(ins.x, 6), round(ins.y, 6)) == (1.0, 1.0)

    def test_dimensions_only_on_outline_edges(self, svc: ParametricCADService):
        # outline 폴리곤(변 4개)에만 정식 치수 — wall rect 변에는 없음
        doc = self._doc(svc)
        dims = doc.modelspace().query("DIMENSION")
        assert len(dims) == 4
        assert all(d.dxf.layer == "DIM" for d in dims)
        measurements = sorted(round(d.get_measurement(), 6) for d in dims)
        assert measurements == [12.0, 12.0, 20.0, 20.0]

    def test_unknown_layer_defaults(self, svc: ParametricCADService):
        # 레이어 미상: label→TEXT, 그 외→WALL_INTERIOR(+outline 아님 → 치수 없음)
        shapes = [
            {"kind": "polygon",
             "points": [{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 50}]},
            {"kind": "label", "x": 10, "y": 10, "text": "A"},
        ]
        doc = self._doc(svc, shapes=shapes)
        msp = doc.modelspace()
        assert len(msp.query('LWPOLYLINE[layer=="WALL_INTERIOR"]')) == 1
        assert len(msp.query('TEXT[layer=="TEXT"]')) == 1
        assert len(msp.query("DIMENSION")) == 0

    def test_polyline_kind_open(self, svc: ParametricCADService):
        shapes = [{"kind": "polyline", "layer": "wall", "closed": False,
                   "points": [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 50, "y": 30}]}]
        doc = self._doc(svc, shapes=shapes)
        polys = doc.modelspace().query("LWPOLYLINE")
        assert len(polys) == 1
        assert not polys[0].closed

    def test_insunits_meters_recorded(self, svc: ParametricCADService):
        # 재가져오기(import) 시 단위 확정용 $INSUNITS=6(m)
        doc = self._doc(svc)
        assert int(doc.header.get("$INSUNITS", 0)) == 6

    def test_invalid_shapes_skipped_valid_kept(self, svc: ParametricCADService):
        shapes = [
            {"kind": "hexagram", "x": 0, "y": 0},                 # 미지원 kind
            {"kind": "circle", "cx": 10, "cy": 10, "r": 0},        # 반경 0
            {"kind": "rect", "x": 0, "y": 0, "w": 50, "h": 30},    # 유효
        ]
        doc = self._doc(svc, shapes=shapes)
        assert len(doc.modelspace().query("LWPOLYLINE")) == 1

    def test_no_valid_shapes_raises_value_error(self, svc: ParametricCADService):
        with pytest.raises(ValueError):
            svc.create_dxf_from_edited_points(
                [], None, scale_px_per_m=10,
                shapes=[{"kind": "hexagram", "x": 0, "y": 0}],
            )

    def test_invalid_scale_raises_value_error(self, svc: ParametricCADService):
        with pytest.raises(ValueError):
            svc.create_dxf_from_edited_points(
                [], None, scale_px_per_m=0, shapes=SHAPES_FIXTURE,
            )

    def test_no_ezdxf_returns_placeholder(self, svc: ParametricCADService, monkeypatch):
        monkeypatch.setattr(pcs_module, "ezdxf", None)
        out = svc.create_dxf_from_edited_points(
            [], None, scale_px_per_m=10, shapes=SHAPES_FIXTURE,
        )
        assert out == b"DXF_PLACEHOLDER_NO_EZDXF"
