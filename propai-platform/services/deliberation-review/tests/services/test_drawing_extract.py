"""P-A — 멀티모달 도면 자동해석: 힌트/비전 추출·날조금지·결정론·정규화·파이프라인 배선."""
from datetime import date

from app.adapters.vision.drawing_extractor import DrawingExtractor
from app.contracts.analysis import AnalysisInput
from app.contracts.drawing_extraction import DrawingSheet, normalize_semantic_hint
from app.services.pipeline.analysis_pipeline import run_analysis


class _FakeVision:
    """주입 비전 클라이언트(결정론) — 요소 2건(하나는 미상 타입)."""

    def extract_elements(self, image_ref, hint_text):
        return [{"type": "PARKING", "confidence": 0.8, "area": 30.0},
                {"type": "foobar", "confidence": 0.5}]


class _EmptyVision:
    def extract_elements(self, image_ref, hint_text):
        return None  # 비전 실패/빈 → 상위 힌트 폴백


def test_extract_from_hints():
    r = DrawingExtractor().extract([DrawingSheet(
        sheet_id="s1", sheet_role="PLAN",
        element_hints=[{"semantic_hint": "PILOTIS", "hint_strength": 0.9, "area": 100.0}])])
    assert r.source == "HINTS"
    assert len(r.elements) == 1
    assert r.elements[0].semantic_hint == "PILOTIS"
    assert r.elements[0].area == 100.0
    assert r.elements[0].provenance["src"] == "hint"


def test_extract_from_vision_normalizes_unknown():
    r = DrawingExtractor(vision_client=_FakeVision()).extract([
        DrawingSheet(sheet_id="s1", image_ref="img://1")])
    assert r.source == "VLLM_VISION"
    assert len(r.elements) == 2
    assert r.elements[0].semantic_hint == "PARKING" and r.elements[0].area == 30.0
    assert r.elements[1].semantic_hint == "UNKNOWN"  # 미상 타입 → UNKNOWN(날조 금지, INV-9)


def test_no_image_no_hint_surfaced():
    r = DrawingExtractor().extract([DrawingSheet(sheet_id="s1")])
    assert r.source == "none"
    assert r.elements == []
    assert any("추출 불가" in n for n in r.notes)


def test_vision_empty_falls_back_to_hints():
    r = DrawingExtractor(vision_client=_EmptyVision()).extract([DrawingSheet(
        sheet_id="s1", image_ref="img://1",
        element_hints=[{"semantic_hint": "PARKING", "hint_strength": 0.7}])])
    assert r.source == "HINTS"
    assert len(r.elements) == 1
    assert any("힌트 폴백" in n for n in r.notes)


def test_deterministic():
    sheets = [DrawingSheet(sheet_id="s1", element_hints=[{"semantic_hint": "EXT_WALL", "hint_strength": 0.8}])]
    assert DrawingExtractor().extract(sheets) == DrawingExtractor().extract(sheets)


def test_normalize_helper():
    assert normalize_semantic_hint("parking") == "PARKING"
    assert normalize_semantic_hint("미상요소") == "UNKNOWN"
    assert normalize_semantic_hint(None) == "UNKNOWN"


def test_pipeline_drawings_wired():
    r = run_analysis(AnalysisInput(
        pnu="1111010100100000002", application_date=date(2026, 1, 1),
        drawings=[{"sheet_id": "A-PLAN", "sheet_role": "PLAN",
                   "element_hints": [{"semantic_hint": "PILOTIS", "hint_strength": 0.9, "area": 100.0}]}]))
    assert r.drawing_source == "HINTS"
    assert r.drawing_elements_n == 1
    assert r.extraction_source == "VLLM"  # 도면 자동추출 요소가 2D/VLLM 경로로 흐름
    assert r.bim_elements == []


def test_calc_target_auto_from_area_table():
    # P-A.2: 면적표(outer_area 600) + 추출요소(PILOTIS 100㎡) → 건축면적 자동 산정 = 500.
    r = run_analysis(AnalysisInput(
        pnu="1111010100100000002", application_date=date(2026, 1, 1),
        drawings=[{"sheet_id": "A-AREA", "sheet_role": "AREA_TABLE",
                   "area_table": {"target": "building_area", "outer_area": 600.0},
                   "element_hints": [{"semantic_hint": "PILOTIS", "hint_strength": 0.95, "area": 100.0}]}]))
    assert r.calc_targets_source == "DRAWING_AUTO"
    assert len(r.legal_quantities) == 1
    assert r.legal_quantities[0].value == 500.0  # 600 - 100(필로티 제외)


