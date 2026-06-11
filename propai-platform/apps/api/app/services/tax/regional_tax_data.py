"""229개 시군구 지역세금 기준 데이터 (수지분석고도화 v2).

3축 교차 설계: 지역(229개 시군구) × 지목(임야/농지/대지) × 개발방식(M01~M15)
"""

from __future__ import annotations

from typing import Any

# ── 취득세 매트릭스: (지목, 주택수, 조정지역) → (기본율, 중과율, 교육세율, 농특세율) ──

ACQUISITION_TAX_MATRIX: dict[tuple[str, int, bool], tuple[float, float, float, float]] = {
    # (지목, 주택수, 조정지역여부) → (기본율, 중과율, 교육세율, 농특세율)
    # 임야(forest)
    ("forest", 0, False): (0.022, 0.0, 0.002, 0.002),
    ("forest", 0, True):  (0.022, 0.0, 0.002, 0.002),
    ("forest", 1, False): (0.022, 0.0, 0.002, 0.002),
    ("forest", 1, True):  (0.022, 0.0, 0.002, 0.002),
    # 농지(farmland)
    ("farmland", 0, False): (0.030, 0.0, 0.002, 0.002),
    ("farmland", 0, True):  (0.030, 0.0, 0.002, 0.002),
    ("farmland", 1, False): (0.030, 0.0, 0.002, 0.002),
    ("farmland", 1, True):  (0.030, 0.0, 0.002, 0.002),
    # 대지(land) — 비주택
    ("land", 0, False): (0.040, 0.0, 0.004, 0.002),
    ("land", 0, True):  (0.040, 0.0, 0.004, 0.002),
    # 대지(land) — 주택 1주택
    ("land", 1, False): (0.010, 0.0, 0.001, 0.0),
    ("land", 1, True):  (0.010, 0.0, 0.001, 0.0),
    # 대지(land) — 주택 2주택
    ("land", 2, False): (0.010, 0.0, 0.001, 0.0),
    ("land", 2, True):  (0.080, 0.0, 0.004, 0.006),  # 조정지역 2주택 중과 8%(지방세법 제13조의2)
    # 대지(land) — 주택 3주택+
    ("land", 3, False): (0.080, 0.0, 0.004, 0.006),  # 비조정 3주택 중과 8%
    ("land", 3, True):  (0.120, 0.0, 0.004, 0.010),  # 조정 3주택+/법인 중과 12%(상한)
}


def _housing_sliding_rate(purchase_won: int) -> float:
    """주택 유상취득 표준세율 (지방세법 제11조 1항 8호).

    6억 이하 1%, 6~9억 구간 슬라이딩 (가액/1억 × 2/3 − 3)%, 9억 초과 3%.
    """
    if purchase_won <= 600_000_000:
        return 0.01
    if purchase_won >= 900_000_000:
        return 0.03
    return round((purchase_won / 100_000_000 * 2 / 3 - 3) / 100, 6)


def get_acquisition_tax_rates(
    land_category: str,
    house_count: int = 0,
    is_adjusted_area: bool = False,
    purchase_won: int = 0,
) -> dict[str, float]:
    """취득세율 조회.

    Args:
        land_category: 'forest', 'farmland', 'land'
        house_count: 주택수 (0=비주택, 1=1주택, 2=2주택, 3+=3주택이상)
        is_adjusted_area: 조정대상지역 여부
        purchase_won: 취득가액 (주택 표준세율 1~3% 슬라이딩 산정용.
            0이면 슬라이딩 미적용 — 기존 flat 1% 동작 유지)

    Returns:
        {'base_rate', 'surcharge_rate', 'education_rate', 'rural_rate', 'total_rate'}
    """
    key_count = min(house_count, 3)
    key = (land_category, key_count, is_adjusted_area)

    if key not in ACQUISITION_TAX_MATRIX:
        # 폴백: 대지 비주택
        rates = ACQUISITION_TAX_MATRIX[("land", 0, False)]
    else:
        rates = ACQUISITION_TAX_MATRIX[key]

    base, surcharge, edu, rural = rates

    # 표준세율(중과 아닌 1%) 적용 주택은 가액 기준 1~3% 슬라이딩
    # (1주택 전체 + 비조정 2주택). 중과(8%/12%) 구간은 flat 유지.
    if land_category == "land" and house_count >= 1 and base == 0.010 and purchase_won > 0:
        base = _housing_sliding_rate(purchase_won)
        edu = round(base * 0.1, 6)  # 주택 지방교육세 = 취득세율 × 1/2 × 20%

    return {
        "base_rate": base,
        "surcharge_rate": surcharge,
        "education_rate": edu,
        "rural_rate": rural,
        "total_rate": base + surcharge + edu + rural,
    }


