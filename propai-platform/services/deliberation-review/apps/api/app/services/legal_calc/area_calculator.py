"""R1.5 — 면적 산정(건축면적/연면적/용적률산정연면적/대지면적). 제외규정 적용 + calc_trace.

제외 임계는 CalcParamSource 주입(하드코딩 금지, INV-11). 각 제외는 calc_trace에 근거 기록(INV-10).
"""
from __future__ import annotations

from app.contracts.legal_quantity import CalcElement, CalcTraceEntry
from app.contracts.semantic_element import SemanticType
from app.services.legal_calc.calc_params import CalcParamSource

_BASIS_119 = "건축법 시행령 제119조"
# 용적률 산정 연면적에서 제외하는 요소타입(지하층/부속주차장 등).
_FAR_EXCLUDED = (SemanticType.BASEMENT, SemanticType.PARKING)
# 대지면적에서 차감하는 요소타입(건축선 후퇴분/도시계획시설 저촉분).
_PLOT_DEDUCTED = (SemanticType.BUILDING_LINE, SemanticType.PLOT_BOUNDARY)


class AreaCalculator:
    def __init__(self, params: CalcParamSource) -> None:
        self.params = params

    def building_area(
        self, outer_area: float, elements: list[CalcElement]
    ) -> tuple[float, list[CalcTraceEntry]]:
        entries = [CalcTraceEntry(rule_id="ba_base", basis_article=_BASIS_119, note="외곽 투영면적")]
        excluded = 0.0

        for el in elements:
            if el.semantic_type == SemanticType.PILOTIS:
                excluded += el.area
                entries.append(CalcTraceEntry(
                    rule_id="ba_pilotis", basis_article=_BASIS_119,
                    excluded_elements=[SemanticType.PILOTIS]))
            elif el.semantic_type == SemanticType.EAVE:
                limit_len = self.params.get("eave_exclusion_length")
                ratio = (min(el.length, limit_len) / el.length) if el.length else 0.0
                excluded += el.area * ratio
                entries.append(CalcTraceEntry(
                    rule_id="ba_eave", basis_article=_BASIS_119,
                    excluded_elements=[SemanticType.EAVE],
                    note="처마 제외길이 이내 분"))
            elif el.semantic_type == SemanticType.BALCONY:
                depth_limit = self.params.get("balcony_exclusion_depth")
                if el.depth <= depth_limit:
                    excluded += el.area
                    entries.append(CalcTraceEntry(
                        rule_id="ba_balcony", basis_article=_BASIS_119,
                        excluded_elements=[SemanticType.BALCONY],
                        note="발코니 제외 깊이 이내"))

        return outer_area - excluded, entries

    def gross_floor_area(
        self, floor_areas: list[float]
    ) -> tuple[float, list[CalcTraceEntry]]:
        entries = [CalcTraceEntry(
            rule_id="gfa_sum", basis_article=_BASIS_119, note="각 층 바닥면적 합")]
        return float(sum(floor_areas)), entries

    def far_floor_area(
        self, gross_floor_area: float, elements: list[CalcElement]
    ) -> tuple[float, list[CalcTraceEntry]]:
        entries = [CalcTraceEntry(
            rule_id="far_base", basis_article=_BASIS_119, note="연면적 기준")]
        excluded = 0.0

        for el in elements:
            if el.semantic_type in _FAR_EXCLUDED:
                excluded += el.area
                entries.append(CalcTraceEntry(
                    rule_id=f"far_{el.semantic_type.value.lower()}",
                    basis_article=_BASIS_119, excluded_elements=[el.semantic_type]))

        return gross_floor_area - excluded, entries

    def plot_area(
        self, parcel_area: float, elements: list[CalcElement]
    ) -> tuple[float, list[CalcTraceEntry]]:
        entries = [CalcTraceEntry(
            rule_id="plot_base", basis_article="건축법 제46조/도시계획", note="필지면적 기준")]
        deducted = 0.0

        for el in elements:
            if el.semantic_type in _PLOT_DEDUCTED:
                deducted += el.area
                entries.append(CalcTraceEntry(
                    rule_id="plot_deduction", basis_article="건축법 제46조/도시계획",
                    excluded_elements=[el.semantic_type],
                    note="건축선 후퇴분/도시계획시설 저촉분"))

        return parcel_area - deducted, entries
