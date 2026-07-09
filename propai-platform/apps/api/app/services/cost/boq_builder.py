"""BOQ(Bill Of Quantities) 빌더 — 계약 응답 스키마 생성.

StandardQuantityEstimator 물량 + 단가 SSOT(UnitPriceRepository) → 계약 items[] 생성.
D4(시장가 3중비교): 각 항목에 standard / market(KCCI 변동모델) / actual(null) 부착.
원가 합계는 OriginCostCalculator(12단계 법정요율)로 산정.

정직성: price_source·price_basis_year·qto_source(bim ±5% / derived ±12%) 표기,
        "참고용·전문 적산사 검토 권장" 배지, 데이터 부재는 null 로 정직 표기.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

UTC = UTC

_BT_KR = {
    "apartment": "공동주택", "officetel": "오피스텔", "office": "근린생활시설",
    "commercial": "근린생활시설", "townhouse": "다세대주택",
    "single_house": "다세대주택", "warehouse": "근린생활시설",
}

# 표준 물량 work_code → 단가 SSOT 키(시장가 매핑용). 비대응(기계/전기 일식)은 None.
_WORKCODE_TO_KEY = {
    "01-콘크리트": "concrete", "02-철근": "rebar", "03-거푸집": "formwork",
    "04-조적": "masonry", "05-방수": "waterproof", "06-창호": "window",
}

# 단가 SSOT 키 → KCCI 시장단가 material_code(D4 market 축).
_KEY_TO_KCCI = {
    "concrete": "ready_mix_concrete", "rebar": "rebar_sd400_d13", "window": "glass_lowe_panel",
}

# qto_source 별 신뢰구간(정직성 표기).
_QTO_BAND = {"bim": "±5%", "derived": "±12%"}
_HONESTY_NOTE = (
    "참고용 개산 — 전문 적산사 검토 권장. 단가는 표준품셈/시장모델(시뮬레이션) 기반이며 "
    "실적단가(actual)는 미보유."
)


def _kcci_market_unit(key: str) -> float | None:
    """KCCI 변동모델로 현재월 시장 단가(원/단위) 산출 — 미대응 키는 None."""
    code = _KEY_TO_KCCI.get(key)
    if not code:
        return None
    try:
        from apps.api.services.kcci_material_price_service import (  # noqa: PLC0415
            _MATERIAL_LIBRARY,
            KCCIMaterialPriceService,
        )
        if code not in _MATERIAL_LIBRARY:
            return None
        now = datetime.now(UTC)
        anchor = datetime(now.year, now.month, 1, tzinfo=UTC)
        p = KCCIMaterialPriceService._calc_unit_price(code, anchor)
        return round(float(p["unit_price_krw"]), 2)
    except Exception:  # noqa: BLE001
        return None


def _kcci_market_source_label(key: str) -> str | None:
    """market_unit_price 출처 라벨 — ★T5 정직화(결정론 시뮬레이션, 실시세 API 아님).

    미대응 키(_KEY_TO_KCCI 밖)는 None(값이 없는데 라벨만 남기지 않음 — 정직).
    """
    if key not in _KEY_TO_KCCI:
        return None
    try:
        from apps.api.services.kcci_material_price_service import (  # noqa: PLC0415
            MARKET_PRICE_SOURCE_LABEL,
        )
        return MARKET_PRICE_SOURCE_LABEL
    except Exception:  # noqa: BLE001
        return None


async def build_boq(
    *,
    building_type: str,
    total_gfa_sqm: float,
    floor_count_above: int,
    floor_count_below: int,
    structure_type: str,
    qto_source: str = "derived",
) -> dict[str, Any]:
    """계약 items[] + summary + badges 를 생성한다(영속화 전 표현)."""
    from app.services.cost.origin_cost_calculator import OriginCostCalculator
    from app.services.cost.standard_quantity_estimator import StandardQuantityEstimator
    from app.services.cost.unit_price_repository import UnitPriceRepository

    # 단가 SSOT 1회 async 조회 → estimator 주입(DB 실패 시 None 폴백 — 동기 fallback 회귀 0).
    # 주입으로 raw 물량(mat/labor/exp)·원가합계(_calc)·items[] 단가가 동일 출처로 정합된다.
    repo = UnitPriceRepository()
    try:
        unit_prices: dict[str, dict[str, Any]] | None = await repo.get_prices()
    except Exception:  # noqa: BLE001
        unit_prices = None

    raw = StandardQuantityEstimator().estimate(
        building_type=_BT_KR.get(building_type, "공동주택"),
        total_gfa_sqm=total_gfa_sqm, floor_count_above=floor_count_above,
        floor_count_below=floor_count_below, structure_type=structure_type,
        prices=unit_prices,
    )

    band = _QTO_BAND.get(qto_source, "±12%")
    items: list[dict[str, Any]] = []
    for it in raw:
        wc = it.get("work_code", "")
        key = _WORKCODE_TO_KEY.get(wc)
        std_unit = float(it.get("mat_unit", 0)) + float(it.get("labor_unit", 0)) + float(it.get("exp_unit", 0))
        # 단가 출처: estimator가 항목별로 정직 표기(주입 DB 출처명 또는 "fallback").
        price_source = it.get("price_source", "fallback") if key else "fallback"
        basis_year = int(it.get("price_basis_year", 2026)) if key else 2026
        qty = float(it.get("quantity", 0))
        market_unit = _kcci_market_unit(key) if key else None
        items.append({
            "code": wc,
            "name": it.get("item_name"),
            "work_type": it.get("spec"),
            "quantity": qty,
            "unit": it.get("unit"),
            "unit_price": int(std_unit),               # = standard_unit_price
            "amount": int(qty * std_unit),
            "price_source": price_source,
            "price_basis_year": basis_year,
            "qto_source": qto_source,
            # D4 시장가 3중비교
            "standard_unit_price": int(std_unit),
            "market_unit_price": market_unit,
            # ★T5 정직화: market_unit_price 출처(결정론 시뮬레이션·실시세 API 아님). 값 없으면 None.
            "market_unit_price_source": _kcci_market_source_label(key) if key else None,
            "actual_unit_price": None,                 # 실적 데이터 없음(정직 표기)
        })

    # 원가 합계(12단계 법정요율).
    calc = OriginCostCalculator().calculate(raw)
    direct = int(calc.get("direct_cost", 0))
    total = int(calc.get("total_project_cost", 0))
    indirect = max(0, total - direct)
    confidence = "B" if qto_source == "bim" else "C"

    return {
        "items": items,
        "summary": {
            "direct": direct, "indirect": indirect, "total": total,
            "confidence_grade": confidence, "confidence_band": band,
            "total_project_cost": total,
        },
        "badges": {
            "note": _HONESTY_NOTE,
            "qto_source": qto_source, "confidence_band": band,
            "actual_data": "실적 데이터 없음",
        },
        "header": {
            "building_type": building_type, "structure_type": structure_type,
            "total_gfa_sqm": total_gfa_sqm, "qto_source": qto_source,
        },
        "_calc": calc,  # 내부용(라우터 영속화/AI 해석 입력)
    }
