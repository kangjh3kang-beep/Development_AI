"""공사단계 세금 엔진 — B01~B08 (8종).

B01: 광역교통부담금
B02: 학교용지부담금
B03: 상수도 원인자부담금
B04: 하수도 원인자부담금
B05: 전기인입부담금
B06: 도시가스인입부담금
B07: 통신인입부담금
B08: 소방시설부담금
"""

from __future__ import annotations

from typing import Any

from app.services.legal.legal_reference_registry import get_legal_ref
from app.services.tax.regional_tax_data import (
    SCHOOL_SITE_CHARGE_RATE,
    SCHOOL_SITE_CHARGE_RATE_DETACHED,
    SCHOOL_SITE_MIN_HOUSEHOLDS,
    SEWAGE_CHARGES_WON,
    get_metro_transport_charge,
    get_utility_charge,
)

# 부담금 코드 → 법령 근거 키(legal_reference_registry). 근거+링크(evidence) 부착용.
_B_LEGAL_KEY: dict[str, str] = {
    "B01": "metro_transport_charge",   # 대도시권광역교통관리법 §7의2
    "B02": "school_land_special",      # 학교용지 확보 특례법
    "B03": "water_supply_cause_charge",  # 수도법 §71
    "B04": "sewage_cause_charge",      # 하수도법 §61
}

# ── B02 학교용지부담금 요율 판정(단일 SSOT — R1 교정) ──
# 학교용지법 §2 3호: '공동주택'에 **준주택 중 대통령령 규모 오피스텔 포함**(2021.6.23
# 시행령~현행 2025.6.21 유지) → 분양형(주거용) 오피스텔은 0.4% 부과 대상이다.
# §5의2: 단독주택 건축용 토지 조성·개발은 1.4%. 순수 업무·상업 등 비주거만 면제.
# 판정 정책: **명시 비주거만 면제, 미지 토큰은 공동주택 요율로 부과**(과소계상 방지 —
# 총사업비 보수 방향). 토큰 어휘는 생산자 feasibility_service_v2._get_building_type의
# 실방출값(apartment/officetel/office/house/townhouse) + 프론트 한글 라벨 계열.
_SCHOOL_SITE_DETACHED_TYPES = {"house", "단독주택", "detached", "전원주택", "타운하우스분양지"}
_SCHOOL_SITE_EXEMPT_TYPES = {
    "office", "업무시설", "commercial", "상업시설", "상가", "근린생활시설",
    "industrial", "산업시설", "지식산업센터", "물류", "logistics", "창고",
    "hotel", "호텔", "숙박시설",
}


def school_site_rate_for(building_type: str) -> float | None:
    """건물유형 → 학교용지부담금 요율(None=면제·비주거).

    공용 헬퍼(SSOT) — budget_template 등 다른 소비처도 이 판정을 따라야 한다.
    """
    bt = (building_type or "").strip()
    if bt in _SCHOOL_SITE_DETACHED_TYPES:
        return SCHOOL_SITE_CHARGE_RATE_DETACHED  # §5의2 단독주택지 1.4%
    if bt in _SCHOOL_SITE_EXEMPT_TYPES:
        return None
    return SCHOOL_SITE_CHARGE_RATE  # 공동주택 0.4% — officetel·townhouse·미지 토큰 포함(보수)


def calculate_b01_metro_transport(
    *,
    sido_name: str,
    sigungu_name: str = "",
    total_gfa_sqm: float = 0,
    building_type: str = "apartment",
    exclusive_area_sqm: float | None = None,
    standard_build_cost_won_per_sqm: int | None = None,
    total_households: int = 0,  # 하위호환(미사용 — 실산식은 연면적 기반)
    address: str = "",
) -> dict[str, Any]:
    """B01 광역교통시설부담금 = 표준건축비 × 부과율 × 건축연면적(대도시권광역교통관리법 §7의2).

    ★실산식(연면적 기반)으로 교체 — 이전 '만원/세대 정액표'는 법정식과 달라 날조라 폐기(무목업 수정).
    표준건축비 고시값 미설정 시 amount_won=0 + detail.confidence=unavailable(무목업·정직). 비대도시권=0.
    """
    result = get_metro_transport_charge(
        sido_name=sido_name, gfa_sqm=total_gfa_sqm, building_type=building_type,
        exclusive_area_sqm=exclusive_area_sqm,
        standard_build_cost_won_per_sqm=standard_build_cost_won_per_sqm,
        # ★주소를 넘겨야 시도 미상일 때 자가치유된다(호출부가 시군구를 넘겨도).
        address=address,
    )
    amt = result.get("amount_won")
    detail = {k: v for k, v in result.items() if k != "amount_won"}
    detail["amount_computable"] = amt is not None
    return {
        "code": "B01", "name": "광역교통시설부담금",
        "base_won": int(total_gfa_sqm),
        "rate": result.get("rate"),
        "amount_won": amt if amt is not None else 0,
        "detail": detail,
    }


