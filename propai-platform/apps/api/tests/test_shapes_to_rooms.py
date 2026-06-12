"""shapes_to_rooms(UP1 — shapes→rooms 역추출 + bbox 경계 어댑터) 단위 테스트.

검증 항목(WI-1·WI-2 스펙):
- 닫힌 polygon(정점≥3, shoelace 면적>1㎡)만 실 추출 — 미달분 정직 경고 폐기
- 라벨 point-in-polygon 귀속 → room_type_of 타입·실명 확정(미등록 실명 type=None)
- 미라벨 추정 + 정직 표기 — name='실(추정)' 고정·inferred=True·confidence,
  한글 실명 날조 금지·라벨 거실 존재 시 거실 추정 억제
- bbox 인접성 — 공유변 경계(BOUNDARY_SCHEMA)·외기변(room_b=None)·미인접 갭 경고
- 면적 보존 — bbox 사각화에도 원본 polygon·shoelace 실면적(area_sqm) 보존
- 순수 결정론(동일 입력=동일 출력)·scale 명시 오류·parse_result dict 수용(UP2 허브)
- unit_plan_generator 경계 엔진(classify_boundaries·place_openings·
  validate_connectivity) 무수정 재사용 파이프라인(end-to-end)
"""

import pytest

from app.services.cad.arch_grammar import BOUNDARY_SCHEMA, room_type_of
from app.services.cad.shapes_to_rooms import (
    INFERRED_ROOM_NAME,
    MIN_ROOM_AREA_SQM,
    boundaries_from_bbox_rooms,
    extract_rooms,
)
from app.services.cad.unit_plan_generator import (
    classify_boundaries,
    place_openings,
    validate_connectivity,
)

_SCALE = 10.0  # 기본 환산(1m = 10px)


# ── 테스트 도형 빌더(px) ──

def _rect_px(x: float, y: float, w: float, h: float,
             scale: float = _SCALE, **extra) -> dict:
    """m 단위 사각형을 px polygon shape로 변환(시계방향 4정점)."""
    pts = [
        [x * scale, y * scale],
        [(x + w) * scale, y * scale],
        [(x + w) * scale, (y + h) * scale],
        [x * scale, (y + h) * scale],
    ]
    return {"kind": "polygon", "points": pts, **extra}


def _label_px(text: str, x: float, y: float, scale: float = _SCALE) -> dict:
    return {"kind": "label", "text": text, "x": x * scale, "y": y * scale}


def _two_room_shapes() -> list[dict]:
    """거실(0,0,4,5)=20㎡ + 침실2(4,0,3,5)=15㎡, 라벨 각 1개."""
    return [
        _rect_px(0, 0, 4, 5),
        _rect_px(4, 0, 3, 5),
        _label_px("거실", 2, 2.5),
        _label_px("침실2", 5.5, 2.5),
    ]


_ROOM_KEYS = {
    "name", "type", "x", "y", "w", "h",
    "polygon", "area_sqm", "inferred", "confidence", "label_source",
}


# ── ① 닫힌 폴리곤 실 추출 ──

