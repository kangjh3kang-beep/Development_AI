"""EX-P2A — 결과예측 휴리스틱: 등급 매핑·근거/한계 동반·정밀확률 없음·종합 우선순위·실행기 e2e."""
import re
from datetime import date
from types import SimpleNamespace

from app.contracts.analysis import AnalysisInput
from app.services.permit.executor import run_process
from app.services.permit.spec_loader import load_default_spec
from app.services.pipeline.analysis_pipeline import run_analysis
from app.services.predict.outcome import overall_outcome, predict_stage


def _stage(status="DONE", conformance="부합", verification="CONFIRMED"):
    return SimpleNamespace(status=status, conformance=conformance, verification_status=verification)


def test_likelihood_mapping_deterministic():
    assert predict_stage(_stage("DONE", "부합", "CONFIRMED")).likelihood == "높음"
    assert predict_stage(_stage("DONE", "미흡", "NEEDS_REVIEW")).likelihood == "낮음"
    assert predict_stage(_stage("DONE", "부합", "BLOCKED")).likelihood == "낮음"
    assert predict_stage(_stage("DONE", "조건부", "NEEDS_REVIEW")).likelihood == "보통"
    assert predict_stage(_stage("NEEDS_INPUT", "HELD", "NEEDS_REVIEW")).likelihood == "미상"
    # ★DONE이라도 conformance=HELD(측정 불가 보류)는 미상 — 보통으로 세탁 금지(무음 금지 회귀 방지)
    assert predict_stage(_stage("DONE", "HELD", "CONFIRMED")).likelihood == "미상"
    assert predict_stage(_stage("DONE", "HELD", "NEEDS_REVIEW")).likelihood == "미상"


def test_prediction_carries_rationale_caveat_no_precise_probability():
    p = predict_stage(_stage("DONE", "미흡", "NEEDS_REVIEW"))
    assert p.rationale and p.basis and p.caveat            # 근거·투입신호·한계 동반(설명가능성)
    assert "모델 아님" in p.caveat                          # 통계/학습모델 아님 명시
    # 정밀 확률(%) 날조 금지 — 등급 문자열만, 숫자 % 없음
    dump = p.model_dump_json()
    assert "%" not in dump and not re.search(r"\d+(\.\d+)?\s*(퍼센트|percent)", dump)


def test_overall_outcome_conservative_precedence():
    assert overall_outcome(["높음", "낮음", "보통"]) == "낮음"   # 낮음 우선(보수)
    assert overall_outcome(["높음", "미상"]) == "미상"
    assert overall_outcome(["높음", "보통"]) == "보통"
    assert overall_outcome(["높음"]) == "높음"
    assert overall_outcome([]) == "미상"


def test_executor_attaches_outcome_only_on_predictor_stages():
    inp = AnalysisInput(
        pnu="1111010100100000050", application_date=date(2026, 1, 1),
        rules=[{"rule": {"rule_id": "far_limit", "target_variable": "far_floor_area",
                         "basis_article": "국토계획법 시행령"}, "measured": 250.0, "limit": 200.0}],
    )
    out = run_process(run_analysis(inp), load_default_spec(), use_zone="제2종일반주거지역")
    by_id = {s.stage_id: s for s in out.stages}
    permit = by_id["building_permit"]
    assert permit.outcome is not None                            # outcome_predictor 설정 단계
    # building_permit 유일 기준 height는 미측정→conformance HELD → 미상(보통 세탁 방지·실파이프라인 회귀)
    assert permit.conformance == "HELD" and permit.outcome.likelihood == "미상"
    assert by_id["building_review"].outcome is None              # 미설정 단계는 예측 없음
    assert out.overall_outcome == "미상"                          # 미상 단계 포함 → 종합 미상(무음 금지)
