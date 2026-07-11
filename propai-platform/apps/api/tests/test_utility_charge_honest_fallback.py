"""B03/B04 상하수도 원인자부담금 무목업 폴백 회귀가드.

수도법 §71·하수도법 §61은 원인자부담금 산정을 지자체 조례에 위임 → 전국 단일 표준값이 없다.
종전엔 조례 미등록 지역에 임의 폴백값(120,000원/세대)을 지어내 계상했다(무목업 위반).
이 테스트가 '미등록 → 0 + confidence=unavailable' 정직 처리를 고정한다.
"""
from __future__ import annotations

from app.services.tax.regional_tax_data import WATER_SUPPLY_CHARGES_WON, get_utility_charge
from app.services.tax.utility_stage_engine import (
    calculate_b03_water_supply,
    calculate_b04_sewage,
)


def test_get_utility_charge_returns_none_for_unregistered():
    """★조례 미등록 지역 → None (임의 전국폴백 120,000 제거)."""
    assert get_utility_charge(WATER_SUPPLY_CHARGES_WON, "강원", "정선군") is None


def test_b03_b04_unavailable_when_no_ordinance():
    """미등록 지역: amount=0 + rate=None + confidence=unavailable (날조 금지)."""
    for fn in (calculate_b03_water_supply, calculate_b04_sewage):
        r = fn(sido_name="강원", sigungu_name="정선군", total_households=300)
        assert r["amount_won"] == 0
        assert r["rate"] is None
        assert r["detail"]["confidence"] == "unavailable"
        assert "조례 확인 필요" in r["detail"]["reason"]


def test_b03_registered_region_charges_normally():
    """등록 지역(서울)은 정상 부과 + confidence=regional (무회귀)."""
    r = calculate_b03_water_supply(sido_name="서울", sigungu_name="강남구", total_households=300)
    assert r["amount_won"] > 0
    assert r["detail"]["confidence"] == "regional"