def test_drawing_auto_balcony_depth_passthrough():
    # INC-3: 도면 자동경로에서 BALCONY 깊이(depth) 승계 검증 — 깊이 2.0 > 기준 1.5 → 제외 안함.
    # (측정치 승계 전엔 depth가 소실돼 0.0으로 잘못 제외됐음 → 592. 이제 600 유지.)
    r = run_analysis(AnalysisInput(
        pnu="1111010100100000002", application_date=date(2026, 1, 1),
        drawings=[{"sheet_id": "A-AREA", "sheet_role": "AREA_TABLE",
                   "area_table": {"target": "building_area", "outer_area": 600.0},
                   "element_hints": [{"semantic_hint": "BALCONY", "hint_strength": 0.9,
                                      "area": 8.0, "depth": 2.0}]}]))
    assert r.calc_targets_source == "DRAWING_AUTO"
    assert r.legal_quantities[0].value == 600.0  # 깊이 2.0 > 1.5 → 제외 대상 아님


def test_calc_target_builder_carries_measurements():
    # INC-3: build_calc_targets_from_drawing이 length/depth/underground/accessory를 excl로 승계(미상=None).
    from app.contracts.drawing_extraction import DrawingExtraction, ExtractedElement
    from app.services.extraction.calc_target_builder import build_calc_targets_from_drawing
    ext = DrawingExtraction(
        source="HINTS",
        area_tables=[{"target": "building_area", "outer_area": 600.0}],
        elements=[ExtractedElement(element_id="e1", semantic_hint="PARKING", hint_strength=0.9,
                                   area=150.0, underground=True, accessory=True)])
    targets, _ = build_calc_targets_from_drawing(ext)
    el = targets[0]["elements"][0]
    assert el["underground"] is True and el["accessory"] is True


def test_drawing_auto_multirow_gross_floor_area():
    # INC-7: 다행(층별) 면적표 → 연면적 자동산정(각 층 바닥면적 합).
    r = run_analysis(AnalysisInput(
        pnu="1111010100100000002", application_date=date(2026, 1, 1),
        drawings=[{"sheet_id": "A-AREA", "sheet_role": "AREA_TABLE",
                   "area_table": {"target": "gross_floor_area",
                                  "rows": [{"floor": "1F", "area": 100.0},
                                           {"floor": "2F", "area": 120.0},
                                           {"floor": "3F", "area": 80.0}]}}]))
    assert r.calc_targets_source == "DRAWING_AUTO"
    gfa = r.legal_quantities[0]
    assert gfa.variable_id == "gross_floor_area" and gfa.value == 300.0


def test_area_sanity_flags_contradiction_and_ratio():
    # INC-6: 제외 area 합 > 외곽 → 모순, 단일 area/외곽 > 상한 → 환각 의심(둘 다 무음 승계 차단).
    from app.services.extraction.area_sanity import area_sanity_notes
    contradiction = area_sanity_notes(100.0, [{"area": 150.0}])
    assert any("모순" in n for n in contradiction)
    ratio = area_sanity_notes(100.0, [{"area": 95.0}])  # 0.95 > 0.9 상한
    assert any("환각 의심" in n for n in ratio)
    assert area_sanity_notes(100.0, [{"area": 30.0}]) == []  # 정상 → 무경고


def test_area_sanity_surfaced_in_pipeline():
    # 도면 자동경로의 모순 면적이 r.skipped로 표면화(무음0).
    r = run_analysis(AnalysisInput(
        pnu="1111010100100000002", application_date=date(2026, 1, 1),
        drawings=[{"sheet_id": "A-AREA", "sheet_role": "AREA_TABLE",
                   "area_table": {"target": "building_area", "outer_area": 100.0},
                   "element_hints": [{"semantic_hint": "PILOTIS", "hint_strength": 0.9, "area": 150.0}]}]))
    assert any("area_sanity" in s for s in r.skipped)


def test_calc_target_explicit_input_wins():
    # 명시 calc_targets가 있으면 도면 자동구성보다 우선(INPUT).
    r = run_analysis(AnalysisInput(
        pnu="1111010100100000002", application_date=date(2026, 1, 1),
        calc_targets=[{"target": "building_area", "payload": {"outer_area": 800.0},
                       "elements": [{"semantic_type": "PILOTIS", "area": 50.0, "confidence": 0.9}]}],
        drawings=[{"sheet_id": "A-AREA", "area_table": {"target": "building_area", "outer_area": 600.0}}]))
    assert r.calc_targets_source == "INPUT"
    assert r.legal_quantities[0].value == 750.0  # 800-50 (명시 입력)


def test_calc_target_auto_skipped_without_area_table():
    # 면적표 없으면 자동산정 불가 표면화(날조 금지).
    r = run_analysis(AnalysisInput(
        pnu="1111010100100000002", application_date=date(2026, 1, 1),
        drawings=[{"sheet_id": "A-PLAN", "element_hints": [{"semantic_hint": "PARKING", "hint_strength": 0.8}]}]))
    assert r.calc_targets_source is None
    assert r.legal_quantities == []
    assert any("calc_target_auto" in s for s in r.skipped)