class TestClosedPolygonExtraction:
    """닫힌 polygon(정점≥3, 면적>1㎡)만 실 후보 — 미달분 정직 폐기."""

    def test_closed_polygons_become_rooms(self):
        out = extract_rooms(_two_room_shapes())
        assert out["warnings"] == []
        rooms = out["rooms"]
        assert len(rooms) == 2
        # 결정론 정렬: (y, x) — 거실(x=0)이 먼저
        assert [r["name"] for r in rooms] == ["거실", "침실2"]
        living = rooms[0]
        assert set(living.keys()) == _ROOM_KEYS
        assert (living["x"], living["y"], living["w"], living["h"]) == (0.0, 0.0, 4.0, 5.0)

    def test_min_area_filter_drops_tiny_polygon(self):
        shapes = [
            _rect_px(0, 0, 1, 1),       # 1.0㎡ — 경계값, > 1.0 아님 → 폐기
            _rect_px(2, 0, 0.5, 0.5),   # 0.25㎡ → 폐기
            _rect_px(0, 2, 2, 2),       # 4.0㎡ → 채택
            _label_px("욕실", 1, 3),
        ]
        out = extract_rooms(shapes)
        assert len(out["rooms"]) == 1
        assert out["rooms"][0]["name"] == "욕실"
        area_warns = [w for w in out["warnings"] if w["rule"] == "최소 실면적"]
        assert len(area_warns) == 2
        assert all(str(MIN_ROOM_AREA_SQM) in str(w["legal"]) for w in area_warns)

    def test_under_3_vertices_dropped_with_warning(self):
        shapes = [{"kind": "polygon", "points": [[0, 0], [100, 0]]}]
        out = extract_rooms(shapes)
        assert out["rooms"] == []
        assert any(w["rule"] == "정점 수" for w in out["warnings"])

    def test_open_polyline_not_a_room(self):
        """closed=False 명시(벽선·치수선) — 실 후보 제외(무관 도형)."""
        shapes = [{
            "kind": "polyline", "closed": False,
            "points": [[0, 0], [40, 0], [40, 50], [0, 50]],
        }]
        out = extract_rooms(shapes)
        assert out["rooms"] == []

    def test_closed_polyline_is_a_room(self):
        """closed=True polyline(DXF parse_result 형) — 실 채택."""
        shapes = [
            {"kind": "polyline", "closed": True,
             "points": [{"x": 0, "y": 0}, {"x": 40, "y": 0},
                        {"x": 40, "y": 50}, {"x": 0, "y": 50}]},
            _label_px("거실", 2, 2.5),
        ]
        out = extract_rooms(shapes)
        assert len(out["rooms"]) == 1
        assert out["rooms"][0]["name"] == "거실"
        assert out["rooms"][0]["area_sqm"] == 20.0

    def test_non_dict_shape_warned(self):
        out = extract_rooms(["잡음", _rect_px(0, 0, 2, 2), _label_px("욕실", 1, 1)])
        assert len(out["rooms"]) == 1
        assert any(w["rule"] == "도형 타입" for w in out["warnings"])

    @pytest.mark.parametrize("bad_scale", [0, -3.0, None])
    def test_scale_must_be_positive(self, bad_scale):
        with pytest.raises(ValueError):
            extract_rooms([], scale_px_per_m=bad_scale)

    def test_pixel_to_m_scale_inversion(self):
        """px / scale = m — scale 100px/m 도면에서 동일 m 좌표 복원."""
        shapes = [_rect_px(0, 0, 4, 5, scale=100.0), _label_px("거실", 2, 2.5, scale=100.0)]
        out = extract_rooms(shapes, scale_px_per_m=100.0)
        r = out["rooms"][0]
        assert (r["x"], r["y"], r["w"], r["h"]) == (0.0, 0.0, 4.0, 5.0)
        assert r["area_sqm"] == 20.0

    def test_determinism_same_input_same_output(self):
        shapes = _two_room_shapes()
        assert extract_rooms(shapes) == extract_rooms(shapes)


# ── ② 라벨 귀속 ──

class TestLabelAttribution:
    """label point-in-polygon 귀속 → room_type_of 타입 확정."""

    def test_label_inside_polygon_sets_name_and_type(self):
        out = extract_rooms(_two_room_shapes())
        by_name = {r["name"]: r for r in out["rooms"]}
        assert by_name["거실"]["type"] == "living"
        assert by_name["거실"]["inferred"] is False
        assert by_name["거실"]["confidence"] is None
        assert by_name["거실"]["label_source"] == "label"
        assert by_name["침실2"]["type"] == "bedroom"  # '침실' prefix 규칙

    def test_unregistered_label_keeps_name_type_none(self):
        """미등록 실명 '창고' — name 보존·type=None·정직 경고(날조 금지)."""
        shapes = [_rect_px(0, 0, 3, 3), _label_px("창고", 1.5, 1.5)]
        out = extract_rooms(shapes)
        r = out["rooms"][0]
        assert r["name"] == "창고"
        assert r["type"] is None
        assert r["inferred"] is False
        assert any(w["rule"] == "실명 매핑" and w["field"] == "창고"
                   for w in out["warnings"])

    def test_label_outside_any_polygon_warned(self):
        shapes = [_rect_px(0, 0, 4, 4), _label_px("거실", 50, 50)]
        out = extract_rooms(shapes)
        assert any(w["rule"] == "라벨 귀속" for w in out["warnings"])
        # 귀속 실패 → 해당 실은 미라벨 추정 경로
        assert out["rooms"][0]["inferred"] is True

    def test_duplicate_labels_first_kept_deterministic(self):
        shapes = [
            _rect_px(0, 0, 4, 4),
            _label_px("거실", 1, 1),
            _label_px("주방·식당", 2, 2),
        ]
        out = extract_rooms(shapes)
        assert out["rooms"][0]["name"] == "거실"  # shapes 순서상 첫 라벨 유지
        assert any(w["rule"] == "라벨 중복" for w in out["warnings"])


