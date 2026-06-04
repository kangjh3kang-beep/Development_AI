"""양도단계 세금 엔진 — D01~D06 (6종).

D01: 양도소득세 (개인)
D02: 법인세 추가세 (법인 주택)
D03: 지방소득세
D04: 장기보유특별공제
D05: 재건축 초과이익환수 (M02)
D06: 종합부동산세 (보유 기간)
"""

from __future__ import annotations

from typing import Any

from app.services.tax.regional_tax_data import (
    CAPITAL_GAINS_BRACKETS,
    LTDC_RATES_RESIDENTIAL,
    LTDC_MAX_RESIDENTIAL,
    LTDC_MAX_NON_RESIDENTIAL,
    CORP_ADDON_RATE_RESIDENTIAL,
)


def calculate_d01_capital_gains_tax(
    *,
    gain_10k_won: float,
    holding_years: int = 0,
    is_residential: bool = True,
) -> dict[str, Any]:
    """D01 양도소득세 (누진세율).

    Args:
        gain_10k_won: 양도차익 (만원)
        holding_years: 보유기간 (년)
        is_residential: 주거용 여부 (장기보유특별공제 적용)
    """
    # 장기보유특별공제
    deduction_rate = 0.0
    if is_residential and holding_years >= 3:
        deduction_rate = LTDC_RATES_RESIDENTIAL.get(min(holding_years, 15), 0.0)
        deduction_rate = min(deduction_rate, LTDC_MAX_RESIDENTIAL)
    elif not is_residential and holding_years >= 3:
        deduction_rate = min(holding_years * 0.02, LTDC_MAX_NON_RESIDENTIAL)

    taxable = gain_10k_won * (1 - deduction_rate)

    # 누진세율 적용
    tax_10k = 0.0
    applied_rate = 0.0
    for threshold, rate, deduction in CAPITAL_GAINS_BRACKETS:
        if taxable >= threshold:
            applied_rate = rate
            tax_10k = taxable * rate - deduction

    amount_won = int(tax_10k * 10_000)

    return {
        "code": "D01", "name": "양도소득세",
        "base_won": int(gain_10k_won * 10_000),
        "rate": applied_rate,
        "amount_won": amount_won,
        "detail": {
            "gain_10k": gain_10k_won,
            "deduction_rate": deduction_rate,
            "taxable_10k": round(taxable, 2),
            "applied_bracket_rate": applied_rate,
        },
    }


def calculate_d02_corp_addon_tax(
    *,
    gain_won: int,
    is_residential: bool = True,
) -> dict[str, Any]:
    """D02 법인세 추가세 (법인 주택 양도, 오류#8 is_residential 파라미터 추가)."""
    if not is_residential:
        return {
            "code": "D02", "name": "법인세 추가세",
            "base_won": 0, "rate": 0,
            "amount_won": 0,
            "detail": {"reason": "비주거용 면제"},
        }
    amount = int(gain_won * CORP_ADDON_RATE_RESIDENTIAL)
    return {
        "code": "D02", "name": "법인세 추가세",
        "base_won": gain_won, "rate": CORP_ADDON_RATE_RESIDENTIAL,
        "amount_won": amount,
    }


def calculate_d03_local_income_tax(
    *,
    capital_gains_tax_won: int,
    rate: float = 0.10,
) -> dict[str, Any]:
    """D03 지방소득세 (양도소득세의 10%)."""
    amount = int(capital_gains_tax_won * rate)
    return {
        "code": "D03", "name": "지방소득세",
        "base_won": capital_gains_tax_won, "rate": rate,
        "amount_won": amount,
    }


def calculate_d04_ltdc(
    *,
    gain_won: int,
    holding_years: int,
    is_residential: bool = True,
) -> dict[str, Any]:
    """D04 장기보유특별공제 (음수: 절감액)."""
    deduction_rate = 0.0
    if is_residential and holding_years >= 3:
        deduction_rate = LTDC_RATES_RESIDENTIAL.get(min(holding_years, 15), 0.0)
        deduction_rate = min(deduction_rate, LTDC_MAX_RESIDENTIAL)
    elif not is_residential and holding_years >= 3:
        deduction_rate = min(holding_years * 0.02, LTDC_MAX_NON_RESIDENTIAL)

    reduction = int(gain_won * deduction_rate)
    return {
        "code": "D04", "name": "장기보유특별공제",
        "base_won": gain_won, "rate": deduction_rate,
        "amount_won": -reduction,  # 음수 = 절감
    }


