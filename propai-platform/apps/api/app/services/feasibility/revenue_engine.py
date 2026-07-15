"""수입 산정 엔진 — 분양/임대/복합/조합원배분 수입 계산.

순수 함수형 설계: DB 의존 없음, 입력 dict → 출력 dict.
참조값: 오산 내삼미동 M04 총수입 11,812억
  - 조합원분양 5,278억, 일반분양 5,684억, 상가 750억, 부대수입 100억
"""

from __future__ import annotations

from typing import Any

from app.services.data_validation.calculation_metadata import CalculationMetadata

# 평 → m² 변환 상수
PYEONG_TO_SQM = 3.305785

# 지역별 자본환원율 (Cap Rate)
REGIONAL_CAP_RATES: dict[str, float] = {
    "서울": 0.045, "경기": 0.055, "인천": 0.055,
    "부산": 0.06, "대구": 0.06, "대전": 0.06,
    "광주": 0.065, "울산": 0.065, "세종": 0.055,
    "default": 0.06,
}


def get_regional_cap_rate(region: str = "default") -> float:
    """지역별 자본환원율 조회.

    Args:
        region: 지역명 (시도 단위, 예: '서울', '경기')

    Returns:
        자본환원율 (소수점)
    """
    return REGIONAL_CAP_RATES.get(region, REGIONAL_CAP_RATES["default"])


def calculate_sale_revenue(
    *,
    households: int,
    avg_area_pyeong: float,
    avg_price_per_pyeong: float,
    sale_ratio: float = 1.0,
) -> dict[str, Any]:
    """일반분양 수입 계산.

    Args:
        households: 총 세대수
        avg_area_pyeong: 평균 전용면적 (평)
        avg_price_per_pyeong: 평균 분양가 (원/평)
        sale_ratio: 분양 비율 (0~1)

    Returns:
        {'sale_households', 'total_area_pyeong', 'total_revenue_won', 'detail'}
    """
    sale_hh = int(households * sale_ratio)
    total_area = sale_hh * avg_area_pyeong
    total_revenue = int(total_area * avg_price_per_pyeong)

    return {
        "sale_households": sale_hh,
        "total_area_pyeong": round(total_area, 2),
        "total_revenue_won": total_revenue,
        "detail": {
            "avg_area_pyeong": avg_area_pyeong,
            "avg_price_per_pyeong": avg_price_per_pyeong,
        },
    }


def calculate_union_revenue(
    *,
    union_households: int,
    avg_area_pyeong: float,
    avg_allotment_price_per_pyeong: float,
) -> dict[str, Any]:
    """조합원분양 수입 계산 (M01/M02/M04 등).

    Args:
        union_households: 조합원 세대수
        avg_area_pyeong: 평균 배정면적 (평)
        avg_allotment_price_per_pyeong: 조합원 분양가 (원/평)

    Returns:
        {'union_households', 'total_area_pyeong', 'total_revenue_won'}
    """
    total_area = union_households * avg_area_pyeong
    total_revenue = int(total_area * avg_allotment_price_per_pyeong)

    return {
        "union_households": union_households,
        "total_area_pyeong": round(total_area, 2),
        "total_revenue_won": total_revenue,
    }


