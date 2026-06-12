"""arch_grammar(건축 설계 문법 KB) 무결성 테스트.

검증 항목:
- UNIT_RULE_TABLE 실명 전수 매핑(room_type_of — 미지명 None, 폴백 금지)
- ROOM_TYPES 스키마·문/창 치수(침실 900×2100 in, 욕실 750×2000 in, 현관 1000×2100
  out·방화, 다용도 750)
- BOUNDARY_RULES: frozenset 키, open 5쌍/wall_door 6쌍, 값 도메인
- DOOR_OWNER_BY_PAIR: wall_door 쌍과 1:1, 소유 타입은 needs_door
- WALL_TYPES: 내력 200/비내력 120, 경계벽 법령 근거
- 법령 근거 보유 항목의 url 형식(law.go.kr 검증 형식만 — 할루시네이션 링크 금지)
- GRID_MODULE_MM=50, DIMENSION_MODE='clear_inner', DOOR_HOST_PRIORITY
- BOUNDARY_SCHEMA/OPENING_SCHEMA 계약 키 존재(IFC 후속 계약)
"""

from app.services.cad.arch_grammar import (
    BOUNDARY_DEFAULT_KIND,
    BOUNDARY_RULES,
    BOUNDARY_SCHEMA,
    DIMENSION_MODE,
    DIMENSION_MODE_LEGAL_BASIS,
    DOOR_HOST_PRIORITY,
    DOOR_OWNER_BY_PAIR,
    GRID_MODULE_MM,
    OPENING_SCHEMA,
    ROOM_NAME_MAP,
    ROOM_TYPES,
    WALL_TYPES,
    room_type_of,
)
from app.services.cad.unit_plan_generator import UNIT_RULE_TABLE

_LAW_URL_PREFIX = "https://www.law.go.kr/"

_ROOM_TYPE_REQUIRED_KEYS = {
    "min_area_sqm", "min_width_m", "needs_door", "door",
    "needs_window", "window", "wet", "source", "legal_basis", "note",
}


def _all_rule_table_names() -> set[str]:
    names: set[str] = set()
    for rule in UNIT_RULE_TABLE.values():
        for name, _ in rule.south:
            names.add(name)
        for name, _ in rule.north:
            names.add(name)
        for name, _ in rule.mid:
            names.add(name)
    return names


class TestRoomNameMapping:
    """UNIT_RULE_TABLE 실명 전수 매핑 — 폴백 금지."""

    def test_all_rule_table_names_mapped(self):
        unmapped = sorted(n for n in _all_rule_table_names() if room_type_of(n) is None)
        assert unmapped == [], f"미매핑 실명: {unmapped}"

    def test_mapped_types_exist_in_room_types(self):
        for name in _all_rule_table_names() | {"발코니"}:
            rtype = room_type_of(name)
            assert rtype in ROOM_TYPES, f"{name} → {rtype} (ROOM_TYPES 미등록)"

    def test_key_mappings(self):
        assert room_type_of("현관") == "entry"
        assert room_type_of("거실") == "living"
        assert room_type_of("주방·식당") == "kitchen_dining"
        assert room_type_of("안방") == "master_bedroom"
        assert room_type_of("공용욕실") == "bath_common"
        assert room_type_of("부속욕실") == "bath_master"
        assert room_type_of("다용도실") == "utility"
        assert room_type_of("복도") == "corridor"
        assert room_type_of("드레스룸") == "dress"
        assert room_type_of("발코니") == "balcony"

    def test_bedroom_prefix(self):
        for n in ("침실2", "침실3", "침실4"):
            assert room_type_of(n) == "bedroom"

    def test_unknown_name_returns_none(self):
        """미지명은 None — 침묵 폴백 금지(엔진이 정직 경고 처리)."""
        assert room_type_of("알수없는실") is None
        assert room_type_of("") is None
        assert room_type_of(None) is None
        assert room_type_of(123) is None

    def test_name_map_values_are_room_types(self):
        for name, rtype in ROOM_NAME_MAP.items():
            assert rtype in ROOM_TYPES, f"{name} → {rtype}"