# ── ③ 미라벨 추정 + 정직 표기 ──

class TestUnlabeledInference:
    """면적 휴리스틱 타입 추정 — 실명 날조 금지·inferred·confidence 정직 표기."""

    @pytest.fixture()
    def inferred_out(self) -> dict:
        # 20㎡(최대) / 12㎡(중형) / 3㎡(소형 습식) — 라벨 없음
        shapes = [
            _rect_px(0, 0, 5, 4),
            _rect_px(5, 0, 3, 4),
            _rect_px(0, 4, 2, 1.5),
        ]
        return extract_rooms(shapes)

    def test_max_area_inferred_living(self, inferred_out):
        rooms = inferred_out["rooms"]
        largest = max(rooms, key=lambda r: r["area_sqm"])
        assert largest["area_sqm"] == 20.0
        assert largest["type"] == "living"

    def test_small_room_inferred_bath(self, inferred_out):
        small = min(inferred_out["rooms"], key=lambda r: r["area_sqm"])
        assert small["area_sqm"] == 3.0
        assert small["type"] == "bath_common"

    def test_mid_room_inferred_bedroom(self, inferred_out):
        mid = next(r for r in inferred_out["rooms"] if r["area_sqm"] == 12.0)
        assert mid["type"] == "bedroom"

    def test_honest_marking_no_korean_name_fabrication(self, inferred_out):
        """전 미라벨 실: name='실(추정)' 고정 + inferred + confidence∈(0,1]."""
        for r in inferred_out["rooms"]:
            assert r["name"] == INFERRED_ROOM_NAME
            assert r["inferred"] is True
            assert r["label_source"] == "heuristic"
            assert isinstance(r["confidence"], float)
            assert 0.0 < r["confidence"] <= 1.0
        # placeholder는 실명 매핑에 존재하지 않는다(법령·KB 오염 방지)
        assert room_type_of(INFERRED_ROOM_NAME) is None

    def test_inference_warnings_emitted(self, inferred_out):
        infer_warns = [w for w in inferred_out["warnings"] if w["rule"] == "미라벨 추정"]
        assert len(infer_warns) == 3
        assert all(w["field"] == INFERRED_ROOM_NAME for w in infer_warns)

    def test_living_inference_suppressed_when_labeled_living_exists(self):
        """라벨 거실이 이미 있으면 더 큰 미라벨 실도 living으로 추정하지 않는다."""
        shapes = [
            _rect_px(0, 0, 4, 4),       # 16㎡ — 라벨 거실
            _rect_px(4, 0, 5, 4),       # 20㎡ — 미라벨(더 큼)
            _label_px("거실", 2, 2),
        ]
        out = extract_rooms(shapes)
        unl = next(r for r in out["rooms"] if r["inferred"])
        assert unl["type"] == "bedroom"  # living 억제 → 일반 추정 경로
        assert unl["name"] == INFERRED_ROOM_NAME


# ── ④ 면적 보존(bbox 사각화에도 원본 기하 보존) ──

