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
- 출처 헬퍼(_std/_practice/_paper) 분리: source_type 도메인·is_legal=False 강제,
  논문 항목 paper_ref 필수(법령화 금지)
- 신규 상수 무결성: ADJACENCY_WEIGHTS(frozenset 대칭·+2~−2)·ADJACENCY_DETECT(논문)·
  CLEARANCES(NKBA/Neufert)·STRUCTURE_SPANS(KDS 표4.2-1)·SECTION_RULES(반자2200·
  층고2400·Blondel)·PARKING_MODULE(주차장법 시행규칙 제3조)
- ROOM_TYPES.furniture_clearance_ref → CLEARANCES 키 참조 정합(additive)
"""

from app.services.cad.arch_grammar import (
    ADJACENCY_DETECT,
    ADJACENCY_WEIGHTS,
    ADJACENCY_WEIGHTS_META,
    BOUNDARY_DEFAULT_KIND,
    BOUNDARY_RULES,
    BOUNDARY_SCHEMA,
    CLEARANCES,
    DIMENSION_MODE,
    DIMENSION_MODE_LEGAL_BASIS,
    DOOR_HOST_PRIORITY,
    DOOR_OWNER_BY_PAIR,
    GRID_MODULE_MM,
    OPENING_SCHEMA,
    PARKING_MODULE,
    ROOM_NAME_MAP,
    ROOM_TYPES,
    SECTION_RULES,
    STRUCTURE_SPANS,
    WALL_TYPES,
    _legal,
    _paper,
    _practice,
    _std,
    room_type_of,
)
from app.services.cad.unit_plan_generator import UNIT_RULE_TABLE

_LAW_URL_PREFIX = "https://www.law.go.kr/"

# furniture_clearance_ref는 additive 신규 필드 — 기존 키 집합에 가산(무파손).
_ROOM_TYPE_REQUIRED_KEYS = {
    "min_area_sqm", "min_width_m", "needs_door", "door",
    "needs_window", "window", "wet", "source", "legal_basis", "note",
    "furniture_clearance_ref",
}

# 비법령 출처 분류 도메인(source_type 정합 검증용)
_NON_LEGAL_SOURCE_TYPES = {"표준", "실무가이드", "통상관행", "논문"}


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


# ── 신규(지식 심화) 검증 — 출처 헬퍼·신규 상수 무결성 ──────────────────────────


def _iter_sourced_dicts(obj):
    """중첩 구조에서 source_type 보유 dict 전수 순회(재귀 — 테스트 전용)."""
    if isinstance(obj, dict):
        if "source_type" in obj:
            yield obj
        for v in obj.values():
            yield from _iter_sourced_dicts(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _iter_sourced_dicts(v)


# 신규 상수 전수(출처 정합 스캔 대상)
_NEW_CONSTANTS = {
    "ADJACENCY_WEIGHTS_META": ADJACENCY_WEIGHTS_META,
    "ADJACENCY_DETECT": ADJACENCY_DETECT,
    "CLEARANCES": CLEARANCES,
    "STRUCTURE_SPANS": STRUCTURE_SPANS,
    "SECTION_RULES": SECTION_RULES,
    "PARKING_MODULE": PARKING_MODULE,
}


class TestSourceHelpers:
    """출처 헬퍼 분리 — _legal(법령 전용) vs _std/_practice/_paper(비법령)."""

    def test_std_record(self):
        rec = _std("KDS 14 20 30", "표4.2-1")
        assert rec["standard"] == "KDS 14 20 30"
        assert rec["clause"] == "표4.2-1"
        assert rec["source_type"] == "표준"
        assert rec["is_legal"] is False
        assert "url" not in rec  # 표준엔 법령 url 미생성(할루시네이션 링크 금지)

    def test_practice_record_default_and_guide(self):
        rec = _practice("테스트 관행")
        assert rec == {"note": "테스트 관행", "source_type": "통상관행", "is_legal": False}
        rec2 = _practice("테스트 가이드", source_type="실무가이드")
        assert rec2["source_type"] == "실무가이드"
        assert rec2["is_legal"] is False

    def test_paper_record_forces_paper_tag(self):
        """논문 헬퍼 — source_type='논문' 강제 + paper_ref 필수(법령화 절대 금지)."""
        rec = _paper("arXiv 0000.00000")
        assert rec["paper_ref"] == "arXiv 0000.00000"
        assert rec["source_type"] == "논문"
        assert rec["is_legal"] is False
        assert "law_name" not in rec and "url" not in rec

    def test_legal_record_is_distinct(self):
        """_legal()은 법령 전용 — 비법령 태그(source_type/is_legal) 미부착."""
        rec = _legal("건축법 시행령", "제51조")
        assert rec["law_name"] == "건축법 시행령"
        assert rec["article"] == "제51조"
        assert "source_type" not in rec
        assert "is_legal" not in rec
        if "url" in rec:
            assert rec["url"].startswith(_LAW_URL_PREFIX)


class TestSourceTypeConsistency:
    """신규 상수 전수 — source_type 도메인·is_legal=False·논문 paper_ref 정합."""

    def test_all_source_types_in_domain(self):
        for name, const in _NEW_CONSTANTS.items():
            for rec in _iter_sourced_dicts(const):
                assert rec["source_type"] in _NON_LEGAL_SOURCE_TYPES, (name, rec)

    def test_all_sourced_records_are_non_legal(self):
        """source_type 보유 레코드는 전부 비법령 — is_legal=False 강제."""
        for name, const in _NEW_CONSTANTS.items():
            for rec in _iter_sourced_dicts(const):
                assert rec["is_legal"] is False, (name, rec)
                assert "law_name" not in rec, (name, rec)  # 가짜 법령화 금지

    def test_paper_tagged_records_have_paper_ref(self):
        """source_type='논문' 레코드는 paper_ref 필수(역방향도 강제)."""
        seen_paper = 0
        for name, const in _NEW_CONSTANTS.items():
            for rec in _iter_sourced_dicts(const):
                if rec["source_type"] == "논문":
                    seen_paper += 1
                    assert rec.get("paper_ref"), (name, rec)
                if "paper_ref" in rec:
                    assert rec["source_type"] == "논문", (name, rec)
        assert seen_paper >= 1  # ADJACENCY_DETECT(R4) 최소 1건


class TestAdjacencyWeights:
    """인접 선호 가중치 — frozenset 대칭·값 도메인 +2~−2(0 미수록)·통상관행."""

    def test_keys_are_symmetric_frozensets_of_known_types(self):
        for pair in ADJACENCY_WEIGHTS:
            assert isinstance(pair, frozenset)
            assert len(pair) == 2
            for t in pair:
                assert t in ROOM_TYPES, t

    def test_symmetric_lookup(self):
        """frozenset 키 — A-B와 B-A 조회가 동일값(대칭 보장)."""
        for pair, w in ADJACENCY_WEIGHTS.items():
            a, b = sorted(pair)
            assert ADJACENCY_WEIGHTS[frozenset({a, b})] == w
            assert ADJACENCY_WEIGHTS[frozenset({b, a})] == w

    def test_value_domain(self):
        """+2~−2 정수, 0(중립)은 미수록(미정의=중립 — 엔진 계약)."""
        for pair, w in ADJACENCY_WEIGHTS.items():
            assert isinstance(w, int), pair
            assert w in (-2, -1, 1, 2), (set(pair), w)

    def test_key_weights(self):
        """A1 핵심: LDK +2·안방존 +2·현관-욕실 −2·침실-주방 −1."""
        assert ADJACENCY_WEIGHTS[frozenset({"living", "kitchen_dining"})] == 2
        assert ADJACENCY_WEIGHTS[frozenset({"kitchen_dining", "utility"})] == 2
        assert ADJACENCY_WEIGHTS[frozenset({"master_bedroom", "bath_master"})] == 2
        assert ADJACENCY_WEIGHTS[frozenset({"master_bedroom", "dress"})] == 2
        assert ADJACENCY_WEIGHTS[frozenset({"living", "entry"})] == 1
        assert ADJACENCY_WEIGHTS[frozenset({"entry", "bath_common"})] == -2
        assert ADJACENCY_WEIGHTS[frozenset({"bedroom", "kitchen_dining"})] == -1

    def test_meta_is_practice(self):
        assert ADJACENCY_WEIGHTS_META["source_type"] == "통상관행"
        assert ADJACENCY_WEIGHTS_META["is_legal"] is False


class TestAdjacencyDetect:
    """인접 판정 임계(R4) — 논문 태그 필수, 법령화 금지."""

    def test_dist_ratio_and_paper_tag(self):
        assert ADJACENCY_DETECT["dist_ratio"] == 0.03
        assert ADJACENCY_DETECT["source_type"] == "논문"
        assert ADJACENCY_DETECT["is_legal"] is False
        assert ADJACENCY_DETECT["paper_ref"]  # 논문 식별자 필수
        assert "law_name" not in ADJACENCY_DETECT


class TestClearances:
    """인체공학 클리어런스 — NKBA(표준)/Neufert(실무가이드) 출처 분리."""

    def test_top_level_keys_each_sourced(self):
        assert set(CLEARANCES.keys()) == {"kitchen", "bath", "furniture", "passage"}
        for key, spec in CLEARANCES.items():
            src = spec["source"]
            assert src["source_type"] in _NON_LEGAL_SOURCE_TYPES, key
            assert src["is_legal"] is False, key

    def test_kitchen_work_triangle_nkba(self):
        """NKBA G5: 변 1200~2700·합≤6700·동선 비관통."""
        tri = CLEARANCES["kitchen"]["work_triangle"]
        assert tri["leg_min_mm"] == 1200
        assert tri["leg_max_mm"] == 2700
        assert tri["sum_max_mm"] == 6700
        assert tri["no_traffic"] is True
        assert CLEARANCES["kitchen"]["source"]["standard"] == "NKBA Kitchen"
        assert CLEARANCES["kitchen"]["source"]["source_type"] == "표준"

    def test_kitchen_aisle_and_landing(self):
        aisle = CLEARANCES["kitchen"]["aisle_mm"]
        assert (aisle["cook1"], aisle["cook2"], aisle["walkway"]) == (1067, 1219, 914)
        assert aisle["opposed_min"] == 1067 and aisle["opposed_max"] == 1219
        landing = CLEARANCES["kitchen"]["landing_mm"]
        assert landing["sink"] == [610, 460]
        assert landing["fridge_handle"] == 380
        assert landing["cooktop"] == 300

    def test_bath_nkba(self):
        """NKBA Bathroom: 변기측면 380(권460)·전면 530(권760)·세면2 760(권910)."""
        bath = CLEARANCES["bath"]
        assert (bath["wc_to_wall_mm"], bath["wc_to_wall_rec_mm"]) == (380, 460)
        assert (bath["wc_front_mm"], bath["wc_front_rec_mm"]) == (530, 760)
        assert (bath["dual_lav_mm"], bath["dual_lav_rec_mm"]) == (760, 910)
        assert bath["source"]["standard"] == "NKBA Bathroom"

    def test_furniture_neufert_guide(self):
        fur = CLEARANCES["furniture"]
        assert fur["dining_wall_mm"] == 750
        assert fur["dining_wall_pass_mm"] == 1000
        assert fur["bed_access_mm"] == 700
        assert fur["wardrobe_front_mm"] == 900
        assert fur["source"]["source_type"] == "실무가이드"  # Neufert — 표준·법령 아님

    def test_passage_widths(self):
        p = CLEARANCES["passage"]
        assert (p["single_mm"], p["standard_mm"]) == (600, 900)
        assert (p["two_min_mm"], p["two_max_mm"]) == (1000, 1500)
        assert (p["unit_corridor_min_mm"], p["unit_corridor_max_mm"]) == (900, 1200)
        assert p["source"]["source_type"] == "실무가이드"


class TestStructureSpans:
    """구조 경간 KB — KDS 14 20 30 표4.2-1 비율 + RC/벽식 관행(데이터 전용)."""

    def test_slab_min_ratio_kds(self):
        r = STRUCTURE_SPANS["slab_min_ratio"]
        assert r["simple"] == 1.0 / 20.0
        assert r["one_end"] == 1.0 / 24.0
        assert r["both"] == 1.0 / 28.0
        assert r["cantilever"] == 1.0 / 10.0

    def test_beam_min_ratio_kds(self):
        r = STRUCTURE_SPANS["beam_min_ratio"]
        assert r["simple"] == 1.0 / 16.0
        assert r["one_end"] == 1.0 / 18.5
        assert r["both"] == 1.0 / 21.0
        assert r["cantilever"] == 1.0 / 8.0

    def test_correction_factors_are_formula_strings(self):
        """보정계수는 '식 문자열'만 KB 보관 — 계산 로직 0 원칙."""
        assert isinstance(STRUCTURE_SPANS["factor_fy"], str)
        assert "fy" in STRUCTURE_SPANS["factor_fy"]
        assert isinstance(STRUCTURE_SPANS["factor_lw"], str)
        assert "wc" in STRUCTURE_SPANS["factor_lw"]

    def test_rc_frame_practice(self):
        rc = STRUCTURE_SPANS["rc_frame"]
        assert rc["col_span_mm"] == [6000, 9000]
        assert rc["col_span_typ_mm"] == [6000, 7500]
        assert rc["warn_over_mm"] == 9000
        assert rc["source_type"] == "통상관행"  # KDS 비율과 달리 관행 — 출처 분리
        assert rc["is_legal"] is False

    def test_bearing_wall_practice(self):
        bw = STRUCTURE_SPANS["bearing_wall"]
        assert bw["spacing_max_mm"] == 6000
        assert bw["thickness_mm"] == [200, 250]
        assert bw["no_beam"] is True
        assert bw["source_type"] == "통상관행"

    def test_kds_source(self):
        src = STRUCTURE_SPANS["source"]
        assert src["standard"] == "KDS 14 20 30"
        assert "표4.2-1" in src["clause"]
        assert src["source_type"] == "표준"
        assert src["is_legal"] is False


class TestSectionRules:
    """단면 규칙 — 법정 반자 2200·층고 2400(법령 근거)·층고 적층 식·Blondel."""

    def test_height_minimums(self):
        assert SECTION_RULES["ceiling_h_min_mm"] == 2200
        assert SECTION_RULES["floor_h_min_mm"] == 2400
        assert SECTION_RULES["ceiling_h_typ_mm"] >= SECTION_RULES["ceiling_h_min_mm"]
        assert SECTION_RULES["floor_h_typ_mm"] >= SECTION_RULES["floor_h_min_mm"]

    def test_floor_height_stacking_formula_is_string(self):
        """층고 적층은 식 문자열만(산정은 엔진) — 계산 로직 0."""
        f = SECTION_RULES["floor_h_formula"]
        assert isinstance(f, str)
        assert "ceiling_h" in f and "slab_thickness" in f

    def test_blondel_stair_rule(self):
        b = SECTION_RULES["stair_blondel_mm"]
        assert b["two_r_plus_t_min"] == 600
        assert b["two_r_plus_t_max"] == 635
        assert SECTION_RULES["stair_source"]["source_type"] == "통상관행"

    def test_legal_basis_for_heights(self):
        basis = SECTION_RULES["ceiling_floor_legal_basis"]
        assert basis["law_name"] == "주택건설기준 등에 관한 규정"
        assert basis["article"] == "제3조"
        if "url" in basis:
            assert basis["url"].startswith(_LAW_URL_PREFIX)


class TestParkingModule:
    """주차 모듈 — 구획·차로(주차장법 시행규칙 제3조)·세대당 대수(조례 변동=관행)."""

    def test_stall_dimensions_legal(self):
        assert PARKING_MODULE["stall_mm"] == {"w": 2500, "l": 5000}
        assert PARKING_MODULE["stall_expanded_mm"] == {"w": 2600, "l": 5200}
        assert PARKING_MODULE["aisle_mm"]["right_angle"] == 6000
        basis = PARKING_MODULE["stall_legal_basis"]
        assert basis["law_name"] == "주차장법 시행규칙"
        assert basis["article"] == "제3조"
        if "url" in basis:
            assert basis["url"].startswith(_LAW_URL_PREFIX)

    def test_units_per_household_is_practice_not_legal(self):
        """세대당 대수 0.7~1.0 — 조례 변동(단일 법정값 없음, 가짜 법령화 금지)."""
        assert PARKING_MODULE["units_per_household"] == [0.7, 1.0]
        meta = PARKING_MODULE["units_per_household_meta"]
        assert meta["source_type"] == "통상관행"
        assert meta["is_legal"] is False


class TestFurnitureClearanceRef:
    """ROOM_TYPES.furniture_clearance_ref — CLEARANCES 키 참조 정합(additive)."""

    def test_ref_values_resolve_to_clearances(self):
        for rtype, spec in ROOM_TYPES.items():
            ref = spec["furniture_clearance_ref"]
            assert ref is None or ref in CLEARANCES, (rtype, ref)

    def test_key_room_refs(self):
        assert ROOM_TYPES["kitchen_dining"]["furniture_clearance_ref"] == "kitchen"
        assert ROOM_TYPES["bath_common"]["furniture_clearance_ref"] == "bath"
        assert ROOM_TYPES["bath_master"]["furniture_clearance_ref"] == "bath"
        assert ROOM_TYPES["corridor"]["furniture_clearance_ref"] == "passage"
        for t in ("living", "bedroom", "master_bedroom", "dress"):
            assert ROOM_TYPES[t]["furniture_clearance_ref"] == "furniture", t

    def test_unreferenced_rooms_are_none(self):
        """참조 클리어런스 미정의 실은 None — 가짜 참조 금지."""
        for t in ("entry", "utility", "balcony"):
            assert ROOM_TYPES[t]["furniture_clearance_ref"] is None, t
