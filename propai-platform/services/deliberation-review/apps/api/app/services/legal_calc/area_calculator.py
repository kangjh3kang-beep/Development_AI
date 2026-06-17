"""R1.5 — 면적 산정(건축면적/연면적/용적률산정연면적/대지면적). 제외규정 적용 + calc_trace.

제외 임계는 CalcParamSource 주입(하드코딩 금지, INV-11). 각 제외는 calc_trace에 근거 기록(INV-10).
"""
from __future__ import annotations

from enum import Enum

from app.contracts.legal_quantity import CalcElement, CalcTraceEntry
from app.contracts.semantic_element import SemanticType
from app.services.legal_calc.calc_params import CalcParamSource

_BASIS_119 = "건축법 시행령 제119조"
# 대지면적에서 차감하는 요소타입(건축선 후퇴분/도시계획시설 저촉분).
_PLOT_DEDUCTED = (SemanticType.BUILDING_LINE, SemanticType.PLOT_BOUNDARY)


class ParkingFarEligibility(str, Enum):
    """주차의 용적률 산정 연면적 제외 적격성(시행령 §119①4: 지하 AND 부속만 제외)."""

    ELIGIBLE = "ELIGIBLE"      # 지하 AND 부속 → 제외 대상
    INELIGIBLE = "INELIGIBLE"  # 지상 또는 비부속(독립) → 산입 대상
    UNKNOWN = "UNKNOWN"        # 미상 → 무음 전량제외 금지(거짓적합 방지), HELD


def parking_far_eligibility(el: CalcElement) -> ParkingFarEligibility:
    """주차 요소의 §119①4 제외 적격성. 지하·부속 둘 다 확정돼야 제외, 하나라도 부정이면 산입, 미상은 UNKNOWN."""
    if el.underground is True and el.accessory is True:
        return ParkingFarEligibility.ELIGIBLE
    if el.underground is False or el.accessory is False:
        return ParkingFarEligibility.INELIGIBLE
    return ParkingFarEligibility.UNKNOWN


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
                    excluded_elements=[SemanticType.PILOTIS],
                    excluded_amount=round(el.area, 2), note="필로티(개방) 건축면적 제외"))
            elif el.semantic_type == SemanticType.EAVE:
                em = self.params.meta("eave_exclusion_length")
                limit_len = em["value"]
                ratio = (min(el.length, limit_len) / el.length) if el.length else 0.0
                exc = el.area * ratio
                excluded += exc
                entries.append(CalcTraceEntry(
                    rule_id="ba_eave", basis_article=em.get("basis_article", _BASIS_119),
                    excluded_elements=[SemanticType.EAVE],
                    threshold=limit_len, threshold_unit=em.get("unit"),
                    measured=el.length, excluded_amount=round(exc, 2),
                    note=f"처마 제외길이 {min(el.length, limit_len)}m/{el.length}m({em.get('description', '')})"))
            elif el.semantic_type == SemanticType.BALCONY:
                bm = self.params.meta("balcony_exclusion_depth")
                depth_limit = bm["value"]
                if el.depth <= depth_limit:
                    excluded += el.area
                    entries.append(CalcTraceEntry(
                        rule_id="ba_balcony", basis_article=bm.get("basis_article", _BASIS_119),
                        excluded_elements=[SemanticType.BALCONY],
                        threshold=depth_limit, threshold_unit=bm.get("unit"),
                        measured=el.depth, excluded_amount=round(el.area, 2),
                        note=f"발코니 깊이 {el.depth}m ≤ 기준 {depth_limit}m({bm.get('description', '')})"))

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
            if el.semantic_type == SemanticType.BASEMENT:
                excluded += el.area
                entries.append(CalcTraceEntry(
                    rule_id="far_basement", basis_article=_BASIS_119,
                    excluded_elements=[SemanticType.BASEMENT],
                    excluded_amount=round(el.area, 2), note="지하층 용적률 산정 연면적 제외"))
            elif el.semantic_type == SemanticType.PARKING:
                # 시행령 §119①4 주차 제외는 '지하 AND 부속'만 — 지상·독립은 산입, 미상은 무음제외 금지(HELD).
                elig = parking_far_eligibility(el)
                if elig is ParkingFarEligibility.ELIGIBLE:
                    excluded += el.area
                    entries.append(CalcTraceEntry(
                        rule_id="far_parking", basis_article=_BASIS_119,
                        excluded_elements=[SemanticType.PARKING],
                        excluded_amount=round(el.area, 2),
                        note="지하·부속 주차 용적률 산정 제외(시행령 §119①4)"))
                elif elig is ParkingFarEligibility.INELIGIBLE:
                    entries.append(CalcTraceEntry(
                        rule_id="far_parking_included", basis_article=_BASIS_119,
                        note="지상·비부속(독립) 주차는 §119①4 제외 대상 아님 — 용적률 산정 연면적 산입"))
                else:  # UNKNOWN — 지하/부속 여부 미확인
                    entries.append(CalcTraceEntry(
                        rule_id="far_parking_held", basis_article=_BASIS_119,
                        note="⚠️ 주차 제외 적격성 미상(지하/부속 여부 미확인) — 무음 전량제외 금지(FAR 과소·거짓적합 "
                             "방지), 보수적 산입 후 확인 필요(HELD)"))

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
                    excluded_elements=[el.semantic_type], excluded_amount=round(el.area, 2),
                    note="건축선 후퇴분/도시계획시설 저촉분 차감"))

        return parcel_area - deducted, entries