def calculate_b02_school_site(
    *,
    total_sale_amount_won: int,
    total_households: int,
    building_type: str = "apartment",
) -> dict[str, Any]:
    """B02 학교용지부담금 (300세대 이상 의무).

    ★건물유형 게이트(R1 교정 반영): 요율은 school_site_rate_for(단일 SSOT)가 판정 —
    공동주택 0.4%(§5의2 1호 — **분양형 오피스텔은 준주택 포함이라 부과 대상**, §2 3호
    2021.6.23~) · 단독주택지 1.4%(§5의2 2호) · 명시 비주거(업무·상업 등)만 면제.
    미지 토큰은 공동주택 요율 부과(과소계상 방지 보수). 한계: 오피스텔의 대통령령
    규모 기준·도시형생활주택 소형 면제 등 세부 조항 미반영 — detail에 표기.
    """
    rate = school_site_rate_for(building_type)
    if rate is None:
        return {
            "code": "B02", "name": "학교용지부담금",
            "base_won": 0, "rate": SCHOOL_SITE_CHARGE_RATE,
            "amount_won": 0,
            "detail": {"reason": (
                f"건물유형 '{building_type or '미상'}' — 주택건설사업 아님"
                "(학교용지법 §2 대상 외 · 업무/상업 등 비주거 면제)"
            )},
        }
    if total_households < SCHOOL_SITE_MIN_HOUSEHOLDS:
        return {
            "code": "B02", "name": "학교용지부담금",
            "base_won": 0, "rate": rate,
            "amount_won": 0,
            "detail": {"reason": f"{total_households}세대 < {SCHOOL_SITE_MIN_HOUSEHOLDS}세대 면제"},
        }
    amount = int(total_sale_amount_won * rate)
    result: dict[str, Any] = {
        "code": "B02", "name": "학교용지부담금",
        "base_won": total_sale_amount_won, "rate": rate,
        "amount_won": amount,
    }
    if (building_type or "").strip() in ("officetel", "오피스텔"):
        # 무날조 한계 표기: §2 3호는 '대통령령으로 정하는 규모'의 오피스텔만 포함 —
        # 규모 기준 미충족(업무용 등)이면 개별 면제 확인 필요(부과 방향 보수 상한).
        result["detail"] = {"note": (
            "분양형 오피스텔=준주택 포함 부과(학교용지법 §2 3호·2021.6.23~) — "
            "대통령령 규모 기준 미충족·업무용이면 개별 면제 확인 필요"
        )}
    return result


def calculate_b03_water_supply(
    *,
    sido_name: str,
    sigungu_name: str,
    total_households: int,
) -> dict[str, Any]:
    """B03 상수도 원인자부담금 — ★**단위단가 개념이 없다**(실비·원가계산).

    수도법 §71② → 시행령 §65③: *"다음 각 호의 **비용을 합산한 금액**"*(신설·증설비 ·
    원상복구 공사비 · 수돗물 요금 상당액 · 급수차 경비 · 도로복구비 …).
    §65① 단서의 *"수돗물 **사용량**에 따라 … **고려하여** 정할 수 있다"* 는 **재량 고려사항**이지
    `사용량 × 단위단가` 산식이 아니다. 실제 조례 표본(강릉시 상수도 급수 조례)도 비용 축이
    **구경(관경)** 이고 `'㎥'` **0회**다.

    ★따라서 이 항목은 **사전 산정 자체가 불가**하다 — 표를 두지 않고 항상 보류한다.
      종전에는 `원/세대 × 세대수` 로 부과했고(출처 0건의 생성값), 첫 봉합에서 나는 그것을
      `원/㎥/일` 로 바꿨는데 **그것도 근거가 없었다**(독립 리뷰 지적 — 지어낸 값을
      지어낸 차원으로 바꾼 셈).

    `total_households` 는 시그니처 호환을 위해 남긴다(호출부가 넘긴다) — **쓰지 않는다.**
    """
    return {
        "code": "B03", "name": "상수도 원인자부담금",
        "base_won": 0, "rate": None, "amount_won": 0,
        "detail": {
            "confidence": "unavailable", "surveyed": False,
            "reason": ("상수도 원인자부담금 미산정 — 수도법 §71·시행령 §65③ 은 신설·증설 "
                       "**실비(원가계산) 합산**이라 사전 단일단가가 존재하지 않는다"
                       "(조례도 「원가계산에 따른 예정가격」 + 사후 정산). "
                       "관할 상수도사업소 협의 견적이 필요하다."),
        },
    }


