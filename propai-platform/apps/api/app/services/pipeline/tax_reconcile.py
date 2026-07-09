"""Fix #4(감사 HIGH): 세금-수지 정합.

배경(감사): _run_tax가 ① 취득세를 '총사업비' 기준(소프트코스트·금융·예비비 포함)으로 과대 과세하고
② 토지 취득세가 이미 사업비 levies(land×4.6%)로 계상됐는데 다시 4.6%를 적용해 이중계상하며
③ 세금을 net_profit/grade(헤드라인 ROI)에 반영하지 않아 세전/세후가 혼재했다.

이 모듈은 그 세 결함을 순수 함수로 바로잡는다: 과세표준을 취득가액(토지+건물)으로 좁히고,
이미 사업비에 포함된 토지 취득세를 차감(이중계상 제거)하며, 세후 이익·등급을 산출한다.
무외부 의존(테스트 용이).
"""
from __future__ import annotations

# ★세율 SSOT: 토지 취득세율(제세공과 산정 기준) 단일출처.
#   project_pipeline(제세공과 levies)와 compute_project_taxes(acquisition_rate 기본값)가 공유한다.
LAND_ACQUISITION_RATE = 0.046


def grade_for_profit_rate(profit_rate_pct: float) -> str:
    """사업이익률(%) → 등급(A≥20, B≥10, C≥0, D). project_pipeline 기존 기준과 동일."""
    if profit_rate_pct >= 20:
        return "A"
    if profit_rate_pct >= 10:
        return "B"
    if profit_rate_pct >= 0:
        return "C"
    return "D"


def compute_project_taxes(
    *,
    total_revenue: float,
    total_project_cost: float,
    net_profit_pretax: float,
    land_cost: float,
    construction_cost: float,
    levies_in_cost: float | None = None,
    acquisition_rate: float = LAND_ACQUISITION_RATE,
    property_rate: float = 0.004,
    transfer_rate: float = 0.22,
    vat_rate: float = 0.1,
) -> dict:
    """프로젝트 세금 + 세후 손익 산출(무목업·정합).

    - acquisition_tax: 취득세 = 취득가액(토지+건물)×율. ★총사업비 아님(과세표준 정정).
    - acquisition_tax_in_cost: 사업비에 이미 포함된 토지 취득세(levies). 미전달 시 land×율로 산정.
    - acquisition_tax_additional: 추가 취득세 = acquisition_tax − levies(이중계상 제거).
    - net_profit_after_tax / profit_rate_after_tax_pct / grade_after_tax: 일회성 세부담
      (추가 취득세 + 양도세)을 반영한 세후 손익(보유세·VAT는 손익 외 별도 성격).
    """
    land = max(0.0, float(land_cost or 0))
    construction = max(0.0, float(construction_cost or 0))
    tpc = max(0.0, float(total_project_cost or 0))
    rev = max(0.0, float(total_revenue or 0))
    npt = float(net_profit_pretax or 0)
    levies = float(levies_in_cost) if levies_in_cost is not None else land * acquisition_rate

    acquisition_base = land + construction
    acquisition_tax = acquisition_base * acquisition_rate
    acquisition_tax_additional = max(0.0, acquisition_tax - max(0.0, levies))
    property_tax_annual = tpc * property_rate  # 보유세(연간) — 일회성 아님
    transfer_tax = max(0.0, npt) * transfer_rate  # 양도소득세(이익 발생 시)
    vat = rev * vat_rate

    one_time_tax = acquisition_tax_additional + transfer_tax
    net_profit_after_tax = npt - one_time_tax
    profit_rate_after_tax = (net_profit_after_tax / tpc * 100) if tpc > 0 else 0.0

    total_tax = acquisition_tax_additional + property_tax_annual + transfer_tax
    return {
        "acquisition_tax": acquisition_tax,
        "acquisition_tax_in_cost": levies,
        "acquisition_tax_additional": acquisition_tax_additional,
        "acquisition_base": acquisition_base,
        "property_tax_annual": property_tax_annual,
        "transfer_tax": transfer_tax,
        "vat": vat,
        "total_tax": total_tax,
        "net_profit_after_tax": net_profit_after_tax,
        "profit_rate_after_tax_pct": round(profit_rate_after_tax, 2),
        "grade_after_tax": grade_for_profit_rate(profit_rate_after_tax),
    }
