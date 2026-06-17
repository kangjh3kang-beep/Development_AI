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
    CalcTraceEntry,
    LegalQuantity,
    emit,
)
from app.contracts.semantic_element import SemanticType
from app.contracts.versioning import Snapshot
from app.core.errors import RuleContractError
from app.core.parameters import param
from app.services.legal_calc.area_calculator import (
    AreaCalculator,
    ParkingFarEligibility,
    parking_far_eligibility,
)
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
        threshold = float(param("calc_min_input_confidence"))
        # HELD 사유를 누적 — status=HELD만으로 '왜 HELD인지' 식별 못 하던 갭 해소(설명가능성).
        held_reasons: list[str] = []
        if has_unknown:
            held_reasons.append("입력 요소에 UNKNOWN(의미 미분류) 포함")
        if min_conf < threshold:
            held_reasons.append(f"입력 분류 신뢰도 {round(min_conf, 2)} < 임계 {threshold}")
        # 용적률 산정 시 주차 제외 적격성 미상(지하/부속 미확인) → HELD(전량제외 무음 거짓적합 방지).
        if target == CalcTarget.FAR_FLOOR_AREA and any(
            e.semantic_type == SemanticType.PARKING
            and parking_far_eligibility(e) is ParkingFarEligibility.UNKNOWN
            for e in elements
        ):
            held_reasons.append("주차 제외 적격성 미상(지하/부속 미확인)")
        held = bool(held_reasons)

        value, entries = self._dispatch(target, payload, elements)
        if held_reasons:  # 강등 사유를 calc_trace에 명시(무라벨 HELD 제거).
            entries.append(CalcTraceEntry(
                rule_id="held_reason", basis_article="INV-12(분류 confidence 상속·불확실→HELD)",
                note="HELD 강등 사유 — " + "; ".join(held_reasons)))

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

    _REQUIRED = {
        CalcTarget.BUILDING_AREA: ("outer_area",),
        CalcTarget.GROSS_FLOOR_AREA: ("floor_areas",),
        CalcTarget.FAR_FLOOR_AREA: ("gross_floor_area",),
        CalcTarget.PLOT_AREA: ("parcel_area",),
        CalcTarget.BUILDING_HEIGHT: ("raw_height",),
        CalcTarget.FLOOR_COUNT: ("above_ground_floors",),
    }

    def _dispatch(self, target, payload, elements):
        # 필수 페이로드 키 검증 — 결손 시 무음 KeyError(→500 붕괴) 대신 RuleContractError(→422 DomainError).
        for key in self._REQUIRED.get(target, ()):
            if key not in payload:
                raise RuleContractError(f"calc target {target.value} requires payload['{key}'] (결손)")
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
