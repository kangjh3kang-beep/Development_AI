"""UP2 — CAD 업로드 연동 허브(distribute) 계약 테스트.

parse_dxf_to_shapes 출력 형태의 dict를 직접 구성해(외부 의존 0 — ezdxf 불필요)
다음 계약을 검증한다:
  1) 네 소비형(editing_shapes/geometry_payload/design_raw/rooms) 분배 정합
  2) 빈/무효 입력 → None + diagnostics(가짜 기하 금지 — 정직)
  3) params_hint bbox 역산 정답값(scale 역산·신발끈 면적합)
  4) 멱등(동일 입력 → 동일 출력, 입력 무변형)
"""

import copy

from app.services.cad.cad_upload_hub import distribute

# ── 픽스처 빌더 ──

SCALE = 10.0  # 1m = 10px (parse_dxf_to_shapes 기본)


def _rect_points_px(x0: float, y0: float, w: float, h: float) -> list[dict[str, float]]:
    """축정렬 사각형 폴리라인 정점(px, 시계방향 아님 — 신발끈 절댓값이라 무관)."""
    return [
        {"x": x0, "y": y0},
        {"x": x0 + w, "y": y0},
        {"x": x0 + w, "y": y0 + h},
        {"x": x0, "y": y0 + h},
    ]


def _parse_result(
    shapes: list[dict],
    scale: float = SCALE,
    main_outline_index: int | None = None,
) -> dict:
    """parse_dxf_to_shapes 반환 형태의 최소 dict(테스트 픽스처)."""
    return {
        "shapes": shapes,
        "unit": {"detected": "m", "source": "insunits"},
        "scale_px_per_m": scale,
        "main_outline_index": main_outline_index,
        "ignored": [],
        "truncated": False,
        "shape_count": len(shapes),
    }


def _standard_fixture(scale: float = SCALE) -> dict:
    """닫힌 외곽선 12m×8m + 내부 라벨 '거실' + 보조선 + 원(스케일 가변)."""
    w_px, h_px = 12.0 * scale, 8.0 * scale
    return _parse_result(
        [
            {"kind": "polyline", "layer": "outline", "closed": True,
             "points": _rect_points_px(0.0, 0.0, w_px, h_px)},
            {"kind": "label", "layer": "note",
             "x": 6.0 * scale, "y": 4.0 * scale, "text": "거실"},
            {"kind": "line", "layer": "wall",
             "x1": 0.0, "y1": 0.0, "x2": w_px, "y2": 0.0},
            {"kind": "circle", "layer": "wall",
             "cx": 1.0 * scale, "cy": 1.0 * scale, "r": 0.5 * scale},
        ],
        scale=scale,
        main_outline_index=0,
    )


# ════════════════════════════════════════════════════════
# 1) 네 소비형 분배 정합
# ════════════════════════════════════════════════════════