# ── 농지전용부담금 ──

FARMLAND_CONVERSION_RATE = 0.30  # 공시지가 × 30%
FARMLAND_CONVERSION_MAX_PER_M2 = 50_000  # 원/m² 상한


# ── 산림조성비 ──

FOREST_CONVERSION_RATES: dict[str, int] = {
    "conservation": 4_700,  # 보전산지 (원/m²)
    "semi_conservation": 2_500,  # 준보전산지
    "temporary": 1_200,  # 임시
}


# ── 개발부담금 ──

DEVELOPMENT_CHARGE_RATES: dict[str, float] = {
    "capital_area": 0.30,  # 수도권
    "metropolitan": 0.25,  # 광역시
    "province": 0.20,  # 지방
}

NORMAL_LAND_RISE_RATE = 0.03  # 정상지가상승률 연 3%


# ── 학교용지부담금 ──

SCHOOL_SITE_CHARGE_RATE = 0.008  # 분양가의 0.8%
SCHOOL_SITE_MIN_HOUSEHOLDS = 300  # 300세대 이상 의무


# ── 광역교통부담금 (시도 기본값 + 시군구 오버라이드) ──

METRO_TRANSPORT_BASE: dict[str, dict[str, float]] = {
    # 시도 → {건물유형: 만원/세대}
    "서울": {"apartment": 21.0, "officetel": 15.0, "commercial": 18.0},
    "경기": {"apartment": 17.0, "officetel": 12.0, "commercial": 14.0},
    "인천": {"apartment": 15.0, "officetel": 11.0, "commercial": 13.0},
    "부산": {"apartment": 10.0, "officetel": 7.0, "commercial": 9.0},
    "대구": {"apartment": 9.0, "officetel": 6.5, "commercial": 8.0},
    "대전": {"apartment": 9.0, "officetel": 6.5, "commercial": 8.0},
    "광주": {"apartment": 8.5, "officetel": 6.0, "commercial": 7.5},
    "울산": {"apartment": 8.5, "officetel": 6.0, "commercial": 7.5},
}

METRO_TRANSPORT_SIGUNGU_OVERRIDE: dict[str, dict[str, float]] = {
    # 시군구 키 → {건물유형: 만원/세대}
    "경기_고양시": {"apartment": 21.0, "officetel": 15.0, "commercial": 18.0},
    "경기_성남시": {"apartment": 20.0, "officetel": 14.0, "commercial": 17.0},
    "경기_수원시": {"apartment": 18.5, "officetel": 13.0, "commercial": 15.5},
    "경기_용인시": {"apartment": 18.0, "officetel": 12.5, "commercial": 15.0},
    "경기_하남시": {"apartment": 20.0, "officetel": 14.0, "commercial": 17.0},
    "경기_과천시": {"apartment": 21.0, "officetel": 15.0, "commercial": 18.0},
    "경기_광명시": {"apartment": 19.0, "officetel": 13.5, "commercial": 16.0},
    "경기_안양시": {"apartment": 18.5, "officetel": 13.0, "commercial": 15.5},
    "경기_화성시": {"apartment": 12.0, "officetel": 8.5, "commercial": 10.0},
    "경기_평택시": {"apartment": 11.5, "officetel": 8.0, "commercial": 9.5},
    "경기_안성시": {"apartment": 10.0, "officetel": 7.0, "commercial": 8.5},
    "경기_오산시": {"apartment": 13.5, "officetel": 9.5, "commercial": 11.0},
}


