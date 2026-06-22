"""INC-5b — 2D 슈레이스 면적 적분: 결정론·방향무관 + 폴리곤→실척 산정 체인(축척 결합)."""
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.services.extraction.geometry_area import polygon_real_area, shoelace_area
from app.services.pipeline.analysis_pipeline import run_analysis


def test_shoelace_square():
    sq = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert shoelace_area(sq) == 100.0
    assert shoelace_area(list(reversed(sq))) == 100.0  # 시계/반시계 무관
    assert shoelace_area(sq) == shoelace_area(sq)       # 결정론


def test_shoelace_degenerate():
    assert shoelace_area([[0, 0], [1, 1]]) == 0.0  # 점 3개 미만 → 0


def test_polygon_real_area_with_scale():
    # 도면단위 면적 2 × 100² = 20000 실척.
    assert polygon_real_area([[0, 0], [2, 0], [2, 1], [0, 1]], 100.0) == 20000.0


def test_polygon_to_real_area_via_pipeline():
    # INC-5b+INC-4: polygon(도면좌표) → 슈레이스 area_px → 축척 실척 환산 → 산정 승계.
    r = run_analysis(AnalysisInput(
        pnu="1111010100100000002", application_date=date(2026, 1, 1),
        drawing={"scale_text": "1:100"},
        drawings=[{"sheet_id": "A", "sheet_role": "AREA_TABLE",
                   "area_table": {"target": "building_area", "outer_area": 30000.0},
                   "element_hints": [{"semantic_hint": "PILOTIS", "hint_strength": 0.9,
                                      "polygon": [[0, 0], [2, 0], [2, 1], [0, 1]]}]}]))
    # area_px=2 → ×100²=20000 실척(필로티 제외) → 건축면적 30000-20000=10000.
    assert r.legal_quantities[0].value == 10000.0
