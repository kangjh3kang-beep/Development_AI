"""ComparableSet 빌더 — 개별 MOLIT 거래 사례를 선정/제외 사유와 함께 승격한다.

★SSOT 재사용(이중화 금지): MOLIT 수집·필터 로직 자체는 ``app.services.sales.pricing.suggest.
_trade_per_pyeong``(집계 SSOT)를 그대로 호출한다 — ``collect_cases=True``만 추가로 넘겨
같은 수집 루프에서 개별 사례를 함께 받는다.

★R1 M-1 봉합(행 재사용 vs 재수집): 이 모듈은 순수 조립(``build_comparable_set_from_cases``,
I/O 없음)과 단독 수집(``build_comparable_set``, ``_trade_per_pyeong`` 자체 호출)을 분리한다.
``suggest_base_price(collect_cases=True)``가 이미 원시 사례를 "trade_cases"에 실어 반환하는
정규 경로(``price_suggestion.py``)는 반드시 ``build_comparable_set_from_cases``로 그 행을
그대로 소비해야 한다(``build_comparable_set``을 다시 부르면 MOLIT 8개월 조회가 중복된다 —
전에 있던 결함). ``build_comparable_set``은 ``suggest_base_price`` 경유 없이 독립적으로
비교사례만 필요한 호출부를 위한 편의 진입점으로만 남긴다.
"""
from __future__ import annotations

import hashlib
from typing import Any

from app.services.market_precision.contracts import ComparableCase, ComparableSet
from app.services.sales.pricing.suggest import _trade_per_pyeong

_SELECTION_BASIS = "평당가 sanity 범위(300~20,000만원/평) 내 + 최근 8개월 MOLIT 실거래(동/시군구 매칭)"


def _case_id(building_name: str, dong: str, jibun: str, deal_ym: str, price: float, area: float) -> str:
    raw = f"{building_name}|{dong}|{jibun}|{deal_ym}|{price}|{area}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_comparable_set_from_cases(raw_cases: list[dict[str, Any]] | None) -> ComparableSet:
    """이미 수집된 원시 MOLIT 사례(``_trade_per_pyeong``의 "cases" 값)를 ComparableSet으로
    순수 조립한다(I/O 없음 — 재수집하지 않는다). 무자료 시 빈 사례(가짜 사례 생성 금지).
    """
    if not raw_cases:
        return ComparableSet(
            cases=(), included_count=0, excluded_count=0,
            anchor_scope="unavailable", data_source="unavailable",
            note="주변 실거래 사례가 없어 비교사례를 구성할 수 없습니다(가짜 사례 생성 금지).",
        )

    cases: list[ComparableCase] = []
    included = 0
    excluded = 0
    for rc in raw_cases:
        building_name = rc.get("building_name") or ""
        dong_val = rc.get("dong") or ""
        jibun = rc.get("jibun") or ""
        deal_ym = rc.get("ym") or ""
        price = float(rc.get("price_10k_won") or 0.0)
        area = float(rc.get("area_m2") or 0.0)
        is_included = bool(rc.get("included"))
        case = ComparableCase(
            case_id=_case_id(building_name, dong_val, jibun, deal_ym, price, area),
            source="MOLIT_실거래",
            building_name=building_name,
            dong=dong_val,
            jibun=jibun,
            deal_ym=deal_ym,
            deal_date=rc.get("deal_date"),
            price_10k_won=price,
            area_m2=area,
            per_pyeong_10k=rc.get("per_pyeong_10k"),
            proximity_scope="동일법정동" if rc.get("matched_dong") else "동일시군구(타동)",
            included=is_included,
            selection_basis=_SELECTION_BASIS,
            exclude_reason=rc.get("exclude_reason"),
        )
        cases.append(case)
        if is_included:
            included += 1
        else:
            excluded += 1

    anchor_scope = "동" if any(c.included and c.proximity_scope == "동일법정동" for c in cases) else "시군구"
    return ComparableSet(
        cases=tuple(cases),
        included_count=included,
        excluded_count=excluded,
        anchor_scope=anchor_scope,
        data_source="molit_live",
        note=f"MOLIT 실거래 {included + excluded}건 중 {included}건 선정·{excluded}건 제외(사유는 사례별 exclude_reason 참조).",
    )


async def build_comparable_set(sigungu5: str, dong: str | None, prop_type: str) -> ComparableSet:
    """시군구/동/유형으로 MOLIT을 직접 수집해 ComparableSet을 조립하는 독립 진입점.

    ★``suggest_base_price`` 결과가 이미 있는 경로(price_suggestion.py)에서는 이 함수를 쓰지
    않는다 — 그 결과의 "trade_cases"를 ``build_comparable_set_from_cases``로 소비해야
    MOLIT 재수집(중복 8개월 조회)을 피한다. 이 함수는 ``suggest_base_price`` 없이 비교사례
    단독이 필요한 호출부 전용이다.
    """
    pp = await _trade_per_pyeong(sigungu5, dong, prop_type, collect_cases=True)
    return build_comparable_set_from_cases(pp.get("cases"))


__all__ = ["build_comparable_set", "build_comparable_set_from_cases"]