def get_metro_transport_charge(
    sido_name: str,
    sigungu_name: str,
    total_households: int,
    building_type: str = "apartment",
) -> dict[str, Any]:
    """광역교통부담금 계층 조회 (시군구 오버라이드 → 시도 기본값 폴백).

    Returns:
        {'per_hh_10k_won': 만원/세대, 'total_100m_won': 억원, 'source': 'override'|'base'|'none'}
    """
    sigungu_key = f"{sido_name}_{sigungu_name}"

    override = METRO_TRANSPORT_SIGUNGU_OVERRIDE.get(sigungu_key)
    if override and building_type in override:
        per_hh = override[building_type]
        return {
            "per_hh_10k_won": per_hh,
            "total_100m_won": round(per_hh * total_households / 10_000, 4),
            "source": "override",
        }

    base = METRO_TRANSPORT_BASE.get(sido_name)
    if base and building_type in base:
        per_hh = base[building_type]
        return {
            "per_hh_10k_won": per_hh,
            "total_100m_won": round(per_hh * total_households / 10_000, 4),
            "source": "base",
        }

    # 수도권 외 또는 미등록
    return {"per_hh_10k_won": 0.0, "total_100m_won": 0.0, "source": "none"}


# ── 상수도/하수도 원인자부담금 (지자체별) ──

WATER_SUPPLY_CHARGES_WON: dict[str, int] = {
    # 시군구 → 원/세대
    "서울": 150_000, "부산": 130_000, "대구": 120_000,
    "인천": 140_000, "광주": 110_000, "대전": 115_000,
    "울산": 125_000, "세종": 135_000,
    "경기_수원시": 130_000, "경기_성남시": 140_000,
    "경기_고양시": 135_000, "경기_용인시": 125_000,
    "경기_화성시": 110_000, "경기_오산시": 120_000,
    "경기_평택시": 105_000, "경기_안성시": 100_000,
    "경기_안양시": 130_000, "경기_하남시": 135_000,
    "경기_과천시": 140_000, "경기_광명시": 130_000,
}

SEWAGE_CHARGES_WON: dict[str, int] = {
    # 시군구 → 원/세대
    "서울": 180_000, "부산": 160_000, "대구": 150_000,
    "인천": 170_000, "광주": 140_000, "대전": 145_000,
    "울산": 155_000, "세종": 165_000,
    "경기_수원시": 160_000, "경기_성남시": 170_000,
    "경기_고양시": 165_000, "경기_용인시": 155_000,
    "경기_화성시": 135_000, "경기_오산시": 150_000,
    "경기_평택시": 130_000, "경기_안성시": 125_000,
    "경기_안양시": 160_000, "경기_하남시": 165_000,
    "경기_과천시": 170_000, "경기_광명시": 160_000,
}


def get_utility_charge(
    charge_map: dict[str, int],
    sido_name: str,
    sigungu_name: str,
) -> int:
    """상하수도 원인자부담금 단가 조회 (시군구 → 시도 폴백)."""
    sigungu_key = f"{sido_name}_{sigungu_name}"
    if sigungu_key in charge_map:
        return charge_map[sigungu_key]
    if sido_name in charge_map:
        return charge_map[sido_name]
    return 120_000  # 전국 기본값


# ── HUG 분양보증수수료 ──

HUG_GUARANTEE_RATES: dict[str, float] = {
    "apartment": 0.0015,  # 0.15%
    "officetel": 0.0030,  # 0.30%
    "commercial": 0.0050,  # 0.50%
}