def calculate_rental_revenue(
    *,
    rental_units: int,
    monthly_rent_per_unit: int = 0,
    management_fee_per_unit: int = 0,
    vacancy_rate: float = 0.05,
    cap_rate: float | None = None,
    region: str = "default",
    avg_area_pyeong: float = 0,
    avg_deposit_per_pyeong: float = 0,
    avg_monthly_rent_per_pyeong: float = 0,
    **kwargs: Any,
) -> dict[str, Any]:
    """임대수입 계산 (보증금 제외, 순 월세 기반 자본환원).

    월세 수입만 자본환원(cap rate)하여 가치를 산정합니다.
    보증금은 별도로 total_deposit_won으로 반환하되,
    capitalized_value_won 계산에는 포함하지 않습니다.

    Args:
        rental_units: 임대 세대/호수
        monthly_rent_per_unit: 세대당 월세 (원) — 신규 방식
        management_fee_per_unit: 세대당 관리비 (원) — 신규 방식
        vacancy_rate: 공실률 (기본 5%)
        cap_rate: 자본환원율 (직접 지정 시 사용, 없으면 region 기반)
        region: 지역명 (cap_rate 미지정 시 자동 조회)
        avg_area_pyeong: 평균 면적 (평) — 레거시 호환
        avg_deposit_per_pyeong: 보증금 (원/평) — 레거시 호환
        avg_monthly_rent_per_pyeong: 월세 (원/평) — 레거시 호환

    Returns:
        {'rental_units', 'total_deposit_won', 'annual_rent_won',
         'annual_net_rent_won', 'capitalized_value_won', 'total_revenue_won'}
    """
    # 지역 기반 cap_rate 적용 (명시 미지정 시에만 — None 센티널)
    # (이전: cap_rate == 0.05 값 비교라 사용자가 명시한 0.05도 지역값으로 덮어썼음)
    if cap_rate is None:
        cap_rate = get_regional_cap_rate(region) if region != "default" else 0.05

    metadata = CalculationMetadata("임대수입")
    metadata.add_source("자본환원율(Cap Rate)", "하드코딩", is_live=False)
    metadata.add_source("공실률", "하드코딩")
    metadata.add_warning("임대수입은 시장 상황에 따라 ±10% 변동 가능")

    # 신규 방식 (세대당 월세 직접 입력)
    if monthly_rent_per_unit > 0:
        annual_net_rent = (monthly_rent_per_unit - management_fee_per_unit) * 12 * rental_units
        annual_net_rent_after_vacancy = int(annual_net_rent * (1 - vacancy_rate))
        capitalized_value = int(annual_net_rent_after_vacancy / cap_rate) if cap_rate > 0 else 0

        result = {
            "rental_units": rental_units,
            "monthly_rent_per_unit": monthly_rent_per_unit,
            "management_fee_per_unit": management_fee_per_unit,
            "vacancy_rate": vacancy_rate,
            "cap_rate": cap_rate,
            "annual_rent_won": annual_net_rent,
            "annual_net_rent_won": annual_net_rent_after_vacancy,
            "capitalized_value_won": capitalized_value,
            "total_revenue_won": capitalized_value,
        }
        result["_metadata"] = metadata.to_dict()
        return result

    # 레거시 방식 (평당 단가 입력) — 보증금 제외, 월세만 자본환원
    total_area = rental_units * avg_area_pyeong
    total_deposit = int(total_area * avg_deposit_per_pyeong)
    annual_rent = int(total_area * avg_monthly_rent_per_pyeong * 12)
    annual_rent_after_vacancy = int(annual_rent * (1 - vacancy_rate))
    capitalized = int(annual_rent_after_vacancy / cap_rate) if cap_rate > 0 else 0

    result = {
        "rental_units": rental_units,
        "total_area_pyeong": round(total_area, 2),
        "total_deposit_won": total_deposit,
        "vacancy_rate": vacancy_rate,
        "cap_rate": cap_rate,
        "annual_rent_won": annual_rent,
        "annual_net_rent_won": annual_rent_after_vacancy,
        "capitalized_value_won": capitalized,
        # ★갭 감사(2026-07-15) P1 봉합: 보증금은 환급 부채라 수입이 아니다 — docstring·
        #   신규 경로(total_revenue=capitalized)와 동일 계약. 종전 `total_deposit + capitalized`는
        #   보증금 제외 수정이 신규 경로에만 반영되고 유일한 활성 소비처(revenue_block —
        #   레거시 평당단가 방식만 호출)에는 미도달해 임대수입이 ~2배 과대됐다.
        #   보증금은 total_deposit_won으로 별도 반환(현금흐름·정보용).
        "total_revenue_won": capitalized,
    }
    result["_metadata"] = metadata.to_dict()
    return result


def calculate_ancillary_revenue(
    *,
    commercial_area_pyeong: float = 0,
    commercial_price_per_pyeong: float = 0,
    other_income_won: int = 0,
) -> dict[str, Any]:
    """부대수입 계산 (상가분양, 기타수입).

    Returns:
        {'commercial_revenue_won', 'other_income_won', 'total_revenue_won'}
    """
    commercial = int(commercial_area_pyeong * commercial_price_per_pyeong)
    return {
        "commercial_revenue_won": commercial,
        "other_income_won": other_income_won,
        "total_revenue_won": commercial + other_income_won,
    }


def calculate_total_revenue(
    *,
    sale_revenue: dict[str, Any] | None = None,
    union_revenue: dict[str, Any] | None = None,
    rental_revenue: dict[str, Any] | None = None,
    ancillary_revenue: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """총수입 합산.

    Returns:
        {'sale', 'union', 'rental', 'ancillary', 'total_revenue_won', 'breakdown_won'}
    """
    sale_won = (sale_revenue or {}).get("total_revenue_won", 0)
    union_won = (union_revenue or {}).get("total_revenue_won", 0)
    rental_won = (rental_revenue or {}).get("total_revenue_won", 0)
    ancillary_won = (ancillary_revenue or {}).get("total_revenue_won", 0)

    total = sale_won + union_won + rental_won + ancillary_won

    return {
        "sale": sale_revenue,
        "union": union_revenue,
        "rental": rental_revenue,
        "ancillary": ancillary_revenue,
        "total_revenue_won": total,
        "breakdown_won": {
            "sale": sale_won,
            "union": union_won,
            "rental": rental_won,
            "ancillary": ancillary_won,
        },
    }
