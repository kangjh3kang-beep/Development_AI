"""통합 세금 엔진 — 38종 4단계 일괄 오케스트레이션.

취득(A01~A10) + 공사(B01~B08) + 분양(C01~C08) + 양도(D01~D06) = 32종 기본
+ 조건부 6종 = 38종 완전 자동화.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.services.tax.acquisition_stage_engine import calculate_all_acquisition_stage
from app.services.tax.disposal_stage_engine import calculate_all_disposal_stage
from app.services.tax.sale_stage_engine import calculate_all_sale_stage
from app.services.tax.utility_stage_engine import calculate_all_utility_stage

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

# R2(버전드 룰엔진): calculate_all_taxes(as_of_date=...) 시 시점 해석 대상 룰 키.
# tax_rules_versions.json에 실존하는 키만 등재(가짜 룰 금지).
_VERSIONED_RULE_KEYS = (
    "acquisition_tax_matrix",
    "capital_gains_brackets",
    "land_comprehensive_tax",
    "capital_gains_multi_home_surcharge_exclusion",
)


def _effective_label(rule: dict[str, Any]) -> str:
    """시행 기간 표기 문자열 — '시행 {from} ~ {to|현행}'."""
    start = rule.get("effective_from") or "?"
    end = rule.get("effective_to") or "현행"
    return f"시행 {start} ~ {end}"


def _attach_rule_versions(result: dict[str, Any], as_of_date: date) -> dict[str, Any]:
    """as_of_date 시점의 버전드 룰 해석 결과를 응답에 additive 가산(in-place).

    - result['as_of_date'] / result['tax_rule_versions'][]: 룰별 (시행일 구간, match).
      policy_flag 룰(예: 양도세 다주택 중과 한시 배제)은 value도 함께 노출.
    - 수록 구간 밖 as_of는 가짜 과거값 대신 tax_rule_version_warnings로 정직 표기.
    - legal_refs: legal_ref_key가 일치하는 레코드에 시행일(effective_from/to·
      effective_label·rule_versions)을 가산 — '적용 세율 + 시행 기간 + 법령 링크' 결합.
    - 어떤 예외도 기존 응답을 손상시키지 않는다(graceful — 메타만 비움).
    """
    try:
        from app.services.tax.regional_tax_data import get_rule

        resolved = [
            r for r in (get_rule(key, as_of=as_of_date) for key in _VERSIONED_RULE_KEYS)
            if r is not None
        ]

        versions: list[dict[str, Any]] = []
        warnings: list[str] = []
        for r in resolved:
            entry: dict[str, Any] = {
                "rule_key": r["rule_key"],
                "effective_from": r["effective_from"],
                "effective_to": r["effective_to"],
                "effective_label": _effective_label(r),
                "legal_ref_key": r.get("legal_ref_key"),
                "match": r.get("match"),
            }
            if r.get("kind") == "policy_flag":
                entry["value"] = r.get("value")
            if r.get("warning"):
                entry["warning"] = r["warning"]
                warnings.append(f"{r['rule_key']}: {r['warning']}")
            versions.append(entry)

        result["as_of_date"] = as_of_date.isoformat()
        result["tax_rule_versions"] = versions
        if warnings:
            result["tax_rule_version_warnings"] = warnings

        by_ref_key: dict[str, list[dict[str, Any]]] = {}
        for r in resolved:
            ref_key = r.get("legal_ref_key")
            if ref_key:
                by_ref_key.setdefault(ref_key, []).append(r)

        for record in result.get("legal_refs") or []:
            matches = by_ref_key.get(record.get("key"))
            if not matches:
                continue
            primary = matches[0]
            record["effective_from"] = primary["effective_from"]
            record["effective_to"] = primary["effective_to"]
            record["effective_label"] = _effective_label(primary)
            record["rule_versions"] = [
                {
                    "rule_key": m["rule_key"],
                    "effective_from": m["effective_from"],
                    "effective_to": m["effective_to"],
                    "effective_label": _effective_label(m),
                }
                for m in matches
            ]
    except Exception:  # noqa: BLE001 — 신뢰 블록은 best-effort, 본 응답 무손상.
        result.setdefault("tax_rule_versions", [])
    return result


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
    # R2: 버전드 룰엔진 — 적용 시점(additive, 기본 None=기존 동작 완전 동일)
    as_of_date: date | None = None,
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
            # as_of_date 지정 시에만(additive):
            'as_of_date': 'YYYY-MM-DD',
            'tax_rule_versions': [...],            # 시점 해석된 룰 버전(시행일 구간)
            'tax_rule_version_warnings': [...],    # 수록 구간 밖 as_of 정직 경고(있을 때만)
        }

    additive: 각 단계 items의 개별 항목에는 레지스트리 매핑이 존재하는 세목에 한해
    legal_ref_key가 가산된다(기존 키·합산 로직 불변).

    as_of_date(additive): 지정 시 tax_rules_versions.json의 해당 시점 룰 버전을
    해석해 응답 메타(tax_rule_versions)와 legal_refs 시행일 표기를 가산한다.
    현행 수록 버전이 단일인 룰은 계산값이 현행과 동일하며, 수록 구간 밖 시점은
    가짜 과거값 대신 경고로 정직 표기한다. None이면 응답이 기존과 완전 동일.
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
    result = _attach_legal_refs(result)

    # R2 버전드 룰 레이어(additive): as_of_date 지정 시에만 시행일 메타 가산.
    # 미지정(None) 시 응답은 기존과 byte-level 동일(하위호환 절대조건).
    if as_of_date is not None:
        _attach_rule_versions(result, as_of_date)
    return result


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
