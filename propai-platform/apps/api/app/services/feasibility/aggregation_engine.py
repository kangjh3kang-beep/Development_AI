"""수지 합산 엔진 — 총수입/총사업비/순이익/등급 판정.

순수 함수형 설계: DB 의존 없음.
참조값: 오산 M04 수익률 19.1%, ROI 23.6%
"""

from __future__ import annotations

from typing import Any


# 등급 기준 (수익률 %)
GRADE_THRESHOLDS: list[tuple[float, str]] = [
    (20.0, "A"),   # 20% 이상
    (15.0, "B"),   # 15% 이상
    (10.0, "C"),   # 10% 이상
    (5.0, "D"),    # 5% 이상
    (0.0, "E"),    # 0% 이상 (손익분기)
    (-999.0, "F"), # 0% 미만 (적자)
]


def determine_grade(profit_rate_pct: float) -> str:
    """수익률 기반 등급 판정 (A~F).

    Args:
        profit_rate_pct: 수익률 (%, 19.1 = 19.1%)

    Returns:
        'A'~'F' 등급
    """
    for threshold, grade in GRADE_THRESHOLDS:
        if profit_rate_pct >= threshold:
            return grade
    return "F"


def aggregate_feasibility(
    *,
    total_revenue_won: int,
    total_land_cost_won: int = 0,
    total_construction_cost_won: int = 0,
    total_finance_cost_won: int = 0,
    total_other_cost_won: int = 0,
    total_tax_cost_won: int = 0,
    equity_won: int = 0,
    discount_rate: float = 0.08,
    project_months: int = 48,
) -> dict[str, Any]:
    """수지분석 합산 + KPI 산출.

    Args:
        total_revenue_won: 총수입 (원)
        total_land_cost_won: 토지비
        total_construction_cost_won: 공사비
        total_finance_cost_won: 금융비
        total_other_cost_won: 기타경비
        total_tax_cost_won: 제세공과금
        equity_won: 자기자본 (ROI 계산용, 0이면 총사업비로 대체)
        discount_rate: 할인율 (NPV 계산용)
        project_months: 사업기간 (월)

    Returns:
        {'total_revenue_won', 'total_cost_won', 'net_profit_won',
         'profit_rate_pct', 'roi_pct', 'npv_won', 'grade',
         'cost_breakdown_won', 'cost_breakdown_pct'}
    """
    total_cost = (
        total_land_cost_won
        + total_construction_cost_won
        + total_finance_cost_won
        + total_other_cost_won
        + total_tax_cost_won
    )

    net_profit = total_revenue_won - total_cost

    # 수익률 = 순이익 / 총수입 × 100
    profit_rate = (net_profit / total_revenue_won * 100) if total_revenue_won > 0 else 0.0

    # ROI = 순이익 / 투입자본 × 100 (자기자본 없으면 총사업비 사용)
    invest_base = equity_won if equity_won > 0 else total_cost
    roi = (net_profit / invest_base * 100) if invest_base > 0 else 0.0

    # 단순 NPV (단일 기간, 사업 종료 시 현금흐름 발생 가정)
    years = project_months / 12
    npv = int(net_profit / ((1 + discount_rate) ** years)) if years > 0 else net_profit

    grade = determine_grade(profit_rate)

    # 비용 구조 분석
    cost_breakdown = {
        "land": total_land_cost_won,
        "construction": total_construction_cost_won,
        "finance": total_finance_cost_won,
        "other": total_other_cost_won,
        "tax": total_tax_cost_won,
    }
    cost_pct = {}
    for key, val in cost_breakdown.items():
        cost_pct[key] = round(val / total_cost * 100, 2) if total_cost > 0 else 0.0

    return {
        "total_revenue_won": total_revenue_won,
        "total_cost_won": total_cost,
        "net_profit_won": net_profit,
        "profit_rate_pct": round(profit_rate, 2),
        "roi_pct": round(roi, 2),
        "npv_won": npv,
        "grade": grade,
        "cost_breakdown_won": cost_breakdown,
        "cost_breakdown_pct": cost_pct,
    }


def compare_scenarios(
    scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    """여러 시나리오 비교 분석.

    Args:
        scenarios: [{'name': str, ...aggregate_feasibility 결과...}, ...]

    Returns:
        {'scenarios', 'best_profit', 'best_roi', 'ranking'}
    """
    if not scenarios:
        return {"scenarios": [], "best_profit": None, "best_roi": None, "ranking": []}

    # 수익률 기준 정렬
    sorted_by_profit = sorted(scenarios, key=lambda s: s.get("profit_rate_pct", 0), reverse=True)

    ranking = []
    for i, s in enumerate(sorted_by_profit):
        ranking.append({
            "rank": i + 1,
            "name": s.get("name", f"시나리오 {i+1}"),
            "profit_rate_pct": s.get("profit_rate_pct", 0),
            "roi_pct": s.get("roi_pct", 0),
            "grade": s.get("grade", "F"),
        })

    return {
        "scenarios": scenarios,
        "best_profit": sorted_by_profit[0] if sorted_by_profit else None,
        "best_roi": max(scenarios, key=lambda s: s.get("roi_pct", 0)),
        "ranking": ranking,
    }