# ── VAT 세율 ──

VAT_EXEMPT_AREA_SQM = 85.0  # 85m² 이하 면세
VAT_RATE = 0.10  # 10%


# ── 양도소득세 누진세율 ──

CAPITAL_GAINS_BRACKETS: list[tuple[float, float, float]] = [
    # (하한 만원, 세율, 누진공제 만원)
    (0, 0.06, 0),
    (1_400, 0.15, 126),
    (5_000, 0.24, 576),
    (8_800, 0.35, 1_544),
    (15_000, 0.38, 1_994),
    (30_000, 0.40, 2_594),
    (50_000, 0.42, 3_594),
    (100_000, 0.45, 6_594),
]

# 장기보유특별공제 (보유기간 → 공제율)
LTDC_RATES_RESIDENTIAL: dict[int, float] = {
    3: 0.06, 4: 0.08, 5: 0.10, 6: 0.12, 7: 0.14,
    8: 0.16, 9: 0.18, 10: 0.20, 11: 0.22, 12: 0.24,
    13: 0.26, 14: 0.28, 15: 0.30,
}

LTDC_MAX_RESIDENTIAL = 0.80  # 주택 최대 80%
LTDC_MAX_NON_RESIDENTIAL = 0.30  # 비주택 최대 30%

# 1세대1주택 장기보유특별공제 (보유+거주 합산, 최대 80%)
LTDC_RATES_PRIMARY_RESIDENCE: dict[int, float] = {
    3: 0.24, 4: 0.32, 5: 0.40, 6: 0.48, 7: 0.56,
    8: 0.64, 9: 0.72, 10: 0.80,  # 10년 이상 80%
}

# 법인 추가세 (주택만)
CORP_ADDON_RATE_RESIDENTIAL = 0.10  # 10%


# ── 종합부동산세: 종합합산 토지(나대지) 기준 (2024) ──
# 개발사업은 착공 전 토지가 통상 '나대지=종합합산' → 공제 5억, 누진 1/2/3%.
# (주택건설사업용 토지는 종부세 비과세 특례가 있을 수 있어 별도 적용 — note 명시)
LAND_COMPREHENSIVE_DEDUCTION_WON = 500_000_000   # 종합합산 토지 공제(공시가격 기준)
LAND_FAIR_MARKET_RATIO = 1.0                       # 토지 공정시장가액비율(2024)
# (과세표준 한도, 세율, 누진공제) — 종합합산토지
LAND_COMPREHENSIVE_TAX_BRACKETS: list[tuple[float, float, int]] = [
    (1_500_000_000, 0.010, 0),
    (4_500_000_000, 0.020, 15_000_000),
    (float("inf"),  0.030, 60_000_000),
]


def calc_land_comprehensive_property_tax(
    assessed_value_won: int,
    *,
    deduction_won: int = LAND_COMPREHENSIVE_DEDUCTION_WON,
    fair_market_ratio: float = LAND_FAIR_MARKET_RATIO,
    holding_years: int = 1,
) -> dict[str, Any]:
    """종합합산 토지 종합부동산세(연간·합산). 공제 이하면 0(구조적 정확).

    과세표준 = max(0, 공시가격합산 − 공제) × 공정시장가액비율 → 누진세율 적용.
    """
    taxable = max(0.0, (assessed_value_won - deduction_won)) * fair_market_ratio
    annual = 0
    rate_applied = 0.0
    for limit, rate, prog in LAND_COMPREHENSIVE_TAX_BRACKETS:
        if taxable <= limit:
            annual = max(0, int(taxable * rate - prog))
            rate_applied = rate
            break
    total = annual * max(1, holding_years)
    return {
        "annual_won": annual,
        "total_won": total,
        "taxable_won": int(taxable),
        "rate": rate_applied,
        "deduction_won": deduction_won,
        "fair_market_ratio": fair_market_ratio,
    }
