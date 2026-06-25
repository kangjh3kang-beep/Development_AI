"""시니어 세무사 정량 평가기 — 부동산 취득세(본세) 산출.

tax_advisor 도메인의 취득세를 실제 입력으로 산출. 무목업: 결측 생략·미확정 별도 표기.
입력(context['inputs']): acquisition_price(취득가액 원)·property_type('housing'/'non_housing')·
multi_home_count(보유주택수)·is_corporate(법인 bool)·is_adjusted_area(조정대상지역 bool).
주택 6억↓ 1%·6~9억 1~3% 누진·9억↑ 3%·비주택 4%·다주택/법인 중과 8/12%.
농특세(85㎡초과 0.2%)·지방교육세는 세부조건 복잡 → 본세 산출 + 별도 정직 표기(무목업).
"""

from __future__ import annotations

from app.services.senior_agents.evaluators.base import (
    PASS,
    WARN,
    RuleEvaluation,
    num,
)

_SIX = 6e8
_NINE = 9e8


def _housing_base_rate(price: float) -> float:
    """주택 유상취득 표준세율(%) — 6억↓ 1%·6~9억 누진(가액×2/3억−3)·9억↑ 3%."""
    if price <= _SIX:
        return 1.0
    if price <= _NINE:
        return max(1.0, min(3.0, price * 2 / 3e8 - 3))
    return 3.0


def _acquisition_rate(
    price: float, property_type: str, homes: int, is_corp: bool, is_adjusted: bool,
) -> tuple[float, str]:
    """취득세율(%)과 설명. 비주택 4%·주택 표준 누진·다주택/법인 중과(2020.8)."""
    if property_type == "non_housing":
        return 4.0, "비주택 표준 4%"
    base = _housing_base_rate(price)
    # 다주택/법인 중과(조정대상지역 기준).
    if is_corp or homes >= 4:
        return 12.0, "법인/4주택+ 중과 12%"
    if homes == 3:
        return (12.0, "조정 3주택 중과 12%") if is_adjusted else (8.0, "비조정 3주택 중과 8%")
    if homes == 2 and is_adjusted:
        return 8.0, "조정 2주택 중과 8%"
    return round(base, 4), f"주택 표준 {base:.2f}%"


def evaluate_tax(inputs: dict) -> list[RuleEvaluation]:
    """취득세 본세 산출(중과 시 WARN). 농특세·지방교육세는 별도 표기. 결측 생략."""
    out: list[RuleEvaluation] = []
    price = num(inputs, "acquisition_price")
    if price is None or price < 0:
        return out

    ptype = inputs.get("property_type") or "housing"
    homes_n = num(inputs, "multi_home_count")
    homes = int(homes_n) if homes_n is not None else 1
    is_corp = bool(inputs.get("is_corporate"))
    is_adjusted = bool(inputs.get("is_adjusted_area"))

    rate, desc = _acquisition_rate(price, ptype, homes, is_corp, is_adjusted)
    tax = price * rate / 100
    out.append(RuleEvaluation(
        rule_id="tax.acquisition_tax", label="취득세(본세)", value=round(rate, 2), unit="%",
        verdict=WARN if rate >= 8.0 else PASS,
        threshold="주택 1~3%·비주택 4%·다주택/법인 중과 8·12%",
        basis="지방세법 제11조(부동산 취득세율)·다주택·법인 중과(2020.8 개정)",
        detail=(f"취득가액 {price:,.0f}×{rate:.2f}%={tax:,.0f}원({desc}). "
                f"농특세(전용 85㎡초과 0.2%)·지방교육세 별도")))
    return out