def calculate_d05_reconstruction_levy(
    *,
    excess_gain_won: int,
) -> dict[str, Any]:
    """D05 재건축 초과이익환수 — 5구간 누진 (오류#6 단위통일).

    구간:
    0~3000만원: 면제
    3000만~5000만: 10%
    5000만~1억: 20%
    1억~1.5억: 30%
    1.5억~: 40%
    최대 50%
    """
    excess_10k = excess_gain_won / 10_000  # 만원 단위

    if excess_10k <= 3_000:
        levy = 0
    elif excess_10k <= 5_000:
        levy = int((excess_10k - 3_000) * 0.10 * 10_000)
    elif excess_10k <= 10_000:
        levy = int(((5_000 - 3_000) * 0.10 + (excess_10k - 5_000) * 0.20) * 10_000)
    elif excess_10k <= 15_000:
        levy = int(((5_000 - 3_000) * 0.10 + (10_000 - 5_000) * 0.20 + (excess_10k - 10_000) * 0.30) * 10_000)
    else:
        levy = int((
            (5_000 - 3_000) * 0.10
            + (10_000 - 5_000) * 0.20
            + (15_000 - 10_000) * 0.30
            + (excess_10k - 15_000) * 0.40
        ) * 10_000)
        # 최대 50% cap
        levy = min(levy, int(excess_gain_won * 0.50))

    return {
        "code": "D05", "name": "재건축 초과이익환수",
        "base_won": excess_gain_won,
        "rate": None,
        "amount_won": levy,
    }


def calculate_d06_comprehensive_property_tax(
    *,
    assessed_value_won: int,
    holding_years: int = 1,
    deduction_won: int | None = None,
    fair_market_ratio: float | None = None,
) -> dict[str, Any]:
    """D06 종합부동산세 (보유 기간 합산) — 종합합산 토지 누진세율+공제 적용.

    (이전: 전체가액×flat 0.5%·공제無 → 구조적 과대계상. 교정: 공제 5억·공정시장가액·
     누진 1/2/3% → 공제 이하 토지는 0원으로 정확.)
    """
    from app.services.tax.regional_tax_data import (
        calc_land_comprehensive_property_tax,
        LAND_COMPREHENSIVE_DEDUCTION_WON,
        LAND_FAIR_MARKET_RATIO,
    )

    r = calc_land_comprehensive_property_tax(
        assessed_value_won,
        deduction_won=deduction_won if deduction_won is not None else LAND_COMPREHENSIVE_DEDUCTION_WON,
        fair_market_ratio=fair_market_ratio if fair_market_ratio is not None else LAND_FAIR_MARKET_RATIO,
        holding_years=holding_years,
    )
    return {
        "code": "D06", "name": "종합부동산세",
        "base_won": r["taxable_won"], "rate": r["rate"],
        "amount_won": r["total_won"],
        "detail": {
            "annual_won": r["annual_won"], "holding_years": holding_years,
            "deduction_won": r["deduction_won"], "fair_market_ratio": r["fair_market_ratio"],
            "note": "종합합산 토지(나대지) 기준. 주택건설사업용 토지는 종부세 비과세 특례 적용 가능(별도).",
        },
    }


def calculate_all_disposal_stage(
    *,
    gain_10k_won: float = 0,
    gain_won: int = 0,
    holding_years: int = 0,
    is_residential: bool = True,
    is_corporate: bool = False,
    excess_gain_won: int = 0,
    assessed_value_won: int = 0,
) -> dict[str, Any]:
    """D01~D06 양도단계 전체 일괄 계산.

    Returns:
        {'items': [...], 'total_won': int, 'applicable_count': int}
    """
    items = []

    # D01 양도소득세
    d01 = calculate_d01_capital_gains_tax(
        gain_10k_won=gain_10k_won, holding_years=holding_years, is_residential=is_residential
    )
    items.append(d01)

    # D02 법인 추가세 (법인만)
    if is_corporate:
        items.append(calculate_d02_corp_addon_tax(gain_won=gain_won, is_residential=is_residential))

    # D03 지방소득세
    items.append(calculate_d03_local_income_tax(capital_gains_tax_won=d01["amount_won"]))

    # D04 장기보유특별공제
    if holding_years >= 3:
        items.append(calculate_d04_ltdc(
            gain_won=gain_won, holding_years=holding_years, is_residential=is_residential
        ))

    # D05 재건축 초과이익
    if excess_gain_won > 0:
        items.append(calculate_d05_reconstruction_levy(excess_gain_won=excess_gain_won))

    # D06 종합부동산세
    if assessed_value_won > 0:
        items.append(calculate_d06_comprehensive_property_tax(
            assessed_value_won=assessed_value_won, holding_years=holding_years
        ))

    total = sum(it["amount_won"] for it in items)
    return {
        "stage": "disposal",
        "items": items,
        "total_won": total,
        "applicable_count": len(items),
    }
