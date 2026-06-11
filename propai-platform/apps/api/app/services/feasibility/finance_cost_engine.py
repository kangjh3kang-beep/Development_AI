"""금융비 산정 엔진 — 브릿지/본PF/중도금 3단계 금융비 계산.

순수 함수형 설계: DB 의존 없음.
가중평균금리 + 이자/보증료/수수료 산정.
"""

from __future__ import annotations

from typing import Any


def calculate_balloon_interest(principal: int, annual_rate: float, months: int) -> int:
    """만기일시상환 이자 계산 (월 복리 기준).

    Args:
        principal: 대출원금 (원)
        annual_rate: 연이율 (0.06 = 6%)
        months: 대출기간 (월)

    Returns:
        총 이자 (원)
    """
    monthly_rate = annual_rate / 12
    total_interest = int(principal * ((1 + monthly_rate) ** months - 1))
    return total_interest


def calculate_drawdown_interest(principal: int, annual_rate: float, months: int) -> int:
    """분할실행(progressive drawdown) 이자 계산.

    PF 기성불 인출·중도금 회차별 실행처럼 원금이 기간에 걸쳐 균등 분할
    실행되는 대출의 이자. 각 월별 트랜치가 만기까지 복리 부리:
        총이자 = Σ_{k=1..m} (P/m) × ((1+i)^(m−k+1) − 1)
    전액·전기간 가정 대비 약 절반 수준 — 실제 PF 관행에 부합.
    """
    if months <= 0 or principal <= 0:
        return 0
    monthly_rate = annual_rate / 12
    tranche = principal / months
    total = sum(
        tranche * ((1 + monthly_rate) ** (months - k + 1) - 1)
        for k in range(1, months + 1)
    )
    return int(total)


def get_pf_rate(credit_grade: str = "A", presale_ratio: float = 0.0) -> float:
    """신용등급 및 분양률 기반 PF 금리 결정.

    Args:
        credit_grade: 신용등급 ('AAA', 'AA', 'A', 'BBB', 'BB')
        presale_ratio: 분양률 (0.0~1.0)

    Returns:
        PF 금리 (소수점)
    """
    base_rates = {"AAA": 0.038, "AA": 0.042, "A": 0.048, "BBB": 0.055, "BB": 0.065}
    rate = base_rates.get(credit_grade, 0.055)
    if presale_ratio >= 0.9:
        rate -= 0.002  # 분양률 90%+ 할인
    elif presale_ratio < 0.7:
        rate += 0.005  # 분양률 70% 미만 가산
    return rate


def calculate_loan_interest(
    *,
    principal_won: int,
    annual_rate: float,
    months: int,
) -> dict[str, Any]:
    """복리 이자 계산 (만기일시상환 기준).

    Args:
        principal_won: 대출원금 (원)
        annual_rate: 연이율 (0.06 = 6%)
        months: 대출기간 (월)

    Returns:
        {'principal_won', 'annual_rate', 'months', 'interest_won'}
    """
    interest = calculate_balloon_interest(principal_won, annual_rate, months)
    return {
        "principal_won": principal_won,
        "annual_rate": annual_rate,
        "months": months,
        "interest_won": interest,
    }


def calculate_bridge_loan(
    *,
    amount_won: int,
    rate: float = 0.05,
    months: int = 12,
    arrangement_fee_rate: float = 0.01,
    loan_start_month: int = 0,
    loan_end_month: int | None = None,
) -> dict[str, Any]:
    """브릿지론 금융비 계산.

    Args:
        amount_won: 대출원금 (원)
        rate: 연이율 (기본 5%, 2025 시장 기준)
        months: 대출기간 (월)
        arrangement_fee_rate: 주선수수료율
        loan_start_month: 대출 시작 월 (사업 타임라인 기준)
        loan_end_month: 대출 종료 월 (None이면 start + months)

    Returns:
        {'interest_won', 'arrangement_fee_won', 'total_bridge_cost_won'}
    """
    if loan_end_month is not None:
        months = max(1, loan_end_month - loan_start_month)

    interest = calculate_loan_interest(
        principal_won=amount_won, annual_rate=rate, months=months
    )
    arrangement_fee = int(amount_won * arrangement_fee_rate)

    return {
        "principal_won": amount_won,
        "rate": rate,
        "months": months,
        "loan_start_month": loan_start_month,
        "loan_end_month": loan_start_month + months,
        "interest_won": interest["interest_won"],
        "arrangement_fee_won": arrangement_fee,
        "total_bridge_cost_won": interest["interest_won"] + arrangement_fee,
    }


def calculate_pf_loan(
    *,
    amount_won: int,
    rate: float | None = None,
    months: int = 30,
    guarantee_fee_rate: float = 0.015,
    credit_grade: str = "A",
    presale_ratio: float = 0.0,
    loan_start_month: int = 0,
    loan_end_month: int | None = None,
) -> dict[str, Any]:
    """본PF 금융비 계산.

    Args:
        amount_won: 대출원금 (원)
        rate: 연이율 (None이면 get_pf_rate()로 동적 결정)
        months: 대출기간 (월)
        guarantee_fee_rate: 보증수수료율
        credit_grade: 신용등급 (PF 금리 결정용)
        presale_ratio: 분양률 (PF 금리 결정용)
        loan_start_month: 대출 시작 월
        loan_end_month: 대출 종료 월

    Returns:
        {'interest_won', 'guarantee_fee_won', 'total_pf_cost_won'}
    """
    if rate is None:
        rate = get_pf_rate(credit_grade, presale_ratio)

    if loan_end_month is not None:
        months = max(1, loan_end_month - loan_start_month)

    interest = calculate_loan_interest(
        principal_won=amount_won, annual_rate=rate, months=months
    )
    guarantee_fee = int(amount_won * guarantee_fee_rate)

    return {
        "principal_won": amount_won,
        "rate": rate,
        "months": months,
        "credit_grade": credit_grade,
        "presale_ratio": presale_ratio,
        "loan_start_month": loan_start_month,
        "loan_end_month": loan_start_month + months,
        "interest_won": interest["interest_won"],
        "guarantee_fee_won": guarantee_fee,
        "total_pf_cost_won": interest["interest_won"] + guarantee_fee,
    }


