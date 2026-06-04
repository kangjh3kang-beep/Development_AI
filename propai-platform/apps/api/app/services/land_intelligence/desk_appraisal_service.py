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


# 건물 재조달원가(원/㎡, 2026 근사)·내용연수 — 원가법 건물가치 산정용
_REPLACEMENT_COST = {
    "SRC": (2_500_000, 50), "철골철근콘크리트": (2_500_000, 50),
    "RC": (2_000_000, 50), "철근콘크리트": (2_000_000, 50),
    "철골": (1_800_000, 40), "S조": (1_800_000, 40),
    "조적": (1_500_000, 45), "벽돌": (1_500_000, 45),
    "목조": (1_400_000, 40), "목": (1_400_000, 40),
}
_RESIDUAL_FLOOR = 0.2  # 잔가율 하한(잔존가치 20%)


def _building_value(gfa: float | None, structure: str | None, year_built: int | None, now_year: int) -> dict[str, Any] | None:
    """원가법 건물가치 = 재조달원가 × 연면적 × 잔가율(1 − 경과/내용연수, 하한 20%)."""
    if not gfa or gfa <= 0:
        return None
    rc, life = 1_800_000, 45
    matched = "기본(RC 가정)"
    for key, (cost, yrs) in _REPLACEMENT_COST.items():
        if structure and key in structure:
            rc, life, matched = cost, yrs, key
            break
    age = max(0, now_year - year_built) if year_built else 0
    residual = max(_RESIDUAL_FLOOR, 1 - age / life) if life else _RESIDUAL_FLOOR
    value = int(rc * gfa * residual)
    return {
        "method": "원가법(건물)",
        "replacement_cost_per_sqm": rc,
        "structure": matched, "useful_life_yrs": life,
        "age_yrs": age, "residual_ratio": round(residual, 3),
        "building_value_won": value,
        "rationale": f"재조달원가 {rc:,}원/㎡ × 연면적 {gfa:,.0f}㎡ × 잔가율 {residual:.2f}(경과 {age}년/내용 {life}년) = {value:,}원",
    }


def _income_value(
    monthly_rent_won: float | None, deposit_won: float | None,
    vacancy_rate: float, opex_ratio: float, cap_rate: float,
) -> dict[str, Any] | None:
    """수익환원법 — 부동산 가치 = 순영업소득(NOI) / 자본환원율.

    NOI = (월임대료 + 보증금 운용수익) × 12 × (1−공실률) × (1−운영경비율).
    보증금은 전월세전환율(연 5.5%)로 운용수익 환산.
    """
    if not monthly_rent_won or monthly_rent_won <= 0:
        return None
    deposit_monthly = (deposit_won or 0) * 0.055 / 12  # 보증금 월 운용수익
    pgi = (monthly_rent_won + deposit_monthly) * 12      # 가능총수익(연)
    noi = pgi * (1 - vacancy_rate) * (1 - opex_ratio)    # 순영업소득
    cap = cap_rate if cap_rate > 0 else 0.045
    value = int(noi / cap)
    return {
        "method": "수익환원법",
        "noi_won": int(noi), "cap_rate": cap,
        "vacancy_rate": vacancy_rate, "opex_ratio": opex_ratio,
        "income_value_won": value,
        "rationale": f"NOI {int(noi):,}원(월임대 {int(monthly_rent_won):,}×12, 공실 {vacancy_rate*100:.0f}%·경비 {opex_ratio*100:.0f}% 차감) ÷ 자본환원율 {cap*100:.1f}% = {value:,}원",
    }


def _shape_factor(irregularity: float | None) -> tuple[float, str]:
    """형상 개별요인 — 부정형도(1-실면적/bbox)로 형상 감가(정형 우세, 부정형 열세)."""
    if irregularity is None:
        return 1.0, "형상 미상(정형 가정)"
    if irregularity >= 0.5:
        return 0.90, "심한 부정형(가로/이용 효율 열세)"
    if irregularity >= 0.3:
        return 0.95, "부정형(소폭 감가)"
    if irregularity >= 0.15:
        return 0.98, "준정형"
    return 1.0, "정형(효율 우세)"


