"""ComparableSet 빌더 — 개별 MOLIT 거래 사례를 선정/제외 사유와 함께 승격한다.

★SSOT 재사용(이중화 금지): MOLIT 수집·필터 로직 자체는 ``app.services.sales.pricing.suggest.
_trade_per_pyeong``(집계 SSOT)를 그대로 호출한다 — ``collect_cases=True``만 추가로 넘겨
같은 수집 루프에서 개별 사례를 함께 받는다(새 MOLIT 호출 없음, 집계 계산 재구현 없음).
"""
from __future__ import annotations

import hashlib

from app.services.market_precision.contracts import ComparableCase, ComparableSet
from app.services.sales.pricing.suggest import _trade_per_pyeong

_SELECTION_BASIS = "평당가 sanity 범위(300~20,000만원/평) 내 + 최근 8개월 MOLIT 실거래(동/시군구 매칭)"


def _case_id(building_name: str, dong: str, jibun: str, deal_ym: str, price: float, area: float) -> str:
    raw = f"{building_name}|{dong}|{jibun}|{deal_ym}|{price}|{area}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def build_comparable_set(sigungu5: str, dong: str | None, prop_type: str) -> ComparableSet:
    """시군구/동/유형으로 MOLIT 비교사례를 조회해 ComparableSet으로 조립한다.

    무자료 시 빈 사례(가짜 사례 생성 금지) + anchor_scope="unavailable" + 정직 note.
    """
    pp = await _trade_per_pyeong(sigungu5, dong, prop_type, collect_cases=True)
    raw_cases = pp.get("cases") or []
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


__all__ = ["build_comparable_set"]
