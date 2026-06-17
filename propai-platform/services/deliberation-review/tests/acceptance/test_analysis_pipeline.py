"""심의분석 파이프라인 엔드투엔드 — 원시 입력 → 11계층 → AnalysisResult. 배선/재현성 검증."""
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.contracts.enums import RecordStatus  # noqa: F401 (계약 가용 표식)
from app.services.pipeline.analysis_pipeline import run_analysis

_INPUT = AnalysisInput(
    pnu="1111010100100000002",
    application_date=date(2026, 1, 1),
    axis_date=date(2026, 1, 1),
    drawing={"scale_text": "1:100"},
    calc_targets=[
        {"target": "building_area", "payload": {"outer_area": 600.0},
         "elements": [{"semantic_type": "PILOTIS", "area": 100.0, "confidence": 0.95}]},
    ],
    rules=[
        {"rule": {"rule_id": "far_limit", "comparator": "<=", "basis_article": "국토계획법 시행령",
                  "relaxations": [{"relaxation_id": "far_relax", "prerequisite_rule_id": "public_space"}]},
         "measured": 250.0, "limit": 200.0, "relaxation_states": {"public_space": "MET"}, "confidence": 0.9},
        {"rule": {"rule_id": "height_limit", "comparator": "<=", "basis_article": "건축법 시행령"},
         "measured": 30.0, "limit": 20.0, "confidence": 0.9},
    ],
    sim_inputs={
        "sunlight": {"latitude": 37.5, "building_height": 30.0, "adjacent_distance": 12.0, "geom_confidence": 0.9},
        "parking": {"turn_radius": 5.0, "geom_confidence": 0.9},
    },
    issue="FAR_DISPUTE",
    corpus=[{"case_id": f"c{i}", "source": f"의결서-{i}", "decision_type": "CONDITIONAL",
             "issue_labels": ["FAR_DISPUTE"], "conditions": ["공개공지 확대"]} for i in range(8)],
    mirror_rules=[{"ref": "건축법 시행령", "effective_date": "2025-01-01"}],
    citations=[{"ref": "건축법 시행령"}],
    qual_facts=[{"feature": "경관조화", "candidate_rubric": "경관 심의기준 3.1",
                 "mapping_confidence": 0.9, "compatibility": 0.8, "criterion_exists": True}],
)


def test_pipeline_runs_all_layers():
    r = run_analysis(_INPUT)
    assert r.preflight is not None
    assert len(r.legal_quantities) == 1
    assert len(r.findings) == 2
    assert r.sim_metrics  # sunlight + parking
    assert r.precedent and r.precedent.distribution
    assert r.qualitative
    assert r.report.items
    assert r.input_hash


def test_pipeline_far_relaxation_not_false_fail():
    # 완화 전제 충족(MET) → far는 NON_COMPLIANT 아님(거짓 불합격 금지).
    r = run_analysis(_INPUT)
    far = next(f for f in r.findings if f.rule_id == "far_limit")
    assert far.verdict.value != "NON_COMPLIANT"


def test_pipeline_reproducible():
    assert run_analysis(_INPUT) == run_analysis(_INPUT)


def test_pipeline_surfaces_skips():
    minimal = AnalysisInput(pnu="1111010100100000002", application_date=date(2026, 1, 1),
                            drawing={"scale_text": "1:100"})
    r = run_analysis(minimal)
    # 미제공 계층은 무음 아님 — skipped로 표면화.
    assert any("legal_calc" in s for s in r.skipped)
    assert any("judge" in s for s in r.skipped)
    assert r.report is not None


def _dual_path_input(declared: float):
    # building_area 산정 = 600 - 100(필로티) = 500. declared와 대조(L5 이중경로).
    return AnalysisInput(
        pnu="1111010100100000002", application_date=date(2026, 1, 1), axis_date=date(2026, 1, 1),
        drawing={"scale_text": "1:100"},
        calc_targets=[
            {"target": "building_area", "payload": {"outer_area": 600.0},
             "elements": [{"semantic_type": "PILOTIS", "area": 100.0, "confidence": 0.95}],
             "declared": declared},
        ],
        rules=[
            {"rule": {"rule_id": "ba_rule", "comparator": "<=", "target_variable": "building_area",
                      "basis_article": "건축법 시행령"},
             "measured": 500.0, "limit": 1000.0, "confidence": 0.95},
        ],
        citations=[{"ref": "건축법 시행령"}],
        mirror_rules=[{"ref": "건축법 시행령", "effective_date": "2025-01-01"}],
    )


def test_pipeline_dual_path_mismatch_flags_needs_review():
    # 명기(600) vs 산정(500) 불일치(>area_tol) → dual_path HELD → finding NEEDS_REVIEW + 사유 표면화.
    r = run_analysis(_dual_path_input(declared=600.0))
    item = r.report.find("ba_rule")
    dp = item.evidence["dual_path"]
    assert dp is not None and dp["status"] == "HELD"
    assert dp["table_value"] == 600.0 and dp["geom_value"] == 500.0
    assert item.status.value == "NEEDS_REVIEW"
    assert "dual_path_HELD" in (item.evidence["gate_reason"] or "")


def test_pipeline_dual_path_match_agreed():
    # 명기(500)=산정(500) → dual_path AGREED(불일치 강등 없음).
    r = run_analysis(_dual_path_input(declared=500.0))
    item = r.report.find("ba_rule")
    dp = item.evidence["dual_path"]
    assert dp is not None and dp["status"] == "AGREED"
    assert "dual_path_HELD" not in (item.evidence["gate_reason"] or "")