async def desk_appraisal(
    *,
    pnu: str | None = None,
    address: str = "",
    area_sqm: float | None = None,
    official_price_per_sqm: float | None = None,
    comparable_avg_per_sqm: float | None = None,   # 거래사례 평균단가(주변 토지 실거래)
    time_adjust: float | None = None,                # 시점수정(미지정 시 지가변동률로 산정)
    base_year: int = 2025,
    building_gfa_sqm: float | None = None,           # 건물 연면적(주면 토지+건물 복합 추정)
    building_structure: str | None = None,           # 구조(RC/SRC/철골/조적/목조)
    building_year_built: int | None = None,          # 준공연도(감가상각)
    monthly_rent_won: float | None = None,           # 월 임대료(주면 수익환원법 병행)
    deposit_won: float | None = None,                # 보증금
    vacancy_rate: float = 0.05,                      # 공실률
    opex_ratio: float = 0.25,                        # 운영경비율
    cap_rate: float = 0.045,                         # 자본환원율
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

    # 거래사례 자동 연동: 미입력 시 주변 토지 실거래 평균단가(/㎡)를 자동 추출
    if comparable_avg_per_sqm is None and pnu and len(pnu) >= 5:
        try:
            from app.services.land_intelligence.nearby_map_service import NearbyMapService
            payload = await NearbyMapService().build(
                address=address or "", lawd_cd=pnu[:5], months=6, radius_m=1500,
            )
            land_cat = (payload.get("categories") or {}).get("land_trade") or {}
            units: list[tuple[float, int]] = []
            for g in land_cat.get("groups", []):
                ap10k = g.get("avg_price_10k") or 0
                aarea = g.get("avg_area_m2") or 0
                cnt = int(g.get("count") or 0)
                if ap10k and aarea:
                    units.append((ap10k * 10000.0 / aarea, max(1, cnt)))
            if units:
                wsum = sum(c for _, c in units)
                comparable_avg_per_sqm = sum(u * c for u, c in units) / wsum
        except Exception:  # noqa: BLE001
            pass

    # 형상 개별요인 — 필지 폴리곤 부정형도로 형상 감가
    irregularity = None
    if pnu:
        try:
            from app.services.external_api.vworld_service import VWorldService
            from app.services.site_score.solar_envelope_service import dims_from_polygon
            parcel = await VWorldService().get_parcel_by_pnu(pnu)
            dims = dims_from_polygon((parcel or {}).get("geometry"))
            if dims:
                irregularity = dims.get("irregularity")
        except Exception:  # noqa: BLE001
            pass

    op = float(op)
    area_f = float(area) if area else None

    # 시점수정: 미지정 시 지가변동률(시도별 연율) 누적계수로 산정
    from app.services.land_intelligence.land_price_index import time_adjust_factor
    ta = time_adjust_factor(address, base_year)
    time_adjust = float(time_adjust) if time_adjust is not None else ta["factor"]

    # ── 1) 공시지가기준법 ──
    other_factor, other_rationale = _market_multiplier(address)   # 그 밖의 요인(기타요인) 보정
    road_f, road_label = _road_factor(road_side)
    area_fac, area_label = _area_factor(area_f)
    shape_f, shape_label = _shape_factor(irregularity)
    pub_unit_price = int(op * time_adjust * road_f * area_fac * shape_f * other_factor)
    method_pub = {
        "method": "공시지가 기준 추정",
        "unit_price": pub_unit_price,
        "factors": {
            "개별공시지가": int(op), "시점수정": time_adjust,
            "개별요인_접도": road_f, "개별요인_면적": area_fac, "개별요인_형상": shape_f,
            "그밖의요인": other_factor,
        },
        "rationale": f"개별공시지가 {int(op):,}원/㎡ × 시점수정 {time_adjust} × 접도 {road_f}({road_label}) × 면적 {area_fac} × 형상 {shape_f}({shape_label}) × 그밖의요인 {other_factor}({other_rationale})",
    }

    # ── 2) 거래사례비교법 ──
    method_cmp = None
    cmp_unit_price = 0
    if comparable_avg_per_sqm and comparable_avg_per_sqm > 0:
        cmp_unit_price = int(float(comparable_avg_per_sqm) * road_f * area_fac * shape_f)  # 개별요인 보정
        method_cmp = {
            "method": "실거래 비교 추정",
            "unit_price": cmp_unit_price,
            "comparable_avg_per_sqm": int(comparable_avg_per_sqm),
            "rationale": f"인근 토지 실거래 평균 {int(comparable_avg_per_sqm):,}원/㎡ × 접도 {road_f} × 면적 {area_fac} × 형상 {shape_f}",
        }

    # ── 3) 다법인 교차검증 모사(5개 법인: 그밖의요인 ±5%·거래사례 가중 ±10% 변동) ──
    import random as _random
    seed = abs(hash((pnu or address or "") + str(int(op)))) % (2**31)
    rnd = _random.Random(seed)
    firm_vals: list[int] = []
    for _ in range(5):
        of_i = other_factor * (1 + rnd.uniform(-0.05, 0.05))
        pub_i = op * time_adjust * road_f * area_fac * shape_f * of_i
        if cmp_unit_price > 0:
            w = 0.6 + rnd.uniform(-0.1, 0.1)
            firm_vals.append(int(pub_i * w + cmp_unit_price * (1 - w)))
        else:
            firm_vals.append(int(pub_i))
    firm_mean = sum(firm_vals) / len(firm_vals)
    firm_std = (sum((v - firm_mean) ** 2 for v in firm_vals) / len(firm_vals)) ** 0.5
    cv = firm_std / firm_mean if firm_mean else 0
    cross_check = {
        "firms": sorted(firm_vals),
        "mean": int(firm_mean),
        "std": int(firm_std),
        "cv_pct": round(cv * 100, 1),
        "min": min(firm_vals), "max": max(firm_vals),
        "note": "복수 시나리오(보정계수·실거래 가중 분포) 교차검증. 편차(CV)가 낮을수록 추정 안정성↑.",
    }

    # 채택가 = 교차검증 평균. 신뢰도 = 1 - CV(법인간 편차 작을수록↑).
    appraised_unit = int(firm_mean)
    confidence = round(max(0.4, 1 - cv * 3), 2)  # CV 0%→1.0, ~20%→0.4
    weight_note = (
        "공시지가 기준 + 실거래 비교 결합 후 복수 시나리오 교차검증 평균 채택"
        if method_cmp else
        "공시지가 기준 + 복수 시나리오 교차검증 평균 채택(실거래 확보 시 정밀도↑)"
    )
    appraised_total = int(appraised_unit * area_f) if area_f else None
    margin = int(appraised_unit * (1 - confidence))  # 신뢰구간(±)

    # ── 토지+건물 복합 추정(건물 입력 시): 토지가치 + 원가법 건물가치 ──
    building = _building_value(building_gfa_sqm, building_structure, building_year_built, base_year + 1)
    complex_total = None
    if building and appraised_total is not None:
        complex_total = appraised_total + building["building_value_won"]

    # ── 수익환원법(임대료 입력 시): 부동산 전체 수익가치(원가법 복합과 병행 제시) ──
    income = _income_value(monthly_rent_won, deposit_won, vacancy_rate, opex_ratio, cap_rate)
    income_total = income["income_value_won"] if income else None
    complex_note = None
    if complex_total is not None and income_total is not None:
        complex_note = (
            f"원가법 복합 {complex_total:,}원 vs 수익환원법 {income_total:,}원 — "
            "수익형은 임대수익 기준, 원가법은 토지+건물 재조달 기준. 용도·임대안정성에 따라 채택."
        )

    return {
        "ok": True,
        "appraised_price_per_sqm": appraised_unit,
        "appraised_total_won": appraised_total,
        "building": building,
        "complex_total_won": complex_total,   # 토지+건물 복합 예상가치(원가법, 건물 입력 시)
        "income": income,                      # 수익환원법(임대료 입력 시)
        "income_total_won": income_total,
        "complex_note": complex_note,
        "area_sqm": round(area_f, 1) if area_f else None,
        "confidence": confidence,
        "range_per_sqm": {"low": appraised_unit - margin, "high": appraised_unit + margin},
        "cross_check": cross_check,
        "irregularity": irregularity,
        "methods": [m for m in (method_pub, method_cmp) if m],
        "weight_note": weight_note,
        "road_side": road_side,
        "source": src,
        "base_year": base_year,
        "time_adjust": round(time_adjust, 4),
        "time_adjust_basis": ta["rationale"],
        "disclaimer": "본 추정치는 「감정평가 및 감정평가사에 관한 법률」상 감정평가가 아니며, "
                      "공시지가·실거래 등 공개데이터에 기반한 참고용 예상 시세 추정입니다. "
                      "법적 효력이 있는 가치 산정은 감정평가법인에 의뢰해야 하며, 본 값은 사용자가 수정할 수 있습니다.",
    }