def calculate_b04_sewage(
    *,
    sido_name: str,
    sigungu_name: str,
    total_households: int,
) -> dict[str, Any]:
    """B04 하수도 원인자부담금 — **오수발생량(㎥/일) × 단위단가(원/㎥/일)**.

    ★종전에는 `원/세대 × 세대수` 로 부과했다. 이 함수의 `reason` 이 스스로
      *"오수발생량×조례단가"* 라고 적어 놓고 **세대수를 곱하는** 자기모순이었다.
      법제처 원문(대조군으로 파서 생존 증명):
        · 하수도법 §61① + 시행령 §35① — *"오수가 **하루 10세제곱미터** 이상 증가"*
        · 울산광역시 하수도 사용 조례 §24①4호 — *"**오수발생량(㎥/일)에 단위단가(원/㎥/일)를
          곱하여** 산정한다"*
      ★**법 2 + 시행령 2** 에서 `'세대'`·`'가구'` 출현 **0회**. ★조례는 별개(울산 §9② 는 세대별 정액 고시 허용).
    """
    rate = get_utility_charge(SEWAGE_CHARGES_WON, sido_name, sigungu_name)
    if rate is None:
        return {
            "code": "B04", "name": "하수도 원인자부담금",
            "base_won": 0, "rate": None, "amount_won": 0,
            "detail": {
                "confidence": "unavailable", "surveyed": False,
                "reason": ("하수도 원인자부담금 미산정 — 관할 지자체 **단위단가(원/㎥/일)** 미확보. "
                           "단가는 조례가 아니라 **시 공고**에 있어 자동조회 대상이 아니다"
                           "(하수도법 §61·시행령 §35 — 오수발생량 ㎥/일 기준). "
                           "관할 공고의 단위단가와 예상 오수발생량을 입력해 주십시오."),
            },
        }
    return {
        "code": "B04", "name": "하수도 원인자부담금",
        "base_won": 0, "rate": rate.won_per_cbm_day, "amount_won": 0,
        "detail": {
            "confidence": "unavailable", "surveyed": False,
            "basis": rate.basis, "source_url": rate.source_url, "as_of": rate.as_of,
            "reason": ("단위단가는 확보했으나 **예상 오수발생량(㎥/일)** 이 입력되지 않아 미산정 — "
                       "환경부 「건축물의 용도별 오수발생량…산정방법」 고시 별표 기준으로 "
                       "산정한 값을 입력해 주십시오."),
        },
    }


def calculate_b05_electricity(
    *,
    total_households: int,
    per_hh_won: int = 250_000,
) -> dict[str, Any]:
    """B05 전기인입부담금."""
    amount = per_hh_won * total_households
    return {
        "code": "B05", "name": "전기인입부담금",
        "base_won": total_households, "rate": per_hh_won,
        "amount_won": amount,
    }


def calculate_b06_gas(
    *,
    total_households: int,
    per_hh_won: int = 180_000,
) -> dict[str, Any]:
    """B06 도시가스인입부담금."""
    amount = per_hh_won * total_households
    return {
        "code": "B06", "name": "도시가스인입부담금",
        "base_won": total_households, "rate": per_hh_won,
        "amount_won": amount,
    }


def calculate_b07_telecom(
    *,
    total_households: int,
    per_hh_won: int = 80_000,
) -> dict[str, Any]:
    """B07 통신인입부담금."""
    amount = per_hh_won * total_households
    return {
        "code": "B07", "name": "통신인입부담금",
        "base_won": total_households, "rate": per_hh_won,
        "amount_won": amount,
    }


def calculate_b08_fire(
    *,
    total_gfa_sqm: float,
    per_sqm_won: int = 3_500,
) -> dict[str, Any]:
    """B08 소방시설부담금."""
    amount = int(total_gfa_sqm * per_sqm_won)
    return {
        "code": "B08", "name": "소방시설부담금",
        "base_won": int(total_gfa_sqm), "rate": per_sqm_won,
        "amount_won": amount,
    }


def calculate_all_utility_stage(
    *,
    sido_name: str = "",
    sigungu_name: str = "",
    total_households: int = 0,
    total_sale_amount_won: int = 0,
    total_gfa_sqm: float = 0,
    building_type: str = "apartment",
    address: str = "",
) -> dict[str, Any]:
    """B01~B08 공사단계 전체 일괄 계산.

    Returns:
        {'items': [...], 'total_won': int, 'applicable_count': int}
    """
    items = [
        calculate_b01_metro_transport(
            sido_name=sido_name, sigungu_name=sigungu_name,
            total_gfa_sqm=total_gfa_sqm, building_type=building_type,
            address=address,
        ),
        calculate_b02_school_site(
            total_sale_amount_won=total_sale_amount_won,
            total_households=total_households,
            building_type=building_type,
        ),
        calculate_b03_water_supply(
            sido_name=sido_name, sigungu_name=sigungu_name,
            total_households=total_households,
        ),
        calculate_b04_sewage(
            sido_name=sido_name, sigungu_name=sigungu_name,
            total_households=total_households,
        ),
        calculate_b05_electricity(total_households=total_households),
        calculate_b06_gas(total_households=total_households),
        calculate_b07_telecom(total_households=total_households),
        calculate_b08_fire(total_gfa_sqm=total_gfa_sqm),
    ]

    # 각 부담금에 법령 근거(근거+링크·evidence) 부착 — DRY 일괄(개별 함수 미수정·verified URL).
    for it in items:
        ref = get_legal_ref(_B_LEGAL_KEY.get(it.get("code", ""), ""))
        if ref:
            it["legal_ref"] = ref
    total = sum(it["amount_won"] for it in items)
    return {
        "stage": "construction",
        "items": items,
        "total_won": total,
        "applicable_count": len(items),
    }
