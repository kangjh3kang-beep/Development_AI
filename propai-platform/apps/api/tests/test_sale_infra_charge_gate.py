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


def test_c07_not_surveyed_is_zero_but_says_so():
    """★★**미조회**와 **미지정**은 다르다(2026-08-26).

    인자를 안 주면 우리는 **구역 지정 여부를 모른다.** 종전 구현은 그 상태에서
    *"기반시설부담구역 **미지정**"* 이라는 **관측 주장**을 화면에 냈다 — 그런데 이 값을
    실제로 넘기는 곳은 **한 군데도 없었다**(프론트 출현 0건 · 대조군 `total_gfa_sqm` 33건).
    즉 **전 사업이 「미조회」인데 「미지정」으로 표기**됐다.
    ★증거 규율 §1 — 미측정을 관측처럼 쓰지 않는다.

    금액은 그대로 0(안전측). 바뀌는 것은 **무엇을 아는지에 대한 주장**이다.
    """
    r = calculate_c07_infrastructure_charge(total_gfa_sqm=50_000)
    assert r["amount_won"] == 0, "안전측 0 은 유지된다(값을 바꾸는 커밋이 아니다)"
    assert r["detail"]["surveyed"] is False
    assert "미조회" in r["detail"]["reason"], "미조회를 미지정이라 단정했다"
    assert r.get("confidence") == "unavailable", "확정이 아님을 하류가 알 수 없다"


def test_c07_surveyed_not_in_zone_is_a_different_claim():
    """★**조회했고 해당 없음**은 확정이다 — 미조회와 같은 문장을 쓰면 안 된다(두 모집단)."""
    surveyed = calculate_c07_infrastructure_charge(
        total_gfa_sqm=50_000, in_infra_charge_zone=False)
    unknown = calculate_c07_infrastructure_charge(total_gfa_sqm=50_000)
    assert surveyed["amount_won"] == unknown["amount_won"] == 0
    # ★두 상태가 **다른 말**을 해야 한다. 같으면 세 상태 분기를 지워도 통과한다.
    assert surveyed["detail"]["reason"] != unknown["detail"]["reason"]
    assert surveyed["detail"]["surveyed"] is True
    assert "미지정" in surveyed["detail"]["reason"]
    assert "confidence" not in surveyed, "확정인데 강등 표기가 붙었다"


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
