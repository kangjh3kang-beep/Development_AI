"""AT-4/AT-5 — calc_trace 없는 산정값 출력 금지 + 분류 불확실 시 HELD. + 변수사전 1:1."""
import pytest

from app.contracts.enums import RecordStatus
from app.contracts.legal_quantity import (
    CalcElement,
    CalcTarget,
    LegalQuantity,
    emit,
)
from app.contracts.semantic_element import SemanticType
from app.core.errors import CalcTraceMissing, RuleContractError
from app.services.legal_calc.calc_engine import CalcEngine
from app.services.legal_calc.variable_seed import build_calc_variable_registry


def test_no_quantity_without_trace():
    q = LegalQuantity(variable_id="building_area", value=500.0, calc_trace=None)
    with pytest.raises(CalcTraceMissing):
        emit(q)


def test_uncertain_classification_holds_quantity():
    q = CalcEngine().compute(
        target=CalcTarget.BUILDING_AREA,
        payload={"outer_area": 600.0},
        elements=[CalcElement(semantic_type=SemanticType.UNKNOWN, area=50.0, confidence=0.3)],
    )
    assert q.status == RecordStatus.HELD  # 무음 계산 금지


def test_calc_target_binds_to_variable_registry():
    reg = build_calc_variable_registry()
    # 모든 CalcTarget이 변수사전에 1:1 등록(DoD).
    for target in CalcTarget:
        assert reg.is_registered(target.value)
    # 미등록 변수로는 산정 불가.
    engine = CalcEngine(registry=reg)
    q = engine.compute(
        target=CalcTarget.BUILDING_AREA,
        payload={"outer_area": 600.0},
        elements=[CalcElement(semantic_type=SemanticType.PILOTIS, area=100.0, confidence=0.9)],
    )
    assert q.variable_id == "building_area"


def test_registry_rejects_unknown_variable():
    from app.contracts.canonical_vars import VariableRegistry

    engine = CalcEngine(registry=VariableRegistry())  # 빈 사전
    with pytest.raises(RuleContractError):
        engine.compute(
            target=CalcTarget.BUILDING_AREA,
            payload={"outer_area": 600.0},
            elements=[],
        )
