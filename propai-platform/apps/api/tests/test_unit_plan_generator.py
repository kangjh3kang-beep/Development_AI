"""unit_plan_generator(R3-1 결정론 유닛플랜) 단위 테스트 — 정답값 회귀.

검증 항목(계획서 R3-1 스펙):
- 59㎡/84㎡ × 2/3베이 결정론 출력(동일 입력 = 동일 출력)
- 84형 3베이 정답 좌표 고정(회귀 가드)
- Σ실면적 = 전용면적 ±5%(실제로는 mm 반올림 수준)
- 채광(거실·침실 외기면 접함)·최소 실면적 검증 통과(룰 테이블 전수)
- 잘못된 입력(베이 5 등) 시 명시 오류
- DesignSpec.unit_grammar additive(기본 None = 기존 동작 불변)
- SVG 렌더(generate_unit_plan_rooms) — 기존 도면 함수 무파손
- 경계 엔진(arch_grammar): 84㎡ 3베이 정답 — LDK open 체인·문 수 고정·
  50mm 그리드·연결성 BFS·창면적 1/10 + SVG 경계 단위 렌더(additive)
"""

import pytest

from app.services.cad.arch_grammar import GRID_MODULE_MM, room_type_of
from app.services.cad.design_spec import DesignSpec, UnitGrammar, validate_spec
from app.services.cad.unit_plan_generator import (
    SUPPORTED_BAYS,
    UNIT_CORE_TYPES,
    UNIT_RULE_TABLE,
    UnitPlanResult,
    classify_boundaries,
    extract_boundaries,
    generate_unit_plan,
    place_openings,
    validate_connectivity,
    validate_unit_layout,
)

# 계획서 명시 조합: 59/84 × 2/3베이
SPEC_COMBOS = [(59.0, 2), (59.0, 3), (84.0, 2), (84.0, 3)]

# 룰 테이블 전수(밴드 명목 면적)
_BAND_NOMINAL = {"49": 49.0, "59": 59.0, "74": 74.0, "84": 84.0, "114": 114.0}
ALL_TABLE_COMBOS = sorted(
    (_BAND_NOMINAL[band], bays) for (band, bays) in UNIT_RULE_TABLE
)


class TestDeterminism:
    """동일 입력 = 동일 출력(결정론)."""

    @pytest.mark.parametrize("area,bays", SPEC_COMBOS)
    def test_same_input_same_output(self, area: float, bays: int):
        r1 = generate_unit_plan(area, bays)
        r2 = generate_unit_plan(area, bays)
        assert r1.rooms == r2.rooms
        assert r1.balconies == r2.balconies
        assert r1.body_width_m == r2.body_width_m
        assert r1.body_depth_m == r2.body_depth_m
        assert r1.violations == r2.violations

    def test_returns_result_type(self):
        r = generate_unit_plan(84.0, 3)
        assert isinstance(r, UnitPlanResult)
        assert r.band == "84"
        assert r.bays == 3
        for room in r.rooms:
            assert set(room.keys()) == {"name", "x", "y", "w", "h"}


class Test84Type3BayFixedAnswer:
    """84형 3베이 정답 좌표 고정(수기 계산 회귀 가드).

    W = 3.0+4.2+3.6 = 10.8m, D = 84/10.8 = 7.778m,
    북측 띠 2.8m / 중간 띠 1.167m / 남측 띠 3.811m.
    """

    @pytest.fixture()
    def result(self) -> UnitPlanResult:
        return generate_unit_plan(84.0, 3)

    def test_body_dimensions(self, result: UnitPlanResult):
        assert result.body_width_m == 10.8
        assert result.body_depth_m == 7.778

    def test_living_room_exact(self, result: UnitPlanResult):
        rooms = {r["name"]: r for r in result.rooms}
        assert rooms["거실"] == {"name": "거실", "x": 3.0, "y": 3.967, "w": 4.2, "h": 3.811}

    def test_north_bedroom_exact(self, result: UnitPlanResult):
        rooms = {r["name"]: r for r in result.rooms}
        assert rooms["침실3"] == {"name": "침실3", "x": 7.452, "y": 0.0, "w": 3.348, "h": 2.8}

    def test_master_bath_exact(self, result: UnitPlanResult):
        rooms = {r["name"]: r for r in result.rooms}
        assert rooms["부속욕실"] == {"name": "부속욕실", "x": 9.0, "y": 2.8, "w": 1.8, "h": 1.167}

    def test_program_3bed_2bath(self, result: UnitPlanResult):
        """계획서 스펙: 84㎡ 3베이 = LDK 남측향, 침실 3, 욕실 2."""
        names = [r["name"] for r in result.rooms]
        bedrooms = [n for n in names if n == "안방" or n.startswith("침실")]
        baths = [n for n in names if "욕실" in n]
        assert len(bedrooms) == 3
        assert len(baths) == 2
        # 거실은 남측 채광면(y+h == D)
        living = next(r for r in result.rooms if r["name"] == "거실")
        assert abs(living["y"] + living["h"] - result.body_depth_m) < 1e-3


