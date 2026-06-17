"""AT-1 — 미정의 변수 참조 룰 등록 거부 + 단위 enum 강제."""
import pytest

from app.contracts.canonical_vars import CanonicalVariable, VariableRegistry
from app.contracts.enums import Method, Unit
from app.core.errors import RuleContractError


def test_undefined_variable_rule_rejected():
    reg = VariableRegistry()
    with pytest.raises(RuleContractError):
        reg.bind_rule(refs=["nonexistent_var"])


def test_registered_variable_binds_ok():
    reg = VariableRegistry()
    reg.register(
        CanonicalVariable(
            id="building_area",
            name="building_area",
            definition="건축면적",
            unit=Unit.M2,
            allowed_sources=[Method.TABLE, Method.VECTOR],
        )
    )
    assert reg.lookup("building_area").unit == Unit.M2
    assert reg.bind_rule(refs=["building_area"]) is True


def test_undefined_unit_rejected():
    with pytest.raises(Exception):
        CanonicalVariable(id="x", name="x", unit="furlong")
