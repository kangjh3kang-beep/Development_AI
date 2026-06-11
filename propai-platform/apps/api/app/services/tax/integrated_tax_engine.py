"""통합 세금 엔진 — 38종 4단계 일괄 오케스트레이션.

취득(A01~A10) + 공사(B01~B08) + 분양(C01~C08) + 양도(D01~D06) = 32종 기본
+ 조건부 6종 = 38종 완전 자동화.
"""

from __future__ import annotations

from typing import Any

from app.services.tax.acquisition_stage_engine import calculate_all_acquisition_stage
from app.services.tax.utility_stage_engine import calculate_all_utility_stage
from app.services.tax.sale_stage_engine import calculate_all_sale_stage
from app.services.tax.disposal_stage_engine import calculate_all_disposal_stage

# ─────────────────────────────────────────────────────────────────────────────
# 신뢰 레이어(additive): 세목 코드 → 법령 근거 레지스트리 키 매핑.
# legal_reference_registry에 **실존하는 키만** 등재한다(할루시네이션 링크 금지).
# 미등재 세목(A03 농특세, B/C 부담금류 등)은 의도적으로 매핑하지 않는다 —
# 근거 없는 링크보다 무링크가 안전. 계산 로직과 무관한 순수 매핑 데이터.
# ─────────────────────────────────────────────────────────────────────────────
_TAX_CODE_LEGAL_KEYS: dict[str, str] = {
    "A01": "acquisition_tax",             # 지방세법 제11조 (취득세)
    "A02": "local_education_tax",         # 지방세법 (지방교육세, 법령 루트)
    "A04": "stamp_tax",                   # 인지세법 제3조 (인지세)
    "D01": "capital_gains_tax",           # 소득세법 제104조 (양도소득세)
    "D05": "reconstruction_levy",         # 재건축초과이익 환수에 관한 법률 (법령 루트)
    "D06": "comprehensive_property_tax",  # 종합부동산세법 (법령 루트)
}

_STAGE_KEYS = ("acquisition", "construction", "sale", "disposal")


def _attach_legal_refs(result: dict[str, Any]) -> dict[str, Any]:
    """응답에 법령 근거를 additive로 부착(in-place) — 기존 키·합산 로직 불변.

    - 각 단계 items의 개별 항목: 코드가 매핑에 있으면 legal_ref_key 가산(setdefault).
    - 응답 루트: 실제 부착된 키들로 legal_refs[] 가산(레지스트리 get_legal_refs 출력만,
      URL 직접 조립 금지). 매핑된 항목이 없으면 빈 배열.
    - 부착 중 어떤 예외도 기존 응답을 손상시키지 않는다(graceful — legal_refs=[]).
    """
    try:
        keys: list[str] = []
        for stage_name in _STAGE_KEYS:
            stage = result.get(stage_name)
            if not isinstance(stage, dict):
                continue
            for item in stage.get("items") or []:
                if not isinstance(item, dict):
                    continue
                ref_key = _TAX_CODE_LEGAL_KEYS.get(item.get("code"))
                if ref_key:
                    item.setdefault("legal_ref_key", ref_key)
                    if ref_key not in keys:
                        keys.append(ref_key)

        from app.services.legal.legal_reference_registry import get_legal_refs

        result.setdefault("legal_refs", get_legal_refs(keys))
    except Exception:  # noqa: BLE001 — 신뢰 블록은 best-effort, 본 응답 무손상.
        result.setdefault("legal_refs", [])
    return result