class TestRoomTypesKB:
    """ROOM_TYPES 스키마·문/창 치수 무결성."""

    def test_schema_keys(self):
        for rtype, spec in ROOM_TYPES.items():
            missing = _ROOM_TYPE_REQUIRED_KEYS - set(spec.keys())
            assert not missing, f"{rtype} 누락 키: {missing}"
            assert spec["source"] in ("법령", "LH기준", "통상관행"), rtype

    def test_needs_door_has_door_spec(self):
        for rtype, spec in ROOM_TYPES.items():
            if spec["needs_door"]:
                door = spec["door"]
                assert isinstance(door, dict), rtype
                assert door["width_mm"] > 0 and door["height_mm"] > 0, rtype
                assert door["swing"] in ("in", "out"), rtype
            else:
                assert spec["door"] is None, rtype

    def test_door_dimensions(self):
        """침실 900×2100 in / 욕실 750×2000 in / 다용도 750 / 현관 1000×2100 out·방화."""
        for t in ("bedroom", "master_bedroom"):
            d = ROOM_TYPES[t]["door"]
            assert (d["width_mm"], d["height_mm"], d["swing"]) == (900, 2100, "in")
        for t in ("bath_common", "bath_master"):
            d = ROOM_TYPES[t]["door"]
            assert (d["width_mm"], d["height_mm"], d["swing"]) == (750, 2000, "in")
        assert ROOM_TYPES["utility"]["door"]["width_mm"] == 750
        e = ROOM_TYPES["entry"]["door"]
        assert (e["width_mm"], e["height_mm"], e["swing"]) == (1000, 2100, "out")
        assert e["fire_rated"] is True

    def test_daylight_rooms_window_ratio(self):
        """거실·침실 채광: 창면적≥바닥 1/10·환기≥1/20 — 건축법 시행령 제51조."""
        for t in ("living", "bedroom", "master_bedroom"):
            spec = ROOM_TYPES[t]
            assert spec["needs_window"] is True, t
            w = spec["window"]
            assert abs(w["area_ratio_min"] - 0.1) < 1e-12, t
            assert abs(w["vent_ratio_min"] - 0.05) < 1e-12, t
            assert 0 < w["width_mm_min"] <= w["width_mm_max"], t
            basis = spec["legal_basis"]
            assert basis is not None and basis["law_name"] == "건축법 시행령", t
            assert basis["article"] == "제51조", t

    def test_undefined_minimums_are_none(self):
        """법정·관행 최소치 미정의 실은 None — 가짜값 금지."""
        assert ROOM_TYPES["utility"]["min_area_sqm"] is None
        assert ROOM_TYPES["balcony"]["min_area_sqm"] is None

    def test_wet_rooms(self):
        for t in ("bath_common", "bath_master", "kitchen_dining", "utility"):
            assert ROOM_TYPES[t]["wet"] is True, t
        for t in ("living", "bedroom", "entry", "corridor"):
            assert ROOM_TYPES[t]["wet"] is False, t


class TestBoundaryRules:
    """실간 경계 규칙 — frozenset 키, open 5쌍/wall_door 6쌍."""

    def test_keys_are_frozensets_of_known_types(self):
        for pair in BOUNDARY_RULES:
            assert isinstance(pair, frozenset)
            assert len(pair) == 2
            for t in pair:
                assert t in ROOM_TYPES, t

    def test_values_domain(self):
        assert set(BOUNDARY_RULES.values()) == {"open", "wall_door"}
        assert BOUNDARY_DEFAULT_KIND == "wall"

    def test_open_pairs_ldk(self):
        """LDK 오픈플랜 5쌍 — 거실↔주방 등은 벽 미설치."""
        open_pairs = {p for p, v in BOUNDARY_RULES.items() if v == "open"}
        assert open_pairs == {
            frozenset({"living", "kitchen_dining"}),
            frozenset({"living", "corridor"}),
            frozenset({"kitchen_dining", "corridor"}),
            frozenset({"entry", "corridor"}),
            frozenset({"entry", "living"}),
        }

    def test_wall_door_pairs(self):
        wd = {p for p, v in BOUNDARY_RULES.items() if v == "wall_door"}
        assert wd == {
            frozenset({"bedroom", "corridor"}),
            frozenset({"master_bedroom", "corridor"}),
            frozenset({"bath_common", "corridor"}),
            frozenset({"bath_master", "master_bedroom"}),
            frozenset({"utility", "kitchen_dining"}),
            frozenset({"dress", "master_bedroom"}),
        }

    def test_door_owner_matches_wall_door_pairs(self):
        wd = {p for p, v in BOUNDARY_RULES.items() if v == "wall_door"}
        assert set(DOOR_OWNER_BY_PAIR.keys()) == wd
        for pair, owner in DOOR_OWNER_BY_PAIR.items():
            assert owner in pair, f"{owner} ∉ {set(pair)}"
            assert ROOM_TYPES[owner]["needs_door"] is True, owner


