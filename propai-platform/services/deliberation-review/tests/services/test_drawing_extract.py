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
