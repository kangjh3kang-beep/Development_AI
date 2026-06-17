"""코드리뷰 — FiniteFloat: 측정치 nan/inf 거부(nan<=limit False로 무음 COMPLIANT 오판 차단)."""
import pytest
from pydantic import ValidationError

from app.contracts.rule import Rule
from app.contracts.sim_metric import SimMetric
from app.services.judge.evaluator import EvalCase


def test_eval_case_rejects_nan_inf():
    with pytest.raises(ValidationError):
        EvalCase(rule=Rule(rule_id="x"), measured_value=float("nan"), limit_value=10.0)
    with pytest.raises(ValidationError):
        EvalCase(rule=Rule(rule_id="x"), measured_value=5.0, limit_value=float("inf"))
    # 정상 유한값은 허용.
    assert EvalCase(rule=Rule(rule_id="x"), measured_value=5.0, limit_value=10.0).measured_value == 5.0


def test_sim_metric_rejects_inf():
    with pytest.raises(ValidationError):
        SimMetric(metric_id="m", value=float("inf"))
