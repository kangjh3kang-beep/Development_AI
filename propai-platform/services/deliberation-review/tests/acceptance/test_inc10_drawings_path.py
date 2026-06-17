"""INC-10 특성화 — drawings(힌트+면적표) 자동경로 출력 동일성 잠금(리팩터 전후 불변).

추출 오케스트레이터 리팩터(인라인 0a/P-A.2/0b → orchestrate_extraction)가 도면 자동경로의
산출(소스/요소수/calc_targets/산정값/skipped)을 byte 동일하게 보존하는지 회귀로 고정한다(INV-1).
"""
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.services.pipeline.analysis_pipeline import run_analysis

_DRAW_INPUT = AnalysisInput(
    pnu="1111010100100000002",
    application_date=date(2026, 1, 1), axis_date=date(2026, 1, 1),
    drawing={"scale_text": "1:100"},
    drawings=[{
        "sheet_id": "A-01", "sheet_role": "PLAN",
        "element_hints": [
            {"semantic_hint": "PILOTIS", "hint_strength": 0.9, "area": 100.0},
            {"semantic_hint": "BALCONY", "hint_strength": 0.8, "area": 20.0, "depth": 1.2},
        ],
        "area_table": {"target": "building_area", "outer_area": 600.0},
    }],
    rules=[{"rule": {"rule_id": "ba_rule", "comparator": "<=", "target_variable": "building_area",
                     "basis_article": "건축법 시행령"},
            "measured": 500.0, "limit": 1000.0, "confidence": 0.95}],
    citations=[{"ref": "건축법 시행령"}],
    mirror_rules=[{"ref": "건축법 시행령", "effective_date": "2025-01-01"}],
)


def test_drawings_auto_path_fields():
    # 도면 힌트 → HINTS 경로, 2 요소, 면적표 → DRAWING_AUTO calc_target, 이중경로 VLLM.
    r = run_analysis(_DRAW_INPUT)
    assert r.drawing_source == "HINTS"
    assert r.drawing_elements_n == 2
    assert r.calc_targets_source == "DRAWING_AUTO"
    assert r.extraction_source == "VLLM"
    # 건축면적 = 외곽 600 - 필로티 100 - 발코니 20 = 480(제외 측정치 승계).
    assert [(lq.variable_id, lq.value) for lq in r.legal_quantities] == [("building_area", 480.0)]
    assert [f.rule_id for f in r.findings] == ["ba_rule"]
    # 추출 경로 클린(면적표 sanity 미위반·source!=none) → 추출 관련 skipped 항목 없음(무음0과 별개).
    assert not [s for s in r.skipped
                if s.startswith(("drawing_extract", "calc_target_auto", "extraction:"))]


def test_drawings_auto_path_reproducible():
    # 결정론 — 동일 입력 동일 결과(trace 포함 완전 동치).
    assert run_analysis(_DRAW_INPUT) == run_analysis(_DRAW_INPUT)
