"""R1.5 — 산정 변수사전 시드. CalcTarget ↔ 변수사전 1:1(DoD). 산정값은 등록된 변수에만 바인딩.

basis_article은 근거조문(데이터). 단위는 Unit enum. 코드 내 법정 수치 없음.
"""
from __future__ import annotations

from app.contracts.canonical_vars import CanonicalVariable, VariableRegistry
from app.contracts.enums import Unit
from app.contracts.legal_quantity import CalcTarget

_DEFS: dict[CalcTarget, tuple[Unit, str, str]] = {
    CalcTarget.BUILDING_AREA: (Unit.M2, "건축면적", "건축법 시행령 제119조"),
    CalcTarget.GROSS_FLOOR_AREA: (Unit.M2, "연면적", "건축법 시행령 제119조"),
    CalcTarget.FAR_FLOOR_AREA: (Unit.M2, "용적률 산정 연면적", "건축법 시행령 제119조"),
    CalcTarget.PLOT_AREA: (Unit.M2, "대지면적", "건축법 제46조/도시계획"),
    CalcTarget.BUILDING_HEIGHT: (Unit.M_ABOVE_GROUND, "건축물 높이", "건축법 시행령 제119조"),
    CalcTarget.FLOOR_COUNT: (Unit.COUNT, "층수", "건축법 시행령 제119조"),
}


def build_calc_variable_registry() -> VariableRegistry:
    reg = VariableRegistry()
    for target, (unit, definition, article) in _DEFS.items():
        reg.register(
            CanonicalVariable(
                id=target.value,
                name=target.value,
                definition=definition,
                unit=unit,
                basis_article=article,
                required=True,
            )
        )
    return reg
