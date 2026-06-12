"""DXF 가져오기 서비스 — 단위 감지·셰이프 추출·왕복 무결성 계약 테스트 (CAD2.0 U1).

핵심 계약: create_dxf_from_edited_points로 내보낸 DXF를 parse_dxf_to_shapes로
재가져오기하면 px 좌표가 보존된다(±0.01 — 정확한 역변환).
"""

import io

import pytest

ezdxf = pytest.importorskip("ezdxf", reason="ezdxf 미설치 — DXF 테스트 스킵")

from app.services.cad.dxf_import_service import parse_dxf_to_shapes
from app.services.cad.parametric_cad_service import ParametricCADService


def _doc_to_bytes(doc) -> bytes:
    """ezdxf 문서를 업로드 가능한 DXF 바이트로 직렬화한다."""
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def _new_doc(insunits=None):
    doc = ezdxf.new("R2010")
    if insunits is not None:
        doc.header["$INSUNITS"] = insunits
    return doc


# ════════════════════════════════════════════════════════
# 단위 감지 — $INSUNITS 매핑 + bbox 휴리스틱
# ════════════════════════════════════════════════════════


class TestUnitDetection:

    def test_insunits_m(self):
        doc = _new_doc(6)
        doc.modelspace().add_line((0, 0), (10, 0))
        out = parse_dxf_to_shapes(_doc_to_bytes(doc))
        assert out["unit"] == {"detected": "m", "source": "insunits"}

    def test_insunits_mm_converts_coordinates(self):
        # mm 도면 12000×8000 → 12m×8m → 10px/m로 120×80px
        doc = _new_doc(4)
        doc.modelspace().add_lwpolyline(
            [(0, 0), (12000, 0), (12000, 8000), (0, 8000)], close=True,
        )
        out = parse_dxf_to_shapes(_doc_to_bytes(doc), scale_px_per_m=10)
        assert out["unit"] == {"detected": "mm", "source": "insunits"}
        pts = out["shapes"][0]["points"]
        assert max(p["x"] for p in pts) == pytest.approx(120.0, abs=0.01)
        assert max(p["y"] for p in pts) == pytest.approx(80.0, abs=0.01)
        assert out["bounds_px"] == {"width": 120.0, "height": 80.0}

    def test_insunits_cm(self):
        doc = _new_doc(5)
        doc.modelspace().add_line((0, 0), (1200, 0))  # 1200cm = 12m → 120px
        out = parse_dxf_to_shapes(_doc_to_bytes(doc), scale_px_per_m=10)
        assert out["unit"] == {"detected": "cm", "source": "insunits"}
        assert out["shapes"][0]["x2"] == pytest.approx(120.0, abs=0.01)

    def test_insunits_inch(self):
        doc = _new_doc(1)
        doc.modelspace().add_line((0, 0), (100, 0))  # 100in = 2.54m → 25.4px
        out = parse_dxf_to_shapes(_doc_to_bytes(doc), scale_px_per_m=10)
        assert out["unit"] == {"detected": "inch", "source": "insunits"}
        assert out["shapes"][0]["x2"] == pytest.approx(25.4, abs=0.01)

    def test_heuristic_large_bbox_is_mm(self):
        # INSUNITS=0(무단위) + bbox 최대변 12000 > 500 → mm 추정
        doc = _new_doc(0)
        doc.modelspace().add_lwpolyline(
            [(0, 0), (12000, 0), (12000, 8000), (0, 8000)], close=True,
        )
        out = parse_dxf_to_shapes(_doc_to_bytes(doc), scale_px_per_m=10)
        assert out["unit"] == {"detected": "mm", "source": "heuristic"}
        pts = out["shapes"][0]["points"]
        assert max(p["x"] for p in pts) == pytest.approx(120.0, abs=0.01)

    def test_heuristic_small_bbox_is_m(self):
        # INSUNITS=0(무단위) + bbox 최대변 12 ≤ 500 → m 추정
        doc = _new_doc(0)
        doc.modelspace().add_lwpolyline(
            [(0, 0), (12, 0), (12, 8), (0, 8)], close=True,
        )
        out = parse_dxf_to_shapes(_doc_to_bytes(doc), scale_px_per_m=10)
        assert out["unit"] == {"detected": "m", "source": "heuristic"}
        pts = out["shapes"][0]["points"]
        assert max(p["x"] for p in pts) == pytest.approx(120.0, abs=0.01)

    def test_unsupported_insunits_falls_back_to_heuristic(self):
        # 2(feet)는 미지원 코드 → 휴리스틱 폴백(작은 bbox → m)
        doc = _new_doc(2)
        doc.modelspace().add_line((0, 0), (10, 0))
        out = parse_dxf_to_shapes(_doc_to_bytes(doc))
        assert out["unit"]["source"] == "heuristic"
        assert out["unit"]["detected"] == "m"