class TestAreaConsistency:
    """Σ실면적 = 전용면적 ±5%(가짜값 금지 — 실제 타일링 검증)."""

    @pytest.mark.parametrize("area,bays", SPEC_COMBOS)
    def test_room_area_sum_within_5pct(self, area: float, bays: int):
        r = generate_unit_plan(area, bays)
        total = sum(rm["w"] * rm["h"] for rm in r.rooms)
        assert abs(total - area) <= area * 0.05
        # 실제로는 mm 반올림 수준(0.5% 이내)이어야 한다
        assert abs(total - area) <= area * 0.005

    @pytest.mark.parametrize("area,bays", SPEC_COMBOS)
    def test_rooms_tile_body_exactly(self, area: float, bays: int):
        r = generate_unit_plan(area, bays)
        total = sum(rm["w"] * rm["h"] for rm in r.rooms)
        assert abs(total - r.body_width_m * r.body_depth_m) < 0.05

    @pytest.mark.parametrize("area,bays", SPEC_COMBOS)
    def test_exclusive_area_field(self, area: float, bays: int):
        r = generate_unit_plan(area, bays)
        assert abs(r.exclusive_area_sqm - area) <= area * 0.05


class TestValidationRules:
    """채광·최소 실면적·침실 최소폭 — 표준 룰 테이블 전수 통과 + 위반 검출."""

    @pytest.mark.parametrize("area,bays", ALL_TABLE_COMBOS)
    def test_all_table_combos_pass(self, area: float, bays: int):
        r = generate_unit_plan(area, bays)
        assert r.violations == [], f"{area}㎡ {bays}베이 위반: {r.violations}"
        assert r.ok is True

    @pytest.mark.parametrize("area,bays", SPEC_COMBOS)
    def test_daylight_rooms_touch_exterior(self, area: float, bays: int):
        """거실·침실은 북(y=0) 또는 남(y+h=D) 외기면에 접해야 한다."""
        r = generate_unit_plan(area, bays)
        for room in r.rooms:
            if room["name"] == "거실" or room["name"] == "안방" or room["name"].startswith("침실"):
                touches = room["y"] <= 1e-3 or (room["y"] + room["h"]) >= r.body_depth_m - 1e-3
                assert touches, f"{room['name']} 채광면 미접촉"

    def test_detects_interior_bedroom(self):
        """외기면에 접하지 않는 침실 → 채광 위반 검출(가짜 통과 금지)."""
        rooms = [{"name": "침실2", "x": 0.0, "y": 2.0, "w": 3.0, "h": 2.5}]
        violations = validate_unit_layout(rooms, 10.0, 8.0)
        assert any(v["rule"] == "채광(외기면 접함)" for v in violations)

    def test_detects_undersized_bath(self):
        rooms = [{"name": "욕실", "x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}]
        violations = validate_unit_layout(rooms, 1.0, 1.0)
        assert any(v["rule"] == "최소 실면적" and v["field"] == "욕실" for v in violations)

    def test_detects_undersized_bedroom(self):
        rooms = [{"name": "안방", "x": 0.0, "y": 0.0, "w": 2.0, "h": 2.5}]
        violations = validate_unit_layout(rooms, 2.0, 2.5)
        assert any(v["rule"] == "최소 실면적" for v in violations)  # 5.0 < 6.0
        assert any(v["rule"] == "침실 최소폭" for v in violations)  # 2.0 < 2.1

    def test_detects_tiling_gap(self):
        """본체를 다 채우지 못한 배치 → 면적 정합 위반."""
        rooms = [{"name": "거실", "x": 0.0, "y": 4.0, "w": 4.0, "h": 4.0}]
        violations = validate_unit_layout(rooms, 10.0, 8.0)
        assert any(v["rule"] == "면적 정합" for v in violations)


class TestExplicitErrors:
    """잘못된 입력 시 명시 오류(침묵 폴백 금지)."""

    def test_bays_5_raises(self):
        with pytest.raises(ValueError, match="베이"):
            generate_unit_plan(84.0, 5)

    def test_bays_1_raises(self):
        with pytest.raises(ValueError, match="베이"):
            generate_unit_plan(59.0, 1)

    def test_zero_area_raises(self):
        with pytest.raises(ValueError, match="전용면적"):
            generate_unit_plan(0.0, 3)

    def test_negative_area_raises(self):
        with pytest.raises(ValueError, match="전용면적"):
            generate_unit_plan(-10.0, 3)

    def test_unknown_core_type_raises(self):
        with pytest.raises(ValueError, match="코어타입"):
            generate_unit_plan(84.0, 3, core_type="원형코어")

    def test_unsupported_combo_raises(self):
        """114형 2베이 — 표준 룰 미정의 조합은 명시 오류."""
        with pytest.raises(ValueError, match="표준 룰"):
            generate_unit_plan(114.0, 2)

    def test_unsupported_combo_49_4bay_raises(self):
        with pytest.raises(ValueError, match="표준 룰"):
            generate_unit_plan(49.0, 4)


class TestBalconyGrammar:
    """발코니 확장 문법 — 전용면적(rooms) 불변, 서비스면적 플래그만 반영."""

    def test_balcony_present_south(self):
        r = generate_unit_plan(84.0, 3)
        assert len(r.balconies) == 1
        b = r.balconies[0]
        assert b["y"] == r.body_depth_m  # 남측(본체 밖)
        assert b["w"] == r.body_width_m
        assert b["extended"] is False
        assert r.service_area_sqm > 0

    def test_extension_flag_only_changes_balcony(self):
        base = generate_unit_plan(84.0, 3, balcony_extension=False)
        ext = generate_unit_plan(84.0, 3, balcony_extension=True)
        assert base.rooms == ext.rooms  # 전용면적 타일링 불변
        assert ext.balconies[0]["extended"] is True
        assert ext.balcony_extension is True
        assert base.service_area_sqm == ext.service_area_sqm

    def test_core_type_recorded(self):
        r = generate_unit_plan(59.0, 2, core_type="복도형")
        assert r.core_type == "복도형"


class TestDesignSpecGrammar:
    """DesignSpec.unit_grammar — additive·하위호환."""

    def test_default_none_backward_compat(self):
        spec = DesignSpec(site_area_sqm=500.0)
        assert spec.unit_grammar is None
        assert validate_spec(spec) == []  # 기존 클린 스펙 그대로 무위반

    def test_to_site_input_unaffected(self):
        spec = DesignSpec(site_area_sqm=500.0, unit_grammar=UnitGrammar(bays=3))
        si = spec.to_site_input()
        assert si.site_area_sqm == 500.0  # 커널 입력 변환 무영향

    def test_valid_grammar_no_violation(self):
        spec = DesignSpec(
            site_area_sqm=500.0,
            unit_grammar=UnitGrammar(bays=3, core_type="계단실형", balcony_extension=True),
        )
        assert [v for v in validate_spec(spec) if v.field.startswith("unit_grammar")] == []

    def test_invalid_bays_violation(self):
        spec = DesignSpec(site_area_sqm=500.0, unit_grammar=UnitGrammar(bays=5))
        violations = [v for v in validate_spec(spec) if v.field == "unit_grammar.bays"]
        assert len(violations) == 1
        assert violations[0].severity == "error"

    def test_invalid_core_type_violation(self):
        spec = DesignSpec(
            site_area_sqm=500.0, unit_grammar=UnitGrammar(core_type="없는형"),
        )
        violations = [v for v in validate_spec(spec) if v.field == "unit_grammar.core_type"]
        assert len(violations) == 1

    def test_grammar_constants_shared(self):
        assert SUPPORTED_BAYS == (2, 3, 4)
        assert "계단실형" in UNIT_CORE_TYPES


class TestSVGRender:
    """svg_drawing_service.generate_unit_plan_rooms — 신규 렌더 + 기존 무파손."""

    @pytest.fixture(autouse=True)
    def _require_svgwrite(self):
        pytest.importorskip("svgwrite")

    @pytest.fixture()
    def svc(self):
        from app.services.drawing.svg_drawing_service import SVGDrawingService
        return SVGDrawingService()

    def test_renders_rooms_and_labels(self, svc):
        r = generate_unit_plan(84.0, 3)
        svg = svc.generate_unit_plan_rooms(
            r.rooms, r.body_width_m, r.body_depth_m,
            unit_type="84A", area_sqm=84.0, balconies=r.balconies,
        )
        assert svg.startswith("<svg") or "<svg" in svg
        for label in ("거실", "안방", "침실2", "침실3"):
            assert label in svg
        assert "발코니" in svg

    def test_extended_balcony_label(self, svc):
        r = generate_unit_plan(59.0, 3, balcony_extension=True)
        svg = svc.generate_unit_plan_rooms(
            r.rooms, r.body_width_m, r.body_depth_m,
            unit_type="59A", area_sqm=59.0, balconies=r.balconies,
        )
        assert "발코니(확장)" in svg

    def test_body_dims_derived_when_omitted(self, svc):
        r = generate_unit_plan(59.0, 2)
        svg = svc.generate_unit_plan_rooms(r.rooms)  # body 치수 생략 → rooms 외곽 산출
        assert "<svg" in svg
        assert "거실" in svg

    def test_empty_rooms_placeholder(self, svc):
        svg = svc.generate_unit_plan_rooms([])
        assert "<svg" in svg  # 명시 placeholder(크래시 금지)

    def test_existing_unit_plan_unbroken(self, svc):
        """기존 generate_unit_plan(파라메트릭) 회귀 — 시그니처·동작 불변."""
        svg = svc.generate_unit_plan("84A", 84.0)
        assert "<svg" in svg
        assert "거실" in svg

    def test_full_drawing_set_additive(self, svc):
        """unit_plan 미제공 시 기존 도면 코드 동일, 제공 시 B-02-UNIT-R 추가."""
        base_data = {
            "site_width_m": 60.0, "site_depth_m": 40.0,
            "building_width_m": 40.0, "building_depth_m": 20.0,
            "floor_count": 5, "floor_height_m": 3.0,
            "project_name": "R3-1 테스트",
        }
        base = svc.generate_full_drawing_set(dict(base_data))
        assert "B-02-UNIT-R" not in base  # 미제공 → 기존 세트 그대로

        r = generate_unit_plan(84.0, 3)
        with_plan = svc.generate_full_drawing_set({
            **base_data,
            "unit_plan": {
                "rooms": r.rooms,
                "body_width_m": r.body_width_m,
                "body_depth_m": r.body_depth_m,
                "balconies": r.balconies,
                "unit_type": "84A",
                "area_sqm": 84.0,
            },
        })
        assert "B-02-UNIT-R" in with_plan
        assert "거실" in with_plan["B-02-UNIT-R"]
        # 기존 도면 코드는 그대로 존재
        for code in base:
            assert code in with_plan


# ── 경계 엔진(arch_grammar) — 84㎡ 3베이 정답 ──


def _open_reachable(boundaries: list, start: str) -> set:
    """open 경계만으로 도달 가능한 실 집합(BFS) — LDK open 체인 검증용."""
    adj: dict[str, set] = {}
    for b in boundaries:
        if b.get("kind") == "open" and b.get("room_b") is not None:
            adj.setdefault(b["room_a"], set()).add(b["room_b"])
            adj.setdefault(b["room_b"], set()).add(b["room_a"])
    seen = {start}
    queue = [start]
    while queue:
        cur = queue.pop(0)
        for nxt in sorted(adj.get(cur, ())):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


class TestBoundaryEngine84Type3Bay:
    """84형 3베이 — 경계 추출·분류·개구·연결성 정답(결정론 회귀 가드)."""

    @pytest.fixture()
    def result(self) -> UnitPlanResult:
        return generate_unit_plan(84.0, 3)

    def test_additive_keys_present_rooms_unchanged(self, result: UnitPlanResult):
        """boundaries/openings는 additive — 기존 rooms 키 계약 불변."""
        assert result.boundaries and result.openings
        for room in result.rooms:
            assert set(room.keys()) == {"name", "x", "y", "w", "h"}
        d = result.as_dict()
        for key in ("boundaries", "openings", "grammar_warnings"):
            assert key in d

    def test_boundaries_deterministic(self):
        r1 = generate_unit_plan(84.0, 3)
        r2 = generate_unit_plan(84.0, 3)
        assert r1.boundaries == r2.boundaries
        assert r1.openings == r2.openings

    def test_boundary_schema_fields(self, result: UnitPlanResult):
        for b in result.boundaries:
            for key in ("id", "room_a", "room_b", "side", "orient",
                        "x1", "y1", "x2", "y2", "length_m",
                        "balcony_front", "kind", "wall_type", "door_owner"):
                assert key in b, (key, b)
            assert b["kind"] in ("open", "wall", "wall_door")
            assert b["orient"] in ("h", "v")

    def test_ldk_open_chain_living_to_kitchen(self, result: UnitPlanResult):
        """거실↔주방 경로 open 체인(복도 경유) — 벽 미생성(LDK 오픈플랜)."""
        reachable = _open_reachable(result.boundaries, "거실")
        assert "주방·식당" in reachable, "거실→주방 open 체인 단절(LDK 위반)"
        # 거실-주방 사이에 wall/wall_door 직접 경계가 생성되면 안 된다
        for b in result.boundaries:
            pair = {b["room_a"], b.get("room_b")}
            if pair == {"거실", "주방·식당"}:
                assert b["kind"] == "open", b

    def test_open_boundaries_exact(self, result: UnitPlanResult):
        """open 경계 = 현관↔복도, 주방↔복도, 복도↔거실(84형 3베이 인접 구성)."""
        open_pairs = {
            frozenset({b["room_a"], b["room_b"]})
            for b in result.boundaries if b["kind"] == "open"
        }
        assert open_pairs == {
            frozenset({"현관", "복도"}),
            frozenset({"주방·식당", "복도"}),
            frozenset({"복도", "거실"}),
        }

    def test_door_counts_fixed(self, result: UnitPlanResult):
        """침실문 3 + 욕실문 2 + 현관문 1 = 총 6문(정답 고정)."""
        doors = [o for o in result.openings if o["kind"] == "door"]
        assert len(doors) == 6
        bedroom_doors = [o for o in doors
                         if room_type_of(o["room"]) in ("bedroom", "master_bedroom")]
        bath_doors = [o for o in doors
                      if room_type_of(o["room"]) in ("bath_common", "bath_master")]
        entrance = [o for o in doors if o["subtype"] == "entrance"]
        assert len(bedroom_doors) == 3
        assert len(bath_doors) == 2
        assert len(entrance) == 1
        assert entrance[0]["fire_rated"] is True
        assert entrance[0]["swing"] == "out"
        assert entrance[0]["width_mm"] == 1000

    def test_one_door_per_room_invariant(self, result: UnitPlanResult):
        """1실 1문 — needs_door 실마다 자기 소유 문 정확히 1개."""
        owned: dict[str, int] = {}
        for o in result.openings:
            if o["kind"] == "door":
                owned[o["room"]] = owned.get(o["room"], 0) + 1
        for name in ("침실2", "침실3", "안방", "공용욕실", "부속욕실", "현관"):
            assert owned.get(name) == 1, (name, owned)

    def test_all_doors_on_50mm_grid(self, result: UnitPlanResult):
        """모든 문 중심(벽 진행축)이 50mm 그리드 위."""
        for o in result.openings:
            if o["kind"] != "door":
                continue
            axis = o["center_x_m"] if o["orient"] == "h" else o["center_y_m"]
            assert round(axis * 1000) % GRID_MODULE_MM == 0, o

    def test_connectivity_bfs_all_rooms_reached(self, result: UnitPlanResult):
        """현관 기점 BFS(open·문 간선) — 전실 도달, 위반 0."""
        violations = validate_connectivity(
            result.rooms, result.boundaries, result.openings,
        )
        assert violations == []
        assert result.grammar_warnings == []  # 84형 3베이 정답: 문법 경고 0

    def test_window_area_ratio_living_and_bedrooms(self, result: UnitPlanResult):
        """거실·침실(안방 포함) 창면적 ≥ 바닥면적 1/10(건축법 시행령 제51조)."""
        rooms = {r["name"]: r for r in result.rooms}
        windows = {o["room"]: o for o in result.openings if o["kind"] == "window"}
        for name in ("거실", "침실2", "침실3", "안방"):
            assert name in windows, f"{name} 창 미배치"
            o = windows[name]
            win_area = o["width_mm"] * o["height_mm"] / 1e6
            floor_area = rooms[name]["w"] * rooms[name]["h"]
            assert win_area >= floor_area / 10.0 - 1e-9, (name, win_area, floor_area)
            assert 1500 <= o["width_mm"] <= 2400, o

    def test_balcony_front_sliding_windows(self, result: UnitPlanResult):
        """남측(발코니 전면) 창은 분합창(balcony_sliding) — 거실 포함."""
        living = next(o for o in result.openings
                      if o["kind"] == "window" and o["room"] == "거실")
        assert living["subtype"] == "balcony_sliding"
        south = [b for b in result.boundaries
                 if b["room_b"] is None and b["side"] == "s"]
        assert south and all(b["balcony_front"] for b in south)

    def test_engine_functions_composable(self, result: UnitPlanResult):
        """엔진 단계 함수 직접 호출 = generate_unit_plan 내장 결과와 동일(결정론)."""
        raw = extract_boundaries(
            result.rooms, result.body_width_m, result.body_depth_m,
            balconies=result.balconies,
        )
        classified, warn1 = classify_boundaries(raw, result.rooms)
        openings, warn2 = place_openings(classified, result.rooms)
        assert classified == result.boundaries
        assert openings == result.openings
        assert warn1 == [] and warn2 == []

    def test_undefined_room_name_warns_not_silent(self):
        """미등록 실명 → wall 처리 + 정직 경고(침묵 폴백 금지)."""
        rooms = [
            {"name": "미지실", "x": 0.0, "y": 0.0, "w": 3.0, "h": 4.0},
            {"name": "거실", "x": 3.0, "y": 0.0, "w": 3.0, "h": 4.0},
        ]
        raw = extract_boundaries(rooms, 6.0, 4.0)
        classified, warnings = classify_boundaries(raw, rooms)
        interior = [b for b in classified if b["room_b"] is not None]
        assert interior and all(b["kind"] == "wall" for b in interior)
        assert any(w["rule"] == "실명 매핑" for w in warnings)


class TestSVGBoundaryRender:
    """SVG 경계 단위 렌더 — additive(미제공 시 기존 렌더 그대로)."""

    @pytest.fixture(autouse=True)
    def _require_svgwrite(self):
        pytest.importorskip("svgwrite")

    @pytest.fixture()
    def svc(self):
        from app.services.drawing.svg_drawing_service import SVGDrawingService
        return SVGDrawingService()

    @pytest.fixture()
    def result(self) -> UnitPlanResult:
        return generate_unit_plan(84.0, 3)

    def test_wall_path_count_equals_nonopen_boundaries(self, svc, result):
        """boundaries 제공 시 벽 path 수 = (open 제외) 경계 수 — 전실 박스 아님."""
        svg = svc.generate_unit_plan_rooms(
            result.rooms, result.body_width_m, result.body_depth_m,
            unit_type="84A", area_sqm=84.0, balconies=result.balconies,
            boundaries=result.boundaries, openings=result.openings,
        )
        n_wall_paths = svg.count('class="wall"')
        n_nonopen = sum(1 for b in result.boundaries if b["kind"] != "open")
        assert n_wall_paths == n_nonopen
        # 실 라벨·면적·발코니 등 기존 표기 유지
        for label in ("거실", "안방", "침실2", "침실3", "발코니"):
            assert label in svg

    def test_legacy_render_unchanged_without_boundaries(self, svc, result):
        """미제공 시 기존 렌더 경로 그대로 — 동일 입력 = 동일 바이트, 벽 path 없음."""
        kwargs = dict(unit_type="84A", area_sqm=84.0, balconies=result.balconies)
        svg1 = svc.generate_unit_plan_rooms(
            result.rooms, result.body_width_m, result.body_depth_m, **kwargs)
        svg2 = svc.generate_unit_plan_rooms(
            result.rooms, result.body_width_m, result.body_depth_m, **kwargs)
        assert svg1 == svg2  # 결정론(바이트 동일)
        assert 'class="wall"' not in svg1  # 경계 렌더 미적용(기존 poché 박스)

    def test_full_drawing_set_passes_boundaries(self, svc, result):
        """full_drawing_set 배선 — unit_plan.boundaries 제공 시 경계 렌더 적용."""
        drawings = svc.generate_full_drawing_set({
            "site_width_m": 60.0, "site_depth_m": 40.0,
            "building_width_m": 40.0, "building_depth_m": 20.0,
            "floor_count": 5, "floor_height_m": 3.0,
            "project_name": "경계 렌더 테스트",
            "unit_plan": {
                "rooms": result.rooms,
                "body_width_m": result.body_width_m,
                "body_depth_m": result.body_depth_m,
                "balconies": result.balconies,
                "boundaries": result.boundaries,
                "openings": result.openings,
                "unit_type": "84A",
                "area_sqm": 84.0,
            },
        })
        assert "B-02-UNIT-R" in drawings
        assert 'class="wall"' in drawings["B-02-UNIT-R"]
