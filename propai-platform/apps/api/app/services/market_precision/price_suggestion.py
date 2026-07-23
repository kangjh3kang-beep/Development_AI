"""PriceSuggestion 조립 — suggest_base_price() SSOT 결과를 계약으로 재포장.

★SSOT 재사용(이중화 금지): 분양가 계산 자체(거래사례비교 3안 tiers·trust 교차검증·원가회수
검증)는 ``app.services.sales.pricing.suggest.suggest_base_price``를 그대로 사용한다 — 이
모듈은 그 결과를 ``PriceSuggestion`` 계약 형태로 재포장하고 ``ComparableSet``(개별사례)·
``TimeAdjustment``(시점보정)·``AbsorptionEstimate``(흡수율)를 부가할 뿐, 가격 산식을
재구현하지 않는다. 기존 ``suggest_base_price()`` 응답/호출부(``routers`` 등)는 전혀
변경하지 않는다(무회귀).
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.market_precision.absorption import estimate_absorption
from app.services.market_precision.comparables import build_comparable_set
from app.services.market_precision.contracts import (
    AbsorptionEstimate,
    ComparableSet,
    PriceSuggestion,
    TimeAdjustment,
)
from app.services.market_precision.time_adjustment import resolve_time_adjustment
from app.services.sales.pricing.suggest import _PROP_TYPE, _extract_dong, suggest_base_price


def price_suggestion_from_result(
    res: dict[str, Any],
    *,
    comparable_set: ComparableSet | None = None,
    time_adjustment: TimeAdjustment | None = None,
    absorption_estimate: AbsorptionEstimate | None = None,
) -> PriceSuggestion:
    """이미 계산된 ``suggest_base_price()`` 결과 ``res``에서 PriceSuggestion을 순수 조립한다
    (I/O 없음 — 재계산·재수집 없이 res의 tiers/trust/cost_validation을 그대로 재포장).
    """
    data_source = res.get("data_source") or "unavailable"
    tiers = res.get("tiers") or []
    trust = res.get("trust") or {}
    cost_val = res.get("cost_validation")
    market_ref = res.get("market_reference") or {}

    limitations: list[str] = []
    if trust.get("warnings"):
        limitations.extend(trust["warnings"])
    if cost_val and cost_val.get("warning"):
        limitations.append(cost_val["warning"])

    if not tiers or data_source != "live":
        limitations.append(res.get("note") or "적정분양가 데이터가 아직 산출되지 않았습니다.")
        return PriceSuggestion(
            point_10k=None, range_low_10k=None, range_high_10k=None,
            unit_label="만원/평(공급)", data_source=data_source,
            basis="비교사례 데이터 부재로 분양가 범위를 산출할 수 없습니다(가짜값 금지).",
            assumptions=(), limitations=tuple(limitations),
            affordability=cost_val, comparable_set=comparable_set,
            time_adjustment=time_adjustment, absorption_estimate=absorption_estimate,
        )

    conservative = tiers[0].get("per_pyeong_10k")
    base = tiers[1].get("per_pyeong_10k") if len(tiers) > 1 else conservative
    aggressive = tiers[-1].get("per_pyeong_10k")
    assumptions = (
        f"범위(보수~공격) = 주변 실거래 시세(공급환산 {market_ref.get('market_pp_supply_10k')}만원/평,"
        f" 신뢰도 {trust.get('confidence')}) × 신축 프리미엄"
        f"(+{tiers[0].get('premium_pct')}%~+{tiers[-1].get('premium_pct')}%). 점추정(base)은 참고용 —"
        f" 범위 전체가 근거입니다(점추정 단독 채택 금지).",
    )

    return PriceSuggestion(
        point_10k=base, range_low_10k=conservative, range_high_10k=aggressive,
        unit_label="만원/평(공급)", data_source=data_source,
        basis=res.get("note") or "",
        assumptions=assumptions, limitations=tuple(limitations),
        affordability=cost_val, comparable_set=comparable_set,
        time_adjustment=time_adjustment, absorption_estimate=absorption_estimate,
    )


async def _enrich_from_result(
    res: dict[str, Any],
) -> tuple[ComparableSet | None, TimeAdjustment, AbsorptionEstimate]:
    """``res``(suggest_base_price 출력)의 위치정보로 ComparableSet/TimeAdjustment/
    AbsorptionEstimate 3종을 조회한다(``assemble_market_precision``·``build_price_suggestion``
    공용 — MOLIT 재수집은 ComparableSet 빌드 시 1회뿐, ``_trade_per_pyeong`` 재사용).
    """
    lawd_cd = res.get("lawd_cd") or ""
    address = res.get("address") or ""
    dev_type = res.get("development_type")

    comparable_set: ComparableSet | None = None
    if lawd_cd:
        dong = _extract_dong(address)
        prop_type = _PROP_TYPE.get((dev_type or "").upper(), "apt")
        comparable_set = await build_comparable_set(lawd_cd[:5], dong, prop_type)

    time_adjustment = await resolve_time_adjustment(address)
    absorption_estimate = estimate_absorption()
    return comparable_set, time_adjustment, absorption_estimate


async def assemble_market_precision(res: dict[str, Any]) -> dict[str, Any]:
    """이미 계산된 ``suggest_base_price()`` 결과 ``res``로부터 market_precision 번들을 조립한다.

    ``suggest_base_price()``를 재호출하지 않는다(무이중화) — 호출부(라우터)가 이미 계산한
    ``res``를 그대로 전달한다.
    """
    comparable_set, time_adjustment, absorption_estimate = await _enrich_from_result(res)
    suggestion = price_suggestion_from_result(
        res, comparable_set=comparable_set,
        time_adjustment=time_adjustment, absorption_estimate=absorption_estimate,
    )
    return {
        "price_suggestion": suggestion.to_dict(),
        "comparable_set": comparable_set.to_dict() if comparable_set else None,
        "time_adjustment": time_adjustment.to_dict(),
        "absorption_estimate": absorption_estimate.to_dict(),
    }


async def build_price_suggestion(
    db: AsyncSession, site_id: uuid.UUID, bcode: str | None = None,
    *, construction_cost_per_gfa_won: int | None = None,
) -> PriceSuggestion:
    """DB에서 직접 조립하는 편의 진입점(신규 호출부용) — suggest_base_price() 1회 호출 후,
    ComparableSet/TimeAdjustment/AbsorptionEstimate를 모두 부착한 PriceSuggestion을 반환한다.
    """
    res = await suggest_base_price(
        db, site_id, bcode=bcode, construction_cost_per_gfa_won=construction_cost_per_gfa_won,
    )
    comparable_set, time_adjustment, absorption_estimate = await _enrich_from_result(res)
    return price_suggestion_from_result(
        res, comparable_set=comparable_set,
        time_adjustment=time_adjustment, absorption_estimate=absorption_estimate,
    )


__all__ = ["assemble_market_precision", "build_price_suggestion", "price_suggestion_from_result"]
