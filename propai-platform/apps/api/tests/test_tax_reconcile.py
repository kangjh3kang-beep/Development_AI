"""Fix #4(감사 HIGH): 세금-수지 정합 — 과세표준·이중계상·세후 반영 검증."""
from app.services.pipeline.tax_reconcile import (
    compute_project_taxes,
    grade_for_profit_rate,
)

# 공통 시나리오: 토지 10억, 건물 20억, 총사업비 40억(소프트코스트 포함), 매출 50억, 세전이익 10억.
BASE = dict(
    total_revenue=5_000_000_000,
    total_project_cost=4_000_000_000,
    net_profit_pretax=1_000_000_000,
    land_cost=1_000_000_000,
    construction_cost=2_000_000_000,
)


def test_acquisition_base_is_acquisition_cost_not_total():
    r = compute_project_taxes(**BASE)
    # 과세표준 = 취득가액(토지10억+건물20억=30억) → ×4.6% = 1.38억. (총사업비 40억×4.6%=1.84억 아님)
    assert r["acquisition_base"] == 3_000_000_000
    assert abs(r["acquisition_tax"] - 138_000_000) < 1


def test_no_double_count_of_land_levies():
    r = compute_project_taxes(**BASE)
    # 사업비에 이미 포함된 토지 취득세 = 10억×4.6% = 0.46억
    assert abs(r["acquisition_tax_in_cost"] - 46_000_000) < 1
    # 추가 취득세 = 1.38억 − 0.46억 = 0.92억 (이중계상 제거)
    assert abs(r["acquisition_tax_additional"] - 92_000_000) < 1


def test_after_tax_profit_and_grade_reflect_tax():
    r = compute_project_taxes(**BASE)
    # 일회성 세부담 = 추가취득 0.92억 + 양도세(10억×22%=2.2억) = 3.12억 → 세후이익 = 6.88억
    assert abs(r["net_profit_after_tax"] - 688_000_000) < 1
    # 세전 이익률 25%(A) → 세후 6.88/40 = 17.2%(B). 세금이 등급에 반영됨.
    assert r["grade_after_tax"] == "B"


def test_grade_thresholds_match_pipeline():
    assert grade_for_profit_rate(20) == "A"
    assert grade_for_profit_rate(10) == "B"
    assert grade_for_profit_rate(0) == "C"
    assert grade_for_profit_rate(-1) == "D"


def test_zero_cost_safe():
    r = compute_project_taxes(
        total_revenue=0, total_project_cost=0, net_profit_pretax=0,
        land_cost=0, construction_cost=0,
    )
    assert r["acquisition_tax"] == 0
    assert r["profit_rate_after_tax_pct"] == 0