# ════════════════════════════════════════════════════════
# 엔티티 추출 — polyline/line/circle/label + ignored + truncated
# ════════════════════════════════════════════════════════


class TestEntityExtraction:

    def test_line_circle_text_mtext(self):
        doc = _new_doc(6)
        msp = doc.modelspace()
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "WALL_INTERIOR"})
        msp.add_circle((5, 5), radius=2)
        msp.add_text("거실", dxfattribs={"height": 0.3}).set_placement((1, 1))
        msp.add_mtext("주방", dxfattribs={"char_height": 0.3}).set_location((2, 2))
        out = parse_dxf_to_shapes(_doc_to_bytes(doc), scale_px_per_m=10)

        assert [s["kind"] for s in out["shapes"]] == ["line", "circle", "label", "label"]
        # 앵커 bbox: minX=0, maxY=5 → y_px=(5−y)·10
        line, circle, text, mtext = out["shapes"]
        assert (line["x1"], line["y1"]) == (0.0, 50.0)
        assert (line["x2"], line["y2"]) == (100.0, 50.0)
        assert line["layer"] == "wall"  # WALL_INTERIOR 역매핑
        assert (circle["cx"], circle["cy"], circle["r"]) == (50.0, 0.0, 20.0)
        assert circle["layer"] == "wall"  # 미상 레이어("0") 기본값
        assert (text["x"], text["y"], text["text"]) == (10.0, 40.0, "거실")
        assert text["layer"] == "note"  # 미상 레이어 label 기본값
        assert (mtext["x"], mtext["y"], mtext["text"]) == (20.0, 30.0, "주방")

    def test_polyline_entity_closed_flag(self):
        doc = _new_doc(6)
        doc.modelspace().add_polyline2d(
            [(0, 0), (10, 0), (10, 5)], close=True, dxfattribs={"layer": "WALL"},
        )
        out = parse_dxf_to_shapes(_doc_to_bytes(doc), scale_px_per_m=10)
        assert len(out["shapes"]) == 1
        s = out["shapes"][0]
        assert s["kind"] == "polyline"
        assert s["closed"] is True
        assert s["layer"] == "outline"  # WALL 역매핑
        assert s["source_layer"] == "WALL"
        assert len(s["points"]) == 3

    def test_ignored_entities_reported(self):
        doc = _new_doc(6)
        msp = doc.modelspace()
        msp.add_line((0, 0), (10, 0))
        msp.add_arc(center=(0, 0), radius=5, start_angle=0, end_angle=90)
        msp.add_arc(center=(2, 2), radius=3, start_angle=0, end_angle=180)
        out = parse_dxf_to_shapes(_doc_to_bytes(doc))
        assert len(out["shapes"]) == 1
        assert out["ignored"] == [{"type": "ARC", "count": 2}]

    def test_truncated_flag(self):
        doc = _new_doc(6)
        msp = doc.modelspace()
        for i in range(10):
            msp.add_line((0, i), (10, i))
        out = parse_dxf_to_shapes(_doc_to_bytes(doc), max_entities=3)
        assert out["truncated"] is True
        assert len(out["shapes"]) == 3

    def test_not_truncated_under_limit(self):
        doc = _new_doc(6)
        doc.modelspace().add_line((0, 0), (10, 0))
        out = parse_dxf_to_shapes(_doc_to_bytes(doc))
        assert out["truncated"] is False
        assert out["shape_count"] == 1

    def test_main_outline_is_largest_closed_polyline(self):
        doc = _new_doc(6)
        msp = doc.modelspace()
        # 작은 닫힌 링(4㎡) → 큰 닫힌 링(200㎡) → 열린 폴리라인(면적 무시)
        msp.add_lwpolyline([(0, 0), (2, 0), (2, 2), (0, 2)], close=True)
        msp.add_lwpolyline([(0, 0), (20, 0), (20, 10), (0, 10)], close=True)
        msp.add_lwpolyline([(0, 0), (50, 0), (50, 50)], close=False)
        out = parse_dxf_to_shapes(_doc_to_bytes(doc))
        assert out["main_outline_index"] == 1

    def test_main_outline_none_without_closed_polyline(self):
        doc = _new_doc(6)
        doc.modelspace().add_line((0, 0), (10, 0))
        out = parse_dxf_to_shapes(_doc_to_bytes(doc))
        assert out["main_outline_index"] is None