class TestAreaPreservation:
    """L자형 등 비직사각 실 — bbox(w·h)와 별개로 polygon·shoelace 면적 보존."""

    def test_l_shape_polygon_and_area_preserved(self):
        # L자: (0,0)→(4,0)→(4,2)→(2,2)→(2,4)→(0,4) — 면적 12㎡, bbox 4×4
        pts_m = [(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)]
        shapes = [
            {"kind": "polygon",
             "points": [[x * _SCALE, y * _SCALE] for x, y in pts_m]},
            _label_px("거실", 1, 1),
        ]
        out = extract_rooms(shapes)
        r = out["rooms"][0]
        assert r["area_sqm"] == 12.0                      # 실면적(shoelace)
        assert (r["w"], r["h"]) == (4.0, 4.0)             # bbox 사각화
        assert r["polygon"] == [[float(x), float(y)] for x, y in pts_m]  # 원본 보존

    def test_rect_area_equals_bbox_area(self):
        out = extract_rooms(_two_room_shapes())
        for r in out["rooms"]:
            assert r["area_sqm"] == pytest.approx(r["w"] * r["h"], abs=1e-6)


# ── ⑤ bbox 인접성(경계 어댑터) ──

def _grid_rooms() -> list[dict]:
    """2×2 그리드: 거실(0,0,4,4)·침실2(4,0,3,4)·주방·식당(0,4,4,3)·욕실(4,4,3,3)."""
    return [
        {"name": "거실", "x": 0.0, "y": 0.0, "w": 4.0, "h": 4.0},
        {"name": "침실2", "x": 4.0, "y": 0.0, "w": 3.0, "h": 4.0},
        {"name": "주방·식당", "x": 0.0, "y": 4.0, "w": 4.0, "h": 3.0},
        {"name": "욕실", "x": 4.0, "y": 4.0, "w": 3.0, "h": 3.0},
    ]


def _boundary_contract_keys() -> set[str]:
    """BOUNDARY_SCHEMA에서 어댑터 산출 키 집합(kind/wall_type/door_owner는
    classify_boundaries 부여 — 어댑터 미산출)."""
    keys: set[str] = set()
    for k in BOUNDARY_SCHEMA:
        if k in ("kind", "wall_type", "door_owner"):
            continue
        keys.update(k.split(","))
    return keys