def calculate_all_taxes(
    *,
    # 공통
    purchase_won: int = 0,
    land_category: str = "land",
    house_count: int = 0,
    is_adjusted: bool = False,
    area_sqm: float = 0,
    official_price_per_sqm: float = 0,
    forest_type: str = "semi_conservation",
    # 개발부담금
    end_land_value_won: int = 0,
    start_land_value_won: int = 0,
    development_cost_won: int = 0,
    project_years: float = 3.0,
    region_type: str = "capital_area",
    # 공사단계
    sido_name: str = "",
    sigungu_name: str = "",
    total_households: int = 0,
    total_sale_amount_won: int = 0,
    total_gfa_sqm: float = 0,
    building_type: str = "apartment",
    # 분양단계
    total_units: int = 0,
    avg_area_sqm: float = 85.0,
    # 양도단계
    gain_10k_won: float = 0,
    gain_won: int = 0,
    holding_years: int = 0,
    is_residential: bool = True,
    is_corporate: bool = False,
    excess_gain_won: int = 0,
    assessed_value_won: int = 0,
) -> dict[str, Any]:
    """38종 세금 4단계 일괄 계산.

    Returns:
        {
            'acquisition': {...},
            'construction': {...},
            'sale': {...},
            'disposal': {...},
            'grand_total_won': int,
            'total_items_count': int,
            'summary_by_stage': {...},
            'legal_refs': [...],  # additive — 세목별 법령 근거(레지스트리 출력만)
        }

    additive: 각 단계 items의 개별 항목에는 레지스트리 매핑이 존재하는 세목에 한해
    legal_ref_key가 가산된다(기존 키·합산 로직 불변).
    """
    acquisition = calculate_all_acquisition_stage(
        purchase_won=purchase_won,
        land_category=land_category,
        house_count=house_count,
        is_adjusted=is_adjusted,
        area_sqm=area_sqm,
        official_price_per_sqm=official_price_per_sqm,
        forest_type=forest_type,
        end_land_value_won=end_land_value_won,
        start_land_value_won=start_land_value_won,
        development_cost_won=development_cost_won,
        project_years=project_years,
        region_type=region_type,
    )

    construction = calculate_all_utility_stage(
        sido_name=sido_name,
        sigungu_name=sigungu_name,
        total_households=total_households,
        total_sale_amount_won=total_sale_amount_won,
        total_gfa_sqm=total_gfa_sqm,
        building_type=building_type,
    )

    sale = calculate_all_sale_stage(
        total_sale_amount_won=total_sale_amount_won,
        total_units=total_units,
        avg_area_sqm=avg_area_sqm,
        total_gfa_sqm=total_gfa_sqm,
        building_type=building_type,
    )

    disposal = calculate_all_disposal_stage(
        gain_10k_won=gain_10k_won,
        gain_won=gain_won,
        holding_years=holding_years,
        is_residential=is_residential,
        is_corporate=is_corporate,
        excess_gain_won=excess_gain_won,
        assessed_value_won=assessed_value_won,
    )

    grand_total = (
        acquisition["total_won"]
        + construction["total_won"]
        + sale["total_won"]
        + disposal["total_won"]
    )

    total_items = (
        acquisition["applicable_count"]
        + construction["applicable_count"]
        + sale["applicable_count"]
        + disposal["applicable_count"]
    )

    result = {
        "acquisition": acquisition,
        "construction": construction,
        "sale": sale,
        "disposal": disposal,
        "grand_total_won": grand_total,
        "total_items_count": total_items,
        "summary_by_stage": {
            "acquisition": acquisition["total_won"],
            "construction": construction["total_won"],
            "sale": sale["total_won"],
            "disposal": disposal["total_won"],
        },
    }
    # 신뢰 레이어(additive): items별 legal_ref_key + 루트 legal_refs[] 가산.
    # 기존 키·합산값은 1개도 변경하지 않는다(실패 시에도 본 응답 무손상).
    return _attach_legal_refs(result)


def get_applicable_tax_codes(
    *,
    development_type: str,
    land_category: str = "land",
) -> list[str]:
    """개발유형+지목별 적용 가능한 세금 코드 목록.

    Returns:
        ['A01', 'A02', ...] 적용 가능 코드 리스트
    """
    # 기본 공통 코드 (항상 적용)
    base_codes = ["A01", "A02", "A03", "A04", "A05", "A06", "A07"]

    # 지목별 조건부
    if land_category == "farmland":
        base_codes.append("A08")
    elif land_category == "forest":
        base_codes.append("A09")

    # 개발부담금 (대부분 적용)
    base_codes.append("A10")

    # 공사단계 (항상)
    base_codes.extend(["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08"])

    # 분양단계
    base_codes.extend(["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08"])

    # 양도단계 (기본)
    base_codes.extend(["D01", "D03"])

    # 개발유형별 특화
    if development_type == "M02":  # 재건축
        base_codes.append("D05")  # 초과이익환수

    # 보유세
    base_codes.append("D06")

    return sorted(set(base_codes))