# ════════════════════════════════════════════════════════
# 정직한 실패 — 손상/비DXF/빈 입력/잘못된 인자
# ════════════════════════════════════════════════════════


class TestParseErrors:

    def test_garbage_bytes_raise_value_error(self):
        with pytest.raises(ValueError):
            parse_dxf_to_shapes(b"NOT A DXF FILE AT ALL")

    def test_empty_bytes_raise_value_error(self):
        with pytest.raises(ValueError):
            parse_dxf_to_shapes(b"")

    def test_invalid_scale_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_dxf_to_shapes(b"0\nSECTION", scale_px_per_m=0)

    def test_invalid_max_entities_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_dxf_to_shapes(b"0\nSECTION", max_entities=0)


# ════════════════════════════════════════════════════════
# 왕복 무결성 — 내보낸 DXF 재가져오기 시 px 좌표 보존(±0.01)
# ════════════════════════════════════════════════════════

# CADEditor 저장 계약과 동일한 점/면 페이로드(test_parametric_cad_service와 동일 형태)
RECT_POINTS = [
    {"id": "p1", "x": 0, "y": 0},
    {"id": "p2", "x": 100, "y": 0},
    {"id": "p3", "x": 100, "y": 50},
    {"id": "p4", "x": 0, "y": 50},
]
RECT_SURFACES = [{"id": "s1", "point_ids": ["p1", "p2", "p3", "p4"]}]

# CAD2.0 셰이프 페이로드(bbox 원점 시작 — px 좌표 보존 검증용)
ROUNDTRIP_SHAPES = [
    {"kind": "polygon", "layer": "outline",
     "points": [{"x": 0, "y": 0}, {"x": 200, "y": 0},
                {"x": 200, "y": 120}, {"x": 0, "y": 120}]},
    {"kind": "rect", "layer": "wall", "x": 20, "y": 20, "w": 60, "h": 40},
    {"kind": "line", "layer": "wall", "x1": 100, "y1": 20, "x2": 180, "y2": 20},
    {"kind": "circle", "layer": "wall", "cx": 150, "cy": 90, "r": 15},
    {"kind": "label", "layer": "note", "x": 10, "y": 110, "text": "거실"},
]


