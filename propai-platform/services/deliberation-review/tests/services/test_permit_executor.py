"""INC-PD2 — 실행기·심의 계측: AnalysisResult 소비 → 단계별 부합도·검증(결정론)."""
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.services.permit.executor import run_permit_process
from app.services.permit.spec_loader import load_default_spec
from app.services.pipeline.analysis_pipeline import run_analysis

_IN = AnalysisInput(
    pnu="1111010100100000020", application_date=date(2026, 1, 1),
    rules=[{"rule": {"rule_id": "far_limit", "target_variable": "far_floor_area",
                     "basis_article": "국토계획법 시행령"}, "measured": 250.0, "limit": 200.0}],
    calc_targets=[{"target": "building_area", "payload": {"outer_area": 500.0},
                   "elements": [{"semantic_type": "EXT_WALL", "confidence": 0.9}]}],
)


def test_executor_consumes_analysis_and_scores_stages():
    result = run_analysis(_IN)
    out = run_permit_process(result, load_default_spec(), use_zone="제2종일반주거지역")
    assert out.spec_id == "permit-default" and out.spec_version == "v1"
    assert out.stages, "단계 결과 산출"
    assert out.roadmap, "로드맵(단계 순서) 산출"
    # 건축허가 단계가 존재 + 검증상태 동반
    permit = next(s for s in out.stages if s.stage_id == "building_permit")
    assert permit.verification_status in ("CONFIRMED", "NEEDS_REVIEW", "BLOCKED")
    # 측정값 있는 정량 기준은 calc_trace(설명가능성) 동반
    for s in out.stages:
        for c in s.criteria:
            if c.kind == "QUANTITATIVE" and c.measured is not None:
                assert c.calc_trace is not None


def test_executor_is_deterministic():
    r = run_analysis(_IN)
    a = run_permit_process(r, load_default_spec(), use_zone="제2종일반주거지역")
    b = run_permit_process(r, load_default_spec(), use_zone="제2종일반주거지역")
    assert a.model_dump() == b.model_dump()   # 동일 입력·스펙 → 동일 결과


def test_qualitative_low_grade_surfaces_noncompliant_e2e():
    # ★실 파이프라인 형상(한글 feature)으로 LOW 정성이 미흡으로 표면화되는지 — 침묵 HELD 강등 회귀 방지.
    inp = AnalysisInput(
        pnu="1111010100100000023", application_date=date(2026, 1, 1),
        qual_facts=[{"feature": "배치적정성", "compatibility": 0.1,
                     "candidate_rubric": "배치 적정성", "mapping_confidence": 0.99,
                     "rubric_source": "공표 심의기준"}],
    )
    result = run_analysis(inp)
    out = run_permit_process(result, load_default_spec(), use_zone="제2종일반주거지역")
    review = next(s for s in out.stages if s.stage_id == "building_review")
    layout = next(c for c in review.criteria if c.criterion_id == "layout")
    assert layout.grade == "LOW"
    assert layout.conformance == "미흡"   # 실 흐름에서 LOW가 미흡으로 표면화(침묵 HELD 아님)


def test_missing_input_surfaces_needs_input_not_silent():
    r = run_analysis(_IN)
    out = run_permit_process(r, load_default_spec(), use_zone=None)  # required_inputs 결손
    assert any(s.status in ("HELD", "NEEDS_INPUT") for s in out.stages)  # 무음 금지
    # 결손 단계는 사유 표면화
    held = next(s for s in out.stages if s.status == "NEEDS_INPUT")
    assert held.issues
