"""예상 탁상감정(Desk Appraisal) — 정식 감정평가가 아닌 사전 추정(은행 탁상가액 성격).

감정평가에 관한 규칙 기준 방법론을 우리 데이터에 매핑:
 1) 공시지가기준법(원칙, §14): 개별공시지가 × 시점수정 × 개별요인(접도·면적) × 그 밖의 요인(기타요인) 보정.
    - '그 밖의 요인'은 공시지가↔시세 괴리 보정으로, 지역 시세보정계수(MARKET_MULTIPLIER)를 사용.
 2) 거래사례비교법(보조, §14): 인근 토지 실거래 평균단가(있을 때) 비교.
 3) 결합: 공시지가기준법 주(主) + 거래사례 보조 가중, 신뢰도·근거 제시.

⚠ 정식 감정평가가 아닌 참고용 탁상 추정치(사용자 수정 가능). 실제 평가는 감정평가사 의뢰 필요.
"""

from __future__ import annotations

from typing import Any

from app.services.land_intelligence.land_price_estimator import _market_multiplier

# 개별요인 — 접도(road_side) 보정율(감정평가 개별요인의 가로조건 근사)
_ROAD_FACTOR = [
    (("광대",), 1.10, "광대로 접면(가로조건 우세)"),
    (("중로",), 1.02, "중로 접면"),
    (("소로",), 0.97, "소로 접면"),
    (("세로(가)", "세로가"), 0.93, "세로(가) 접면"),
    (("세로(불)", "세로불", "맹지"), 0.85, "세로(불)/맹지(가로조건 열세)"),
]


def _road_factor(road_side: str | None) -> tuple[float, str]:
    rs = road_side or ""
    for keys, f, label in _ROAD_FACTOR:
        if any(k in rs for k in keys):
            return f, label
    return 1.0, "접도 보통(기본)"


def _area_factor(area_sqm: float | None) -> tuple[float, str]:
    """면적 개별요인(과대·과소 획지 감가) 근사."""
    if not area_sqm:
        return 1.0, "면적요인 미적용"
    if area_sqm < 60:
        return 0.95, "과소획지(60㎡ 미만) 소폭 감가"
    if area_sqm > 3000:
        return 0.97, "대규모 획지 환금성 감가"
    return 1.0, "표준 규모"


async def desk_appraisal(
    *,
    pnu: str | None = None,
    address: str = "",
    area_sqm: float | None = None,
    official_price_per_sqm: float | None = None,
    comparable_avg_per_sqm: float | None = None,   # 거래사례 평균단가(주변 토지 실거래)
    time_adjust: float = 1.02,                       # 시점수정(공시기준일→현재, 기본 +2%)
    base_year: int = 2025,
) -> dict[str, Any]:
    """예상 탁상감정가 산출(공시지가기준법 + 거래사례비교법 결합)."""
    op = official_price_per_sqm
    area = area_sqm
    road_side = None
    src = "입력값"

    if op is None or not area or pnu:
        try:
            from app.services.external_api.vworld_service import VWorldService
            vw = VWorldService()
            if not pnu and address:
                geo = await vw.geocode_address(address)
                pnu = (geo or {}).get("pnu") or pnu
            if pnu:
                lc = await vw.get_land_characteristics(pnu)
                if lc:
                    op = op if op is not None else lc.get("official_price_per_sqm")
                    area = area or lc.get("area_sqm")
                    road_side = lc.get("road_side") or None
                    src = "NED 토지특성(주소→PNU)"
        except Exception:  # noqa: BLE001
            pass

    if not op or op <= 0:
        return {"ok": False, "message": "공시지가를 확인할 수 없습니다. PNU 또는 공시지가를 입력하세요."}

    op = float(op)
    area_f = float(area) if area else None

    # ── 1) 공시지가기준법 ──
    other_factor, other_rationale = _market_multiplier(address)   # 그 밖의 요인(기타요인) 보정
    road_f, road_label = _road_factor(road_side)
    area_fac, area_label = _area_factor(area_f)
    pubprice_unit = op * time_adjust * road_f * area_fac * other_factor
    method_pub = {
        "method": "공시지가기준법",
        "unit_price": int(pubprice_unit),
        "factors": {
            "개별공시지가": int(op), "시점수정": time_adjust,
            "개별요인_접도": road_f, "개별요인_면적": area_fac,
            "그밖의요인": other_factor,
        },
        "rationale": f"개별공시지가 {int(op):,}원/㎡ × 시점수정 {time_adjust} × 접도 {road_f}({road_label}) × 면적 {area_fac} × 그밖의요인 {other_factor}({other_rationale})",
    }

    # ── 2) 거래사례비교법 ──
    method_cmp = None
    if comparable_avg_per_sqm and comparable_avg_per_sqm > 0:
        cmp_unit = float(comparable_avg_per_sqm) * road_f * area_fac  # 개별요인 보정(시점은 사례가 최근 가정)
        method_cmp = {
            "method": "거래사례비교법",
            "unit_price": int(cmp_unit),
            "comparable_avg_per_sqm": int(comparable_avg_per_sqm),
            "rationale": f"인근 토지 실거래 평균 {int(comparable_avg_per_sqm):,}원/㎡ × 접도 {road_f} × 면적 {area_fac}",
        }

    # ── 3) 결합(공시지가기준법 주 0.6 + 거래사례 0.4) ──
    if method_cmp:
        appraised_unit = method_pub["unit_price"] * 0.6 + method_cmp["unit_price"] * 0.4
        weight_note = "공시지가기준법 60% + 거래사례비교법 40% 가중결합"
        # 두 방법 괴리로 신뢰도 산정
        hi = max(method_pub["unit_price"], method_cmp["unit_price"])
        lo = min(method_pub["unit_price"], method_cmp["unit_price"])
        spread = (hi - lo) / hi if hi else 0
        confidence = round(max(0.4, 1 - spread), 2)
    else:
        appraised_unit = method_pub["unit_price"]
        weight_note = "공시지가기준법 단독(거래사례 부족) — 거래사례 확보 시 정밀도 향상"
        confidence = 0.6

    appraised_unit = int(appraised_unit)
    appraised_total = int(appraised_unit * area_f) if area_f else None
    margin = int(appraised_unit * (1 - confidence))  # 신뢰구간(±)

    return {
        "ok": True,
        "appraised_price_per_sqm": appraised_unit,
        "appraised_total_won": appraised_total,
        "area_sqm": round(area_f, 1) if area_f else None,
        "confidence": confidence,
        "range_per_sqm": {"low": appraised_unit - margin, "high": appraised_unit + margin},
        "methods": [m for m in (method_pub, method_cmp) if m],
        "weight_note": weight_note,
        "road_side": road_side,
        "source": src,
        "base_year": base_year,
        "disclaimer": "본 결과는 정식 감정평가가 아닌 참고용 예상 탁상감정치입니다(은행 탁상가액 성격). "
                      "실제 가치는 감정평가사 정식 평가가 필요하며, 사용자가 수정할 수 있습니다.",
    }
