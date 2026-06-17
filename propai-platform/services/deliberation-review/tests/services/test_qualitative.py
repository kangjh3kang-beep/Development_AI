"""AT-1..7 — 정성 평가: 인용접지 강제, 기준 미존재→재량, 저신뢰→보류, 재현성,
등급만(법적 단정 금지), 새 사실 금지, 임계 파라미터화."""
import pathlib

import pytest

from app.contracts.qualitative import QualAssessment, QualStatus, emit
from app.core.errors import CitationRequired
from app.core.parameters import param
from app.services.qualitative.evidence_collector import EXISTING_LAYERS, EvidenceCollector
from app.services.qualitative.qual_evaluator import QualEvaluator
from app.services.qualitative.rubric_grounding import RubricGrounding
from tools.static_scan import scan_for_numeric_legal_constants

_QUAL_DIR = (
    pathlib.Path(__file__).resolve().parents[2]
    / "apps" / "api" / "app" / "services" / "qualitative"
)

FACT = {"feature": "경관조화", "candidate_rubric": "경관 심의기준 3.1",
        "mapping_confidence": 0.9, "compatibility": 0.8, "criterion_exists": True}
FACT_WITHOUT_CRITERION = {"feature": "신규유형", "criterion_exists": False}
LOW_CONF_FACT = {"feature": "배치적정성", "candidate_rubric": "배치 기준 2.2",
                 "mapping_confidence": 0.3, "criterion_exists": True}
PROJECT = {
    "semantic_elements": [{"element_id": "e1", "semantic_type": "BALCONY"}],
    "legal_quantities": [{"variable_id": "building_area", "value": 500}],
    "sim_metrics": [{"metric_id": "continuous_sunlight_hours", "value": 3.2}],
}


def test_qualitative_requires_citation():
    with pytest.raises(CitationRequired):
        emit(QualAssessment(item="x", status=QualStatus.GRADED, citation=None))


def test_no_criterion_yields_discretion():
    a = QualEvaluator().evaluate(FACT_WITHOUT_CRITERION)
    assert a.status == QualStatus.DISCRETION_HELD


def test_low_mapping_confidence_holds():
    g = RubricGrounding(threshold=param("mapping_confidence_threshold")).ground(LOW_CONF_FACT)
    assert g.status == QualStatus.HELD


def test_qualitative_reproducible():
    a = QualEvaluator().evaluate(FACT, snapshot="snap-1", model="qual-model-v1")
    b = QualEvaluator().evaluate(FACT, snapshot="snap-1", model="qual-model-v1")
    assert a == b


def test_no_rule_assertion_only_grade():
    a = QualEvaluator().evaluate(FACT)
    assert a.is_grade is True
    assert a.asserts_legal_verdict is False


def test_criterion_without_rubric_holds_not_empty_citation():
    # criterion_exists지만 인용할 루브릭 미매핑 → HELD(빈 인용 등급화 금지, INV-31).
    fact = {"feature": "공공성", "candidate_rubric": "", "mapping_confidence": 0.9, "criterion_exists": True}
    a = QualEvaluator().evaluate(fact)
    assert a.status == QualStatus.HELD


def test_no_new_fact_generation():
    facts = EvidenceCollector().collect(PROJECT)
    assert facts
    assert all(f.source_layer in EXISTING_LAYERS for f in facts)


def test_mapping_threshold_parameterized():
    offenders = {}
    for py in _QUAL_DIR.rglob("*.py"):
        hits = scan_for_numeric_legal_constants(py.read_text(encoding="utf-8"))
        if hits:
            offenders[py.name] = hits
    assert offenders == {}
