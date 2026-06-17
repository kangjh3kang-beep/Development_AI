"""R1.5 — 산정 오케스트레이션(CalcEngine). PreflightContext + SemanticElement[] → LegalQuantity[].

INV-10: 모든 출력은 calc_trace 동반(emit 강제). INV-11: 임계 파라미터 주입. INV-12: 입력 분류
confidence 상속, 불확실/UNKNOWN → status=HELD(무음 계산 금지). 변수사전 registry로 변수 1:1 검증.
"""
from __future__ import annotations

from datetime import date

from app.contracts.canonical_vars import VariableRegistry
from app.contracts.calc_rule import CalcRuleSet
from app.contracts.enums import RecordStatus, Unit
from app.contracts.legal_quantity import (
    CalcElement,
    CalcTarget,
    CalcTrace,
    LegalQuantity,
    emit,
)
from app.contracts.semantic_element import SemanticType
from app.contracts.versioning import Snapshot
from app.core.errors import RuleContractError
from app.core.parameters import param
from app.services.legal_calc.area_calculator import AreaCalculator
from app.services.legal_calc.calc_params import CalcParamSource
from app.services.legal_calc.height_floor_calc import HeightFloorCalc

_UNIT = {
    CalcTarget.BUILDING_AREA: Unit.M2,
    CalcTarget.GROSS_FLOOR_AREA: Unit.M2,
    CalcTarget.FAR_FLOOR_AREA: Unit.M2,
    CalcTarget.PLOT_AREA: Unit.M2,
    CalcTarget.BUILDING_HEIGHT: Unit.M_ABOVE_GROUND,
    CalcTarget.FLOOR_COUNT: Unit.COUNT,
}


class CalcEngine:
    def __init__(
        self,
        params: dict | None = None,
        rule_set: CalcRuleSet | None = None,
        base_date: date | None = None,
        registry: VariableRegistry | None = None,
    ) -> None:
        self.base_date = base_date
        self.registry = registry
        self.calc_rule_version: str | None = None

        rule_params: dict | None = None
        if rule_set is not None and base_date is not None:
            effective = rule_set.effective_on(base_date)
            rule_params = effective.params
            self.calc_rule_version = effective.version

        self.param_source = CalcParamSource(overrides=params, base=rule_params)
        self.area = AreaCalculator(self.param_source)
        self.height = HeightFloorCalc(self.param_source)

    def compute(
        self,
        target: CalcTarget,
        payload: dict | None = None,
        elements: list[CalcElement] | None = None,
        snapshot: Snapshot | None = None,
    ) -> LegalQuantity:
        payload = payload or {}
        elements = elements or []

        if snapshot is not None:
            snapshot.assert_synced()  # INV-6: 버전축 불일치 스냅샷은 산정 진입 거부.

        if self.registry is not None:
            self.registry.lookup(target.value)  # 변수사전 1:1 (미등록 → RuleContractError)

        # INV-12: 분류 confidence 상속 + 불확실/UNKNOWN → HELD.
        min_conf = min((e.confidence for e in elements), default=1.0)
        has_unknown = any(e.semantic_type == SemanticType.UNKNOWN for e in elements)
        held = has_unknown or min_conf < float(param("calc_min_input_confidence"))

        value, entries = self._dispatch(target, payload, elements)

        status = RecordStatus.HELD if held else RecordStatus.AGREED
        q = LegalQuantity(
            variable_id=target.value,
            value=value,
            unit=_UNIT[target],
            status=status,
            confidence=min_conf,
            calc_trace=CalcTrace(entries=entries),
            calc_rule_version=self.calc_rule_version,
            snapshot_id=snapshot.snapshot_id if snapshot else None,
        )
        return emit(q)

    def _dispatch(self, target, payload, elements):
        if target == CalcTarget.BUILDING_AREA:
            return self.area.building_area(payload["outer_area"], elements)
        if target == CalcTarget.GROSS_FLOOR_AREA:
            return self.area.gross_floor_area(payload["floor_areas"])
        if target == CalcTarget.FAR_FLOOR_AREA:
            return self.area.far_floor_area(payload["gross_floor_area"], elements)
        if target == CalcTarget.PLOT_AREA:
            return self.area.plot_area(payload["parcel_area"], elements)
        if target == CalcTarget.BUILDING_HEIGHT:
            return self.height.building_height(
                payload["raw_height"], payload.get("rooftop_area", 0.0),
                payload.get("building_area"))
        if target == CalcTarget.FLOOR_COUNT:
            return self.height.floor_count(
                payload["above_ground_floors"], payload.get("rooftop_area", 0.0),
                payload.get("building_area"))
        raise RuleContractError(f"unsupported calc target: {target}")