class TestDistributeConsumers:

    def test_output_keys_contract(self):
        out = distribute(_standard_fixture())
        assert set(out.keys()) == {
            "editing_shapes", "geometry_payload", "design_raw",
            "rooms", "params_hint", "diagnostics",
        }

    def test_editing_shapes_sanitize_pass(self):
        """유효 셰이프 4건 전부 통과 — 좌표 무변형(검증 패스스루)."""
        pr = _standard_fixture()
        out = distribute(pr)
        assert len(out["editing_shapes"]) == 4
        assert out["editing_shapes"][0] == pr["shapes"][0]  # 기하 무변형
        assert out["diagnostics"] == []  # 전부 유효 — 사유 없음

    def test_editing_shapes_drops_invalid_with_reason(self):
        """무효 셰이프(line 좌표 결손)는 폐기 + diagnostics 사유(조용한 무시 금지)."""
        pr = _standard_fixture()
        pr["shapes"].append({"kind": "line", "x1": 0.0, "y1": 0.0})  # x2/y2 결손
        out = distribute(pr)
        assert len(out["editing_shapes"]) == 4  # 유효분만
        assert any("line 좌표 결손" in d for d in out["diagnostics"])

    def test_geometry_payload_standard_geometry(self):
        """normalize_geometry 재사용 — 표준 10px/m geometry + bbox m 치수."""
        out = distribute(_standard_fixture())
        geo = out["geometry_payload"]
        assert geo is not None
        assert geo["scale_px_per_m"] == 10.0
        assert geo["bbox"]["width_m"] == 12.0
        assert geo["bbox"]["height_m"] == 8.0
        # 닫힌 폴리라인 1건 → surface 1, 정점 4 + 보조선 2 = 점 6
        assert len(geo["surfaces"]) == 1
        assert len(geo["points"]) == 6
        # 닫힌 변 4 + 보조선 1 = 5
        assert len(geo["lines"]) == 5

    def test_geometry_payload_nondefault_scale_inverts_to_meters(self):
        """scale=20에서도 px→m 역산 후 표준 geometry로 정규화(치수 보존)."""
        out = distribute(_standard_fixture(scale=20.0))
        geo = out["geometry_payload"]
        assert geo is not None
        assert geo["bbox"]["width_m"] == 12.0
        assert geo["bbox"]["height_m"] == 8.0
        assert geo["scale_px_per_m"] == 10.0  # 출력은 항상 표준 10px/m

    def test_design_raw_contract(self):
        """design_payload_from_shapes 계약 — 닫힌 polygon→surface, 정점→points, 변→lines, id 자동부여."""
        out = distribute(_standard_fixture())
        design = out["design_raw"]
        assert design is not None
        # 폴리곤 정점 4 + 보조선 끝점 2
        assert len(design["points"]) == 6
        # 폴리곤 닫힌 변 4 + 보조선 1
        assert len(design["lines"]) == 5
        # 닫힌 폴리곤 1건 → surface 1(정점 id 4개)
        assert len(design["surfaces"]) == 1
        assert design["surfaces"][0]["point_ids"] == [
            "pt-s0-0", "pt-s0-1", "pt-s0-2", "pt-s0-3",
        ]
        # id 결정론 부여 + 참조 정합(모든 line 끝점이 points에 존재)
        point_ids = {p["id"] for p in design["points"]}
        for ln in design["lines"]:
            assert ln["start_point_id"] in point_ids
            assert ln["end_point_id"] in point_ids
        assert design["scale"] == 10.0

    def test_design_raw_none_without_closed_polygon(self):
        """닫힌 면이 없으면 design_raw=None + 사유(법규 기하검증 불가 — 정직)."""
        pr = _parse_result(
            [{"kind": "line", "x1": 0.0, "y1": 0.0, "x2": 50.0, "y2": 0.0}],
        )
        out = distribute(pr)
        assert out["design_raw"] is None
        assert any("design_raw:" in d for d in out["diagnostics"])

    def test_rooms_via_up1_extract_rooms(self):
        """UP1 extract_rooms 호출 — 라벨 '거실' 귀속·m 역산·실면적 정답."""
        out = distribute(_standard_fixture())
        rooms = out["rooms"]
        assert rooms is not None
        assert len(rooms["rooms"]) == 1
        room = rooms["rooms"][0]
        assert room["name"] == "거실"
        assert room["type"] == "living"
        assert room["inferred"] is False
        assert (room["x"], room["y"], room["w"], room["h"]) == (0.0, 0.0, 12.0, 8.0)
        assert room["area_sqm"] == 96.0

    def test_rooms_respects_scale(self):
        """scale=20에서도 px→m 역산이 정확(동일 m 치수)."""
        out = distribute(_standard_fixture(scale=20.0))
        room = out["rooms"]["rooms"][0]
        assert (room["w"], room["h"]) == (12.0, 8.0)
        assert room["area_sqm"] == 96.0

    def test_circle_label_only_geometry_none_with_reason(self):
        """점/선 형상 없음(circle/label만) — geometry None + 사유, editing은 통과."""
        pr = _parse_result(
            [
                {"kind": "circle", "cx": 10.0, "cy": 10.0, "r": 5.0},
                {"kind": "label", "x": 5.0, "y": 5.0, "text": "비고"},
            ],
        )
        out = distribute(pr)
        assert len(out["editing_shapes"]) == 2
        assert out["geometry_payload"] is None
        assert any("표준 geometry 생성 불가" in d for d in out["diagnostics"])
        assert out["design_raw"] is None
        assert out["params_hint"] is None


# ════════════════════════════════════════════════════════
# 2) 빈/무효 입력 — None + diagnostics(정직)
# ════════════════════════════════════════════════════════


class TestEmptyInput:

    def _assert_all_empty(self, out: dict):
        assert out["editing_shapes"] == []
        assert out["geometry_payload"] is None
        assert out["design_raw"] is None
        assert out["rooms"] is None
        assert out["params_hint"] is None
        assert len(out["diagnostics"]) >= 1

    def test_none_input(self):
        self._assert_all_empty(distribute(None))

    def test_empty_dict(self):
        self._assert_all_empty(distribute({}))

    def test_empty_shapes_list(self):
        out = distribute(_parse_result([]))
        self._assert_all_empty(out)
        assert any("shapes 비어 있음" in d for d in out["diagnostics"])

    def test_all_invalid_shapes(self):
        """전 셰이프 무효 → 정제 후 0건, 다운스트림 전부 미산출 + 사유 누적."""
        out = distribute(_parse_result(
            [
                {"kind": "line", "x1": 0.0},                 # 좌표 결손
                {"kind": "polyline", "points": [{"x": 1.0}]},  # 정점 무효
                {"kind": "unknown_kind"},                     # 미지 kind
                "문자열",                                      # dict 아님
            ],
        ))
        self._assert_all_empty(out)
        assert any("정제 후 유효 셰이프 0건" in d for d in out["diagnostics"])
        assert len(out["diagnostics"]) >= 5  # 셰이프별 사유 4건 + 종합 1건


