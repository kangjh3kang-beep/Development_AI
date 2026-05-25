"""금융비 산정 엔진 — 브릿지/본PF/중도금 3단계 금융비 계산.

순수 함수형 설계: DB 의존 없음.
가중평균금리 + 이자/보증료/수수료 산정.
"""

from __future__ import annotations

from typing import Any


def calculate_loan_interest(
    *,
    principal_won: int,
    annual_rate: float,
    months: int,
) -> dict[str, Any]:
    """단순 이자 계산 (원금 × 연이율 × 기간).

    Args:
        principal_won: 대출원금 (원)
        annual_rate: 연이율 (0.06 = 6%)
        months: 대출기간 (월)

    Returns:
        {'principal_won', 'annual_rate', 'months', 'interest_won'}
    """
    interest = int(principal_won * annual_rate * months / 12)
    return {
        "principal_won": principal_won,
        "annual_rate": annual_rate,
        "months": months,
        "interest_won": interest,
    }


def calculate_bridge_loan(
    *,
    amount_won: int,
    rate: float = 0.06,
    months: int = 12,
    arrangement_fee_rate: float = 0.01,
) -> dict[str, Any]:
    """브릿지론 금융비 계산.

    Returns:
        {'interest_won', 'arrangement_fee_won', 'total_bridge_cost_won'}
    """
    interest = calculate_loan_interest(
        principal_won=amount_won, annual_rate=rate, months=months
    )
    arrangement_fee = int(amount_won * arrangement_fee_rate)

    return {
        "principal_won": amount_won,
        "rate": rate,
        "months": months,
        "interest_won": interest["interest_won"],
        "arrangement_fee_won": arrangement_fee,
        "total_bridge_cost_won": interest["interest_won"] + arrangement_fee,
    }


def calculate_pf_loan(
    *,
    amount_won: int,
    rate: float = 0.045,
    months: int = 30,
    guarantee_fee_rate: float = 0.015,
) -> dict[str, Any]:
    """본PF 금융비 계산.

    Returns:
        {'interest_won', 'guarantee_fee_won', 'total_pf_cost_won'}
    """
    interest = calculate_loan_interest(
        principal_won=amount_won, annual_rate=rate, months=months
    )
    guarantee_fee = int(amount_won * guarantee_fee_rate)

    return {
        "principal_won": amount_won,
        "rate": rate,
        "months": months,
        "interest_won": interest["interest_won"],
        "guarantee_fee_won": guarantee_fee,
        "total_pf_cost_won": interest["interest_won"] + guarantee_fee,
    }


def calculate_midpay_loan(
    *,
    amount_won: int,
    rate: float = 0.04,
    months: int = 18,
) -> dict[str, Any]:
    """중도금 대출 금융비 계산.

    Returns:
        {'interest_won', 'total_midpay_cost_won'}
    """
    interest = calculate_loan_interest(
        principal_won=amount_won, annual_rate=rate, months=months
    )
    return {
        "principal_won": amount_won,
        "rate": rate,
        "months": months,
        "interest_won": interest["interest_won"],
        "total_midpay_cost_won": interest["interest_won"],
    }


def calculate_weighted_average_rate(
    loans: list[dict[str, Any]],
) -> float:
    """가중평균금리 계산.

    Args:
        loans: [{'principal_won': int, 'rate': float}, ...]

    Returns:
        가중평균금리 (소수점)
    """
    total_principal = sum(l["principal_won"] for l in loans)
    if total_principal == 0:
        return 0.0

    weighted_sum = sum(l["principal_won"] * l["rate"] for l in loans)
    return round(weighted_sum / total_principal, 6)


def calculate_total_finance_cost(
    *,
    bridge_amount_won: int = 0,
    bridge_rate: float = 0.06,
    bridge_months: int = 12,
    bridge_arrangement_fee_rate: float = 0.01,
    pf_amount_won: int = 0,
    pf_rate: float = 0.045,
    pf_months: int = 30,
    pf_guarantee_fee_rate: float = 0.015,
    midpay_amount_won: int = 0,
    midpay_rate: float = 0.04,
    midpay_months: int = 18,
) -> dict[str, Any]:
    """금융비 총합 (브릿지 + 본PF + 중도금).

    Returns:
        {'bridge', 'pf', 'midpay', 'weighted_avg_rate', 'total_finance_cost_won'}
    """
    bridge = calculate_bridge_loan(
        amount_won=bridge_amount_won,
        rate=bridge_rate,
        months=bridge_months,
        arrangement_fee_rate=bridge_arrangement_fee_rate,
    )

    pf = calculate_pf_loan(
        amount_won=pf_amount_won,
        rate=pf_rate,
        months=pf_months,
        guarantee_fee_rate=pf_guarantee_fee_rate,
    )

    midpay = calculate_midpay_loan(
        amount_won=midpay_amount_won,
        rate=midpay_rate,
        months=midpay_months,
    )

    loans = []
    if bridge_amount_won > 0:
        loans.append({"principal_won": bridge_amount_won, "rate": bridge_rate})
    if pf_amount_won > 0:
        loans.append({"principal_won": pf_amount_won, "rate": pf_rate})
    if midpay_amount_won > 0:
        loans.append({"principal_won": midpay_amount_won, "rate": midpay_rate})

    weighted_rate = calculate_weighted_average_rate(loans)

    total = (
        bridge["total_bridge_cost_won"]
        + pf["total_pf_cost_won"]
        + midpay["total_midpay_cost_won"]
    )

    return {
        "bridge": bridge,
        "pf": pf,
        "midpay": midpay,
        "weighted_avg_rate": weighted_rate,
        "total_finance_cost_won": total,
    }
