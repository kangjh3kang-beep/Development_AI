"""C07 기반시설부담금 부담구역 게이트 회귀가드.

국토계획법 §67~69: 기반시설부담금은 '기반시설부담구역'으로 지정된 지역에서만 부과된다.
종전 구현은 게이트 없이 전 프로젝트에 연면적×15,000원을 무조건 부과해, 부담구역 아닌
대다수 사업지의 총사업비를 구조적으로 과대계상했다. 이 테스트가 게이트 재발을 막는다.
"""
from __future__ import annotations

from app.services.tax.sale_stage_engine import (
    calculate_all_sale_stage,
    calculate_c07_infrastructure_charge,
)


def test_c07_not_in_zone_is_zero():
    """★기본(부담구역 미지정)이면 0 — 과대계상 방지."""
    r = calculate_c07_infrastructure_charge(total_gfa_sqm=50_000)
    assert r["amount_won"] == 0
    assert "미지정" in r["detail"]["reason"]


def test_c07_in_zone_uses_standard_cost_x_rate():
    """부담구역 지정 시: 표준시설비용 × 부담률 × 연면적."""
    r = calculate_c07_infrastructure_charge(total_gfa_sqm=50_000, in_infra_charge_zone=True)
    assert r["rate"] == round(82_000 * 0.20)  # 16,400원/㎡
    assert r["amount_won"] == 50_000 * round(82_000 * 0.20)


def test_sale_stage_default_excludes_infra_charge():
    """분양단계 일괄 계산 기본값: C07=0 (부담구역 미지정 기본)."""
    stage = calculate_all_sale_stage(
        total_sale_amount_won=100_000_000_000, total_units=500, total_gfa_sqm=50_000
    )
    c07 = next(i for i in stage["items"] if i["code"] == "C07")
    assert c07["amount_won"] == 0


def test_sale_stage_applies_infra_charge_when_in_zone():
    """in_infra_charge_zone=True 전달 시에만 부과."""
    stage = calculate_all_sale_stage(
        total_sale_amount_won=100_000_000_000, total_units=500,
        total_gfa_sqm=50_000, in_infra_charge_zone=True,
    )
    c07 = next(i for i in stage["items"] if i["code"] == "C07")
    assert c07["amount_won"] > 0