class TestBoundariesFromBboxRooms:
    """공유변 → BOUNDARY_SCHEMA 경계, 외곽=room_b None, 갭 경고."""

    @pytest.fixture()
    def grid_out(self) -> dict:
        return boundaries_from_bbox_rooms(_grid_rooms())

    def test_counts_and_no_warnings(self, grid_out):
        assert grid_out["warnings"] == []
        bounds = grid_out["boundaries"]
        internal = [b for b in bounds if b["room_b"] is not None]
        external = [b for b in bounds if b["room_b"] is None]
        assert len(internal) == 4
        assert len(external) == 8
        assert len(bounds) == 12

    def test_internal_pairs(self, grid_out):
        pairs = {
            (b["room_a"], b["room_b"])
            for b in grid_out["boundaries"] if b["room_b"] is not None
        }
        assert pairs == {
            ("거실", "침실2"), ("거실", "주방·식당"),
            ("침실2", "욕실"), ("주방·식당", "욕실"),
        }

    def test_vertical_shared_edge_exact(self, grid_out):
        b = next(x for x in grid_out["boundaries"]
                 if (x["room_a"], x["room_b"]) == ("거실", "침실2"))
        assert b["side"] == "e"          # room_a(서측)→room_b 방향
        assert b["orient"] == "v"
        assert b["x1"] == b["x2"] == 4.0
        assert (b["y1"], b["y2"]) == (0.0, 4.0)
        assert b["length_m"] == 4.0
        assert b["balcony_front"] is False

    def test_horizontal_shared_edge_exact(self, grid_out):
        b = next(x for x in grid_out["boundaries"]
                 if (x["room_a"], x["room_b"]) == ("거실", "주방·식당"))
        assert b["side"] == "s"          # room_a(북측)→room_b 방향
        assert b["orient"] == "h"
        assert b["y1"] == b["y2"] == 4.0
        assert (b["x1"], b["x2"]) == (0.0, 4.0)
        assert b["length_m"] == 4.0

    def test_external_boundaries_room_b_none(self, grid_out):
        ext_sides: dict[str, set[str]] = {}
        for b in grid_out["boundaries"]:
            if b["room_b"] is None:
                ext_sides.setdefault(b["room_a"], set()).add(b["side"])
        assert ext_sides == {
            "거실": {"n", "w"}, "침실2": {"n", "e"},
            "주방·식당": {"w", "s"}, "욕실": {"e", "s"},
        }
        # 남측 외기(채광면)는 본체 남단 y=7
        south = [b for b in grid_out["boundaries"]
                 if b["room_b"] is None and b["side"] == "s"]
        assert all(b["y1"] == b["y2"] == 7.0 for b in south)

    def test_ids_deterministic(self, grid_out):
        ids = [b["id"] for b in grid_out["boundaries"]]
        assert ids == [f"b{k:03d}" for k in range(1, 13)]
        again = boundaries_from_bbox_rooms(_grid_rooms())
        assert again["boundaries"] == grid_out["boundaries"]

    def test_boundary_keys_match_schema_contract(self, grid_out):
        contract = _boundary_contract_keys()
        for b in grid_out["boundaries"]:
            assert set(b.keys()) == contract

    def test_partial_overlap_spans_intersection_only(self):
        rooms = [
            {"name": "거실", "x": 0.0, "y": 0.0, "w": 4.0, "h": 4.0},
            {"name": "침실2", "x": 4.0, "y": 2.0, "w": 3.0, "h": 4.0},
        ]
        out = boundaries_from_bbox_rooms(rooms)
        b = next(x for x in out["boundaries"] if x["room_b"] == "침실2")
        assert (b["y1"], b["y2"]) == (2.0, 4.0)  # 겹침 구간만
        assert b["length_m"] == 2.0

    def test_gap_warns_per_room(self):
        rooms = [
            {"name": "거실", "x": 0.0, "y": 0.0, "w": 4.0, "h": 4.0},
            {"name": "침실2", "x": 5.0, "y": 0.0, "w": 3.0, "h": 4.0},  # 1m 갭
        ]
        out = boundaries_from_bbox_rooms(rooms)
        gap_warns = [w for w in out["warnings"] if w["rule"] == "실 인접성"]
        assert {w["field"] for w in gap_warns} == {"거실", "침실2"}
        assert all(b["room_b"] is None for b in out["boundaries"])  # 내부 경계 0

    def test_single_room_externals_no_gap_warning(self):
        out = boundaries_from_bbox_rooms(
            [{"name": "거실", "x": 0.0, "y": 0.0, "w": 4.0, "h": 4.0}]
        )
        assert out["warnings"] == []
        assert {b["side"] for b in out["boundaries"]} == {"n", "s", "e", "w"}
        assert all(b["room_b"] is None for b in out["boundaries"])

    def test_missing_bbox_fields_warned_and_excluded(self):
        rooms = [
            {"name": "거실", "x": 0.0, "y": 0.0, "w": 4.0, "h": 4.0},
            {"name": "파손", "x": 1.0},  # w/h 결손
        ]
        out = boundaries_from_bbox_rooms(rooms)
        assert any(w["rule"] == "실 bbox 필드" for w in out["warnings"])
        assert all(b["room_a"] == "거실" for b in out["boundaries"])

    def test_empty_rooms(self):
        assert boundaries_from_bbox_rooms([]) == {"boundaries": [], "warnings": []}


# ── ⑥ parse_result dict 수용(UP2 cad_upload_hub 호출 계약) ──