# ════════════════════════════════════════════════════════
# 3) params_hint — bbox 역산 정답값
# ════════════════════════════════════════════════════════


class TestParamsHint:

    def test_bbox_inversion_scale_10(self):
        """120×80px @10px/m → 폭 12.0m·깊이 8.0m·면적 96.0㎡, source='도면추정'."""
        out = distribute(_standard_fixture())
        hint = out["params_hint"]
        assert hint is not None
        assert hint["building_width_m"] == 12.0
        assert hint["building_depth_m"] == 8.0
        assert hint["building_area_sqm"] == 96.0
        assert hint["source"] == "도면추정"

    def test_bbox_inversion_scale_20(self):
        """동일 px라도 scale=20이면 m 치수 절반 — 역산이 scale을 따라간다."""
        pr = _parse_result(
            [{"kind": "polyline", "closed": True,
              "points": _rect_points_px(0.0, 0.0, 120.0, 80.0)}],
            scale=20.0,
            main_outline_index=0,
        )
        hint = distribute(pr)["params_hint"]
        assert hint["building_width_m"] == 6.0
        assert hint["building_depth_m"] == 4.0
        assert hint["building_area_sqm"] == 24.0  # 9600px² / 20² = 24㎡

    def test_area_sums_all_closed_polygons(self):
        """면적은 닫힌 폴리곤 전부 합산, 폭/깊이는 메인 외곽선 bbox만."""
        pr = _parse_result(
            [
                {"kind": "polyline", "closed": True,
                 "points": _rect_points_px(0.0, 0.0, 120.0, 80.0)},   # 96㎡
                {"kind": "polyline", "closed": True,
                 "points": _rect_points_px(200.0, 0.0, 40.0, 40.0)},  # 16㎡
            ],
            main_outline_index=0,
        )
        hint = distribute(pr)["params_hint"]
        assert hint["building_width_m"] == 12.0   # 메인 외곽선(idx 0)만
        assert hint["building_depth_m"] == 8.0
        assert hint["building_area_sqm"] == 112.0  # 96 + 16 합산

    def test_no_closed_polygon_returns_none(self):
        """닫힌 외곽선 없음 → params_hint=None + 사유(가짜 치수 금지)."""
        pr = _parse_result(
            [{"kind": "line", "x1": 0.0, "y1": 0.0, "x2": 100.0, "y2": 0.0}],
        )
        out = distribute(pr)
        assert out["params_hint"] is None
        assert any("파라미터 힌트 산출 불가" in d for d in out["diagnostics"])

    def test_open_polyline_excluded_from_area(self):
        """열린 폴리라인은 면적 합산 제외(닫힌 폴리곤만)."""
        pr = _parse_result(
            [
                {"kind": "polyline", "closed": True,
                 "points": _rect_points_px(0.0, 0.0, 120.0, 80.0)},
                {"kind": "polyline", "closed": False,
                 "points": _rect_points_px(300.0, 0.0, 50.0, 50.0)},
            ],
            main_outline_index=0,
        )
        hint = distribute(pr)["params_hint"]
        assert hint["building_area_sqm"] == 96.0  # 열린 폴리라인 미합산


# ════════════════════════════════════════════════════════
# 4) 멱등 — 동일 입력 → 동일 출력, 입력 무변형
# ════════════════════════════════════════════════════════


class TestIdempotency:

    def test_same_input_same_output(self):
        pr = _standard_fixture()
        assert distribute(pr) == distribute(pr)

    def test_input_not_mutated(self):
        pr = _standard_fixture()
        snapshot = copy.deepcopy(pr)
        distribute(pr)
        assert pr == snapshot

    def test_deepcopy_inputs_equal_outputs(self):
        """객체 동일성이 아닌 값 동일성으로도 멱등(결정론 — 난수·외부상태 없음)."""
        out1 = distribute(_standard_fixture())
        out2 = distribute(copy.deepcopy(_standard_fixture()))
        assert out1 == out2