class TestWallTypes:
    """벽 타입 — 내력 200(법령)/비내력 120(통상관행)."""

    def test_bearing_walls_200(self):
        for t in ("exterior", "unit_party", "core"):
            spec = WALL_TYPES[t]
            assert spec["thickness_mm"] == 200, t
            assert spec["bearing"] is True, t
            basis = spec["legal_basis"]
            assert basis is not None, t
            assert basis["law_name"] == "주택건설기준 등에 관한 규정", t
            assert basis["article"] == "제14조", t

    def test_partition_120_convention(self):
        p = WALL_TYPES["partition"]
        assert p["thickness_mm"] == 120
        assert p["bearing"] is False
        assert p["source"] == "통상관행"
        assert p["legal_basis"] is None  # 법정 기준 아님 — 가짜 근거 금지


class TestLegalUrls:
    """법령 근거 보유 항목의 url 형식 — law.go.kr 검증 형식만."""

    @staticmethod
    def _iter_legal_bases():
        for spec in list(ROOM_TYPES.values()) + list(WALL_TYPES.values()):
            if spec.get("legal_basis"):
                yield spec["legal_basis"]
        yield DIMENSION_MODE_LEGAL_BASIS

    def test_url_format_when_present(self):
        seen = 0
        for basis in self._iter_legal_bases():
            assert basis["law_name"], basis
            assert basis["article"].startswith("제"), basis
            if "url" in basis:  # registry 가용 시에만 생성(실패 시 텍스트만 — 정직)
                seen += 1
                assert basis["url"].startswith(_LAW_URL_PREFIX), basis["url"]
        # 본 테스트 환경에서는 registry import가 가능해야 한다(url 전수 생성)
        assert seen > 0, "법령 url이 하나도 생성되지 않았습니다(registry import 실패?)"

    def test_dimension_mode_basis(self):
        assert DIMENSION_MODE_LEGAL_BASIS["law_name"] == "주택건설기준 등에 관한 규칙"
        assert DIMENSION_MODE_LEGAL_BASIS["article"] == "제3조"


class TestGrammarConstants:
    """그리드·치수 기준·문 호스트 우선순위·IFC 스키마 계약."""

    def test_grid_module(self):
        assert GRID_MODULE_MM == 50

    def test_dimension_mode(self):
        assert DIMENSION_MODE == "clear_inner"

    def test_door_host_priority(self):
        assert DOOR_HOST_PRIORITY == ("corridor", "living", "kitchen_dining")
        for t in DOOR_HOST_PRIORITY:
            assert t in ROOM_TYPES

    def test_boundary_schema_contract_keys(self):
        for key in ("id", "room_a", "room_b", "side", "orient",
                    "length_m", "balcony_front", "kind", "wall_type", "door_owner"):
            assert key in BOUNDARY_SCHEMA, key

    def test_opening_schema_contract_keys(self):
        for key in ("id", "kind", "subtype", "boundary_id", "room", "host",
                    "orient", "width_mm,height_mm", "swing", "swing_side",
                    "hinge", "fire_rated"):
            assert key in OPENING_SCHEMA, key