def calculate_midpay_loan(
    *,
    amount_won: int,
    rate: float = 0.04,
    months: int = 18,
    guarantee_fee_rate: float = 0.004,
    loan_start_month: int = 0,
    loan_end_month: int | None = None,
) -> dict[str, Any]:
    """중도금 대출 금융비 계산.

    Args:
        amount_won: 대출원금 (원)
        rate: 연이율 (기본 4%)
        months: 대출기간 (월)
        guarantee_fee_rate: 중도금 보증수수료율 (기본 0.4%)
        loan_start_month: 대출 시작 월
        loan_end_month: 대출 종료 월

    Returns:
        {'interest_won', 'guarantee_fee_won', 'total_midpay_cost_won'}
    """
    if loan_end_month is not None:
        months = max(1, loan_end_month - loan_start_month)

    interest = calculate_loan_interest(
        principal_won=amount_won, annual_rate=rate, months=months
    )
    guarantee_fee = int(amount_won * guarantee_fee_rate)

    return {
        "principal_won": amount_won,
        "rate": rate,
        "months": months,
        "loan_start_month": loan_start_month,
        "loan_end_month": loan_start_month + months,
        "interest_won": interest["interest_won"],
        "guarantee_fee_won": guarantee_fee,
        "total_midpay_cost_won": interest["interest_won"] + guarantee_fee,
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
    bridge_rate: float = 0.05,
    bridge_months: int = 12,
    bridge_arrangement_fee_rate: float = 0.01,
    bridge_start_month: int = 0,
    bridge_end_month: int | None = None,
    pf_amount_won: int = 0,
    pf_rate: float | None = None,
    pf_months: int = 30,
    pf_guarantee_fee_rate: float = 0.015,
    pf_credit_grade: str = "A",
    pf_presale_ratio: float = 0.0,
    pf_start_month: int = 0,
    pf_end_month: int | None = None,
    midpay_amount_won: int = 0,
    midpay_rate: float = 0.04,
    midpay_months: int = 18,
    midpay_guarantee_fee_rate: float = 0.004,
    midpay_start_month: int = 0,
    midpay_end_month: int | None = None,
    progressive_drawdown: bool = True,
) -> dict[str, Any]:
    """금융비 총합 (브릿지 + 본PF + 중도금).

    progressive_drawdown=True(기본)면 PF·중도금 이자를 분할실행 모델로 계산한다
    (PF는 기성불 인출, 중도금은 회차별 실행 — 전액·전기간 가정은 ~2배 과대계상).
    브릿지는 토지비 일시 실행이므로 항상 전액 기준.

    Returns:
        {'bridge', 'pf', 'midpay', 'weighted_avg_rate', 'total_finance_cost_won'}
    """
    bridge = calculate_bridge_loan(
        amount_won=bridge_amount_won,
        rate=bridge_rate,
        months=bridge_months,
        arrangement_fee_rate=bridge_arrangement_fee_rate,
        loan_start_month=bridge_start_month,
        loan_end_month=bridge_end_month,
    )

    pf = calculate_pf_loan(
        amount_won=pf_amount_won,
        rate=pf_rate,
        months=pf_months,
        guarantee_fee_rate=pf_guarantee_fee_rate,
        credit_grade=pf_credit_grade,
        presale_ratio=pf_presale_ratio,
        loan_start_month=pf_start_month,
        loan_end_month=pf_end_month,
    )

    midpay = calculate_midpay_loan(
        amount_won=midpay_amount_won,
        rate=midpay_rate,
        months=midpay_months,
        guarantee_fee_rate=midpay_guarantee_fee_rate,
        loan_start_month=midpay_start_month,
        loan_end_month=midpay_end_month,
    )

    # 분할실행 모델: PF(기성불)·중도금(회차별)은 평균잔액이 원금의 ~50%
    # — 전액·전기간 복리 이자를 분할실행 이자로 교체 (브릿지는 일시 실행 유지)
    if progressive_drawdown:
        pf_dd_interest = calculate_drawdown_interest(
            pf_amount_won, pf["rate"], pf["months"]
        )
        pf["interest_won"] = pf_dd_interest
        pf["disbursement"] = "progressive"
        pf["total_pf_cost_won"] = pf_dd_interest + pf["guarantee_fee_won"]

        mid_dd_interest = calculate_drawdown_interest(
            midpay_amount_won, midpay_rate, midpay["months"]
        )
        midpay["interest_won"] = mid_dd_interest
        midpay["disbursement"] = "progressive"
        midpay["total_midpay_cost_won"] = mid_dd_interest + midpay["guarantee_fee_won"]

    # 실제 적용된 PF 금리 (동적 결정된 경우 포함)
    actual_pf_rate = pf["rate"]

    loans = []
    if bridge_amount_won > 0:
        loans.append({"principal_won": bridge_amount_won, "rate": bridge_rate})
    if pf_amount_won > 0:
        loans.append({"principal_won": pf_amount_won, "rate": actual_pf_rate})
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