class TestRoundTrip:

    @pytest.fixture()
    def svc(self):
        return ParametricCADService()

    def test_points_mode_roundtrip_preserves_px(self, svc):
        """기존 points 직변환 DXF 재가져오기 — 좌표 보존 ±0.01."""
        dxf = svc.create_dxf_from_edited_points(
            RECT_POINTS, RECT_SURFACES, scale_px_per_m=10,
        )
        out = parse_dxf_to_shapes(dxf, scale_px_per_m=10)
        polys = [s for s in out["shapes"] if s["kind"] == "polyline"]
        assert len(polys) == 1
        assert polys[0]["closed"] is True
        for got, exp in zip(polys[0]["points"], RECT_POINTS):
            assert got["x"] == pytest.approx(exp["x"], abs=0.01)
            assert got["y"] == pytest.approx(exp["y"], abs=0.01)
        assert out["main_outline_index"] == out["shapes"].index(polys[0])
        # 치수(DIMENSION)는 셰이프가 아니라 ignored로 투명 보고
        assert {"type": "DIMENSION", "count": 4} in out["ignored"]

    def test_shapes_mode_roundtrip_preserves_px(self, svc):
        """shapes 모드 DXF 재가져오기 — 전체 kind 좌표 보존 ±0.01."""
        dxf = svc.create_dxf_from_edited_points(
            [], None, scale_px_per_m=10, shapes=ROUNDTRIP_SHAPES,
        )
        out = parse_dxf_to_shapes(dxf, scale_px_per_m=10)
        # DIMENSION 제외 셰이프는 입력 순서 보존: polygon, rect, line, circle, label
        assert [s["kind"] for s in out["shapes"]] == [
            "polyline", "polyline", "line", "circle", "label",
        ]
        polygon, rect, line, circle, label = out["shapes"]

        for got, exp in zip(polygon["points"], ROUNDTRIP_SHAPES[0]["points"]):
            assert got["x"] == pytest.approx(exp["x"], abs=0.01)
            assert got["y"] == pytest.approx(exp["y"], abs=0.01)
        assert polygon["closed"] is True

        rect_exp = [(20, 20), (80, 20), (80, 60), (20, 60)]
        for got, (ex, ey) in zip(rect["points"], rect_exp):
            assert got["x"] == pytest.approx(ex, abs=0.01)
            assert got["y"] == pytest.approx(ey, abs=0.01)

        assert (line["x1"], line["y1"]) == (pytest.approx(100, abs=0.01),
                                            pytest.approx(20, abs=0.01))
        assert (line["x2"], line["y2"]) == (pytest.approx(180, abs=0.01),
                                            pytest.approx(20, abs=0.01))
        assert circle["cx"] == pytest.approx(150, abs=0.01)
        assert circle["cy"] == pytest.approx(90, abs=0.01)
        assert circle["r"] == pytest.approx(15, abs=0.01)
        assert label["x"] == pytest.approx(10, abs=0.01)
        assert label["y"] == pytest.approx(110, abs=0.01)
        assert label["text"] == "거실"

    def test_shapes_mode_roundtrip_unit_is_insunits_m(self, svc):
        """shapes 모드 내보내기는 $INSUNITS=6 기록 → 재가져오기 단위 확정(휴리스틱 불요)."""
        dxf = svc.create_dxf_from_edited_points(
            [], None, scale_px_per_m=10, shapes=ROUNDTRIP_SHAPES,
        )
        out = parse_dxf_to_shapes(dxf, scale_px_per_m=10)
        assert out["unit"] == {"detected": "m", "source": "insunits"}

    def test_shapes_mode_roundtrip_layer_mapping(self, svc):
        """레이어맵 왕복: outline→WALL→outline, wall→WALL_INTERIOR→wall, note→TEXT→note."""
        dxf = svc.create_dxf_from_edited_points(
            [], None, scale_px_per_m=10, shapes=ROUNDTRIP_SHAPES,
        )
        out = parse_dxf_to_shapes(dxf, scale_px_per_m=10)
        assert [s["layer"] for s in out["shapes"]] == [
            "outline", "wall", "wall", "wall", "note",
        ]
        assert out["main_outline_index"] == 0  # outline 폴리곤이 메인 외곽

    def test_shapes_mode_roundtrip_outline_dimensions_ignored(self, svc):
        """outline 변의 정식 DIMENSION(4개)은 재가져오기 시 ignored로 보고."""
        dxf = svc.create_dxf_from_edited_points(
            [], None, scale_px_per_m=10, shapes=ROUNDTRIP_SHAPES,
        )
        out = parse_dxf_to_shapes(dxf, scale_px_per_m=10)
        assert {"type": "DIMENSION", "count": 4} in out["ignored"]