class TestParseResultDictInput:
    """extract_rooms(parse_result) — dict 입력 unwrap + 내장 scale 우선."""

    def test_parse_result_dict_uses_embedded_scale(self):
        pr = {
            "shapes": [
                _rect_px(0, 0, 4, 5, scale=20.0),
                _label_px("거실", 2, 2.5, scale=20.0),
            ],
            "scale_px_per_m": 20.0,
        }
        out = extract_rooms(pr)  # 파라미터 기본 10.0이지만 내장 20.0 우선
        r = out["rooms"][0]
        assert (r["w"], r["h"], r["area_sqm"]) == (4.0, 5.0, 20.0)

    def test_invalid_embedded_scale_falls_back_with_warning(self):
        pr = {"shapes": _two_room_shapes(), "scale_px_per_m": -1}
        out = extract_rooms(pr)  # 파라미터(기본 10.0) 사용 + 정직 경고
        assert any(w["rule"] == "내장 스케일" for w in out["warnings"])
        assert out["rooms"][0]["w"] == 4.0

    def test_dict_without_shapes_key(self):
        out = extract_rooms({"scale_px_per_m": 10.0})
        assert out["rooms"] == []


# ── ⑦ plan 엔진 재사용 파이프라인(end-to-end, 무수정 import) ──

class TestPlanEnginePipelineReuse:
    """shapes → rooms → boundaries → classify/openings/connectivity 전 구간."""

    @pytest.fixture()
    def plan(self) -> dict:
        # 7m×6m 완전 타일링: 현관·복도·욕실(북측 띠) + 거실·침실2(남측 띠)
        shapes = [
            _rect_px(0, 0, 2, 2), _label_px("현관", 1, 1),
            _rect_px(2, 0, 2, 2), _label_px("복도", 3, 1),
            _rect_px(4, 0, 3, 2), _label_px("욕실", 5.5, 1),
            _rect_px(0, 2, 4, 4), _label_px("거실", 2, 4),
            _rect_px(4, 2, 3, 4), _label_px("침실2", 5.5, 4),
        ]
        extracted = extract_rooms(shapes)
        assert extracted["warnings"] == []
        rooms = extracted["rooms"]
        bres = boundaries_from_bbox_rooms(rooms)
        assert bres["warnings"] == []
        classified, cls_warnings = classify_boundaries(bres["boundaries"], rooms)
        openings, open_warnings = place_openings(classified, rooms)
        return {
            "rooms": rooms, "boundaries": classified, "openings": openings,
            "cls_warnings": cls_warnings, "open_warnings": open_warnings,
        }

    def _pair(self, plan, a, b):
        return next(
            x for x in plan["boundaries"]
            if x["room_b"] is not None and {x["room_a"], x["room_b"]} == {a, b}
        )

    def test_ldk_open_chain(self, plan):
        assert self._pair(plan, "현관", "복도")["kind"] == "open"
        assert self._pair(plan, "현관", "거실")["kind"] == "open"
        assert self._pair(plan, "복도", "거실")["kind"] == "open"

    def test_bath_wall_door(self, plan):
        b = self._pair(plan, "복도", "욕실")
        assert b["kind"] == "wall_door"
        assert b["door_owner"] == "욕실"

    def test_bedroom_door_promoted(self, plan):
        """침실2 — BOUNDARY_RULES 미정의 쌍뿐이므로 1실 1문 승격 경로."""
        b = self._pair(plan, "거실", "침실2")
        assert b["kind"] == "wall_door"
        assert b["door_owner"] == "침실2"
        assert any(w["rule"] == "1실 1문" for w in plan["cls_warnings"])

    def test_external_boundaries_classified_exterior(self, plan):
        ext = [b for b in plan["boundaries"] if b["room_b"] is None]
        assert ext
        assert all(b["kind"] == "wall" and b["wall_type"] == "exterior" for b in ext)

    def test_openings_placed(self, plan):
        doors = [o for o in plan["openings"] if o["kind"] == "door"]
        entr = [d for d in doors if d["subtype"] == "entrance"]
        assert len(entr) == 1
        assert entr[0]["fire_rated"] is True
        assert {d["room"] for d in doors if d["subtype"] == "swing"} == {"욕실", "침실2"}
        windows = [o for o in plan["openings"] if o["kind"] == "window"]
        assert {w["room"] for w in windows} >= {"거실", "침실2"}

    def test_connectivity_all_rooms_reachable(self, plan):
        violations = validate_connectivity(
            plan["rooms"], plan["boundaries"], plan["openings"]
        )
        assert violations == []
