"""R1.5 — 높이/층수 산정(지표면 기준, 옥탑 산정규칙). 임계는 파라미터 주입.

옥탑이 건축면적 대비 제외 비율 이하면 높이/층수 산정에서 제외(calc_trace 기록).
"""
from __future__ import annotations

from app.contracts.legal_quantity import CalcTraceEntry
from app.services.legal_calc.calc_params import CalcParamSource

_BASIS_119 = "건축법 시행령 제119조"


class HeightFloorCalc:
    def __init__(self, params: CalcParamSource) -> None:
        self.params = params

    def building_height(
        self,
        raw_height: float,
        rooftop_area: float = 0.0,
        building_area: float | None = None,
    ) -> tuple[float, list[CalcTraceEntry]]:
        entries = [CalcTraceEntry(
            rule_id="height_base", basis_article=_BASIS_119, note="지표면 기준 높이")]

        if building_area and rooftop_area:
            rm = self.params.meta("rooftop_height_exclusion_ratio")
            ratio_limit = rm["value"]
            ratio = rooftop_area / building_area
            if ratio <= ratio_limit:
                entries.append(CalcTraceEntry(
                    rule_id="height_rooftop_excluded",
                    basis_article=rm.get("basis_article", _BASIS_119),
                    threshold=ratio_limit, threshold_unit=rm.get("unit"), measured=round(ratio, 3),
                    note=f"옥탑 면적비 {round(ratio, 3)} ≤ 기준 {ratio_limit}({rm.get('description', '')}) → 높이 산정 제외"))
            else:  # 비율 초과 → 산입(왜 산입했는지 명시 — far_parking_included 대칭)
                entries.append(CalcTraceEntry(
                    rule_id="height_rooftop_included",
                    basis_article=rm.get("basis_article", _BASIS_119),
                    threshold=ratio_limit, threshold_unit=rm.get("unit"), measured=round(ratio, 3),
                    note=f"옥탑 면적비 {round(ratio, 3)} > 기준 {ratio_limit} → 높이 산정 산입(제외 대상 아님)"))
        elif rooftop_area:  # 옥탑 있으나 건축면적 결손 → 제외비율 판정 불가
            entries.append(CalcTraceEntry(
                rule_id="height_rooftop_unknown", basis_article=_BASIS_119,
                note="옥탑 존재하나 건축면적 결손 — 제외 비율 판정 불가, 보수적 산입(HELD 검토 필요)"))

        return raw_height, entries

    def floor_count(
        self,
        above_ground_floors: int,
        rooftop_area: float = 0.0,
        building_area: float | None = None,
    ) -> tuple[int, list[CalcTraceEntry]]:
        entries = [CalcTraceEntry(
            rule_id="floor_base", basis_article=_BASIS_119, note="지상 층수")]

        if building_area and rooftop_area:
            rm = self.params.meta("rooftop_height_exclusion_ratio")
            ratio_limit = rm["value"]
            ratio = rooftop_area / building_area
            if ratio <= ratio_limit:
                entries.append(CalcTraceEntry(
                    rule_id="floor_rooftop_excluded",
                    basis_article=rm.get("basis_article", _BASIS_119),
                    threshold=ratio_limit, threshold_unit=rm.get("unit"), measured=round(ratio, 3),
                    note=f"옥탑 면적비 {round(ratio, 3)} ≤ 기준 {ratio_limit} → 층수 산정 제외"))
            else:  # 비율 초과 → 산입
                entries.append(CalcTraceEntry(
                    rule_id="floor_rooftop_included",
                    basis_article=rm.get("basis_article", _BASIS_119),
                    threshold=ratio_limit, threshold_unit=rm.get("unit"), measured=round(ratio, 3),
                    note=f"옥탑 면적비 {round(ratio, 3)} > 기준 {ratio_limit} → 층수 산정 산입(제외 대상 아님)"))
        elif rooftop_area:  # 옥탑 있으나 건축면적 결손 → 제외비율 판정 불가
            entries.append(CalcTraceEntry(
                rule_id="floor_rooftop_unknown", basis_article=_BASIS_119,
                note="옥탑 존재하나 건축면적 결손 — 제외 비율 판정 불가, 보수적 산입(HELD 검토 필요)"))

        return above_ground_floors, entries
