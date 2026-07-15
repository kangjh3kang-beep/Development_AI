"""229개 시군구 지역세금 기준 데이터 (수지분석고도화 v2).

3축 교차 설계: 지역(229개 시군구) × 지목(임야/농지/대지) × 개발방식(M01~M15)

R2(법령 시행일 버전드 룰엔진): 핵심 세율 상수(ACQUISITION_TAX_MATRIX·
CAPITAL_GAINS_BRACKETS·LAND_COMPREHENSIVE_TAX_BRACKETS 등)는
tax_rules_versions.json으로 외부화되었고, 기존 상수명은 **현행 최신본을
가리키는 별칭**으로 유지된다(하위호환 — 기존 호출·테스트 무수정 통과).
시점별 조회는 get_rule(rule_key, as_of=...)로 한다.
"""

from __future__ import annotations

import copy
import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# R2: 법령 시행일 버전드 룰 로더 (tax_rules_versions.json)
#
# 스키마: rules[rule_key] = {kind, legal_ref_key, versions: [
#     {effective_from, effective_to(null=현행), legal_basis, value}, ...]}
# 원칙: 잘못된 과거 세율/시행일 추정 금지 — 검증 버전만 수록하고, 수록 구간
# 밖의 as_of 요청은 가짜 과거값 대신 match="out_of_range" + warning으로 정직 표기.
# ─────────────────────────────────────────────────────────────────────────────

_TAX_RULES_VERSIONS_PATH = Path(__file__).resolve().parent / "tax_rules_versions.json"


def _parse_iso_date(value: str | None) -> date | None:
    """ISO 'YYYY-MM-DD' → date. None/빈값은 None(개방 구간)."""
    if not value:
        return None
    return date.fromisoformat(value)


@lru_cache(maxsize=1)
def _load_tax_rules_versions() -> dict[str, Any]:
    """tax_rules_versions.json 로드 + 구조 검증(실패 시 fail-fast — 무결성 우선)."""
    with open(_TAX_RULES_VERSIONS_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    rules = data.get("rules")
    if not isinstance(rules, dict) or not rules:
        raise ValueError(f"tax_rules_versions.json: 'rules' 비어있음 ({_TAX_RULES_VERSIONS_PATH})")
    for rule_key, rule in rules.items():
        versions = rule.get("versions")
        if not isinstance(versions, list) or not versions:
            raise ValueError(f"tax_rules_versions.json: rule '{rule_key}' versions 비어있음")
        for ver in versions:
            eff_from = _parse_iso_date(ver.get("effective_from"))
            if eff_from is None:
                raise ValueError(f"tax_rules_versions.json: rule '{rule_key}' effective_from 누락")
            eff_to = _parse_iso_date(ver.get("effective_to"))
            if eff_to is not None and eff_to < eff_from:
                raise ValueError(f"tax_rules_versions.json: rule '{rule_key}' 시행 구간 역전")
    return data


def _build_rule_result(rule_key: str, rule: dict, version: dict, match: str,
                       warning: str | None = None) -> dict[str, Any]:
    """get_rule 반환 레코드 구성 — value는 깊은 복사(캐시 오염 방지)."""
    out: dict[str, Any] = {
        "rule_key": rule_key,
        "value": copy.deepcopy(version["value"]),
        "effective_from": version["effective_from"],
        "effective_to": version.get("effective_to"),
        "legal_ref_key": rule.get("legal_ref_key"),
        "legal_basis": version.get("legal_basis", ""),
        "kind": rule.get("kind", "rate_table"),
        "match": match,
    }
    if warning:
        out["warning"] = warning
    return out


def get_rule(rule_key: str, as_of: date | None = None) -> dict[str, Any] | None:
    """버전드 세율 룰 조회.

    Args:
        rule_key: tax_rules_versions.json의 룰 키.
        as_of: 적용 시점. None이면 현행 최신본(effective_to=null 우선).

    Returns:
        {rule_key, value, effective_from, effective_to, legal_ref_key,
         legal_basis, kind, match[, warning]} — 미등록 rule_key는 None.
        match: 'latest'(as_of 미지정 현행본) | 'exact'(구간 일치) |
               'out_of_range'(수록 구간 이전 — 최초 수록본 폴백+경고) |
               'stale'(종료된 마지막 구간 폴백+경고; 데이터 공백 시).
    """
    rule = _load_tax_rules_versions()["rules"].get(rule_key)
    if rule is None:
        return None

    versions = sorted(rule["versions"], key=lambda v: _parse_iso_date(v["effective_from"]))

    if as_of is None:
        # 현행 최신본: 개방 구간(effective_to=null) 중 최신 → 없으면 최신 시행본.
        open_versions = [v for v in versions if _parse_iso_date(v.get("effective_to")) is None]
        chosen = open_versions[-1] if open_versions else versions[-1]
        return _build_rule_result(rule_key, rule, chosen, "latest")

    started = [v for v in versions if _parse_iso_date(v["effective_from"]) <= as_of]
    if not started:
        earliest = versions[0]
        return _build_rule_result(
            rule_key, rule, earliest, "out_of_range",
            warning=(
                f"as_of={as_of.isoformat()} 이전의 검증된 룰 데이터 미보유 — "
                f"최초 수록본(시행 {earliest['effective_from']})을 폴백 반환(과거 세율 추정 금지)"
            ),
        )

    candidate = started[-1]
    cand_to = _parse_iso_date(candidate.get("effective_to"))
    if cand_to is None or as_of <= cand_to:
        return _build_rule_result(rule_key, rule, candidate, "exact")

    # 데이터 공백(종료된 마지막 구간 이후, 후속 버전 미수록) — 정직 경고 폴백.
    return _build_rule_result(
        rule_key, rule, candidate, "stale",
        warning=(
            f"as_of={as_of.isoformat()} 시점의 룰 버전 미수록 — "
            f"직전 버전(시행 {candidate['effective_from']} ~ {candidate.get('effective_to')})을 폴백 반환"
        ),
    )


# ── 취득세 매트릭스: (지목, 주택수, 조정지역) → (기본율, 중과율, 교육세율, 농특세율) ──


def _acquisition_matrix_from_records(
    records: list[dict[str, Any]],
) -> dict[tuple[str, int, bool], tuple[float, float, float, float]]:
    """JSON 레코드 목록 → 기존 매트릭스 dict 구조(튜플 키/값) 복원."""
    return {
        (r["land_category"], int(r["house_count"]), bool(r["is_adjusted_area"])): (
            r["base_rate"], r["surcharge_rate"], r["education_rate"], r["rural_rate"],
        )
        for r in records
    }


# 별칭(하위호환): 현행 최신본 — 기존 import·조회 코드 무수정 동작.
ACQUISITION_TAX_MATRIX: dict[tuple[str, int, bool], tuple[float, float, float, float]] = (
    _acquisition_matrix_from_records(get_rule("acquisition_tax_matrix")["value"])
)


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
    as_of: date | None = None,
) -> dict[str, float]:
    """취득세율 조회.

    Args:
        land_category: 'forest', 'farmland', 'land'
        house_count: 주택수 (0=비주택, 1=1주택, 2=2주택, 3+=3주택이상)
        is_adjusted_area: 조정대상지역 여부
        purchase_won: 취득가액 (주택 표준세율 1~3% 슬라이딩 산정용.
            0이면 슬라이딩 미적용 — 기존 flat 1% 동작 유지)
        as_of: 적용 시점(additive). None이면 현행 최신본 — 기존 동작 완전 동일.
            지정 시 해당 시점 버전드 매트릭스(get_rule) 적용.

    Returns:
        {'base_rate', 'surcharge_rate', 'education_rate', 'rural_rate', 'total_rate'}
    """
    if as_of is None:
        matrix = ACQUISITION_TAX_MATRIX
    else:
        matrix = _acquisition_matrix_from_records(
            get_rule("acquisition_tax_matrix", as_of=as_of)["value"]
        )

    key_count = min(house_count, 3)
    key = (land_category, key_count, is_adjusted_area)

    if key not in matrix:
        # 폴백: 대지 비주택
        rates = matrix[("land", 0, False)]
    else:
        rates = matrix[key]

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

# ★현행 요율: 공동주택 분양가의 0.4% (학교용지법 §5의2). 법률 제20568호(2024.12.20 공포·
#   2025.6.21 시행)로 0.8%→0.4% 인하·의무세대 100→300 상향. 시행 후 최초 분양공고 승인분부터 적용.
#   (구값 0.008은 개정 전 값이라 신규 분양사업 과대계상 — 실무 수지표도 "변경전 0.8% 변경후 0.4%" 확인.)
SCHOOL_SITE_CHARGE_RATE = 0.004  # 공동주택 분양가의 0.4%
SCHOOL_SITE_CHARGE_RATE_DETACHED = 0.014  # 단독주택지 분양가의 1.4% (§5의2 1호·2호)
SCHOOL_SITE_MIN_HOUSEHOLDS = 300  # 300세대 이상 의무


# ── 광역교통시설부담금 (대도시권광역교통관리법 §7의2·시행령 제16조의2) ──
# ★실산식(다중출처 확정·법제처/국토부): 부담금 = 1㎡당 표준건축비 × 부과율 × 건축연면적 − 공제액.
#   · 부과율: 주택 전용면적 85㎡ 이하 1%(100분의1)·초과 2%(100분의2)·주택 외 2%.
#   · 건축연면적 = 전체연면적 − (비주거 지하층·건물내 주차장·부대복리·주민공동시설).
#   · 표준건축비 = 국토교통부장관 고시(제2024-192호 계열) — ★값을 지어내지 않는다(무목업).
#     고시 첨부값이라 코드 기본값 None. 관리자/호출부가 주입(주입 전엔 정직 unavailable).
# 부과 대상: 대도시권(수도권·부산울산권·대구권·광주권·대전권). 그 외 미부과(0).
# ★이전 '만원/세대 정액표'는 법정 산식(연면적 기반)과 다른 날조라 폐기(무목업 위반 수정).

# 대도시권 시·도(대도시권광역교통관리법 시행령 별표1 권역의 중심 시·도). 경남·경북·전남·충남·충북은
# 일부 시군만 권역 → 과부과 방지 위해 v1은 중심 시·도만 부과(권역 시군 정밀판정 후속).
METRO_AREA_SIDO: set[str] = {"서울", "인천", "경기", "부산", "울산", "대구", "광주", "대전", "세종"}

# ── 시도명 정규화(완전명 → 단가표 축약 키) ──────────────────────────
# ★후속 스윕(2026-07-15 감사): 부담금 테이블(METRO_AREA_SIDO·상하수도 단가표)은 축약형
#   키("서울")인데 호출자(개략수지·지오코딩 경로)는 행정 완전명("서울특별시")을 전달 —
#   B01 광역교통이 대도시권을 비대도시권으로 오판(침묵 미부과)하고 B03/B04 상하수도가
#   등록 지자체인데도 unavailable로 강등되던 미매칭을 조회 지점에서 일괄 봉합한다.
_SIDO_FULL_TO_SHORT: dict[str, str] = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원",
    "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남",
    "제주특별자치도": "제주", "제주도": "제주",
}


def normalize_sido_short(sido_name: str) -> str:
    """시도명을 부담금 테이블 축약 키로 정규화 — 이미 축약형이면 그대로(멱등)."""
    s = (sido_name or "").strip()
    return _SIDO_FULL_TO_SHORT.get(s, s)
# 표준건축비(원/㎡): 국토부 고시값 — 미확정(고시 첨부·비색인) → None. 관리자 설정/호출부 주입 필요.
METRO_STANDARD_BUILD_COST_WON_PER_SQM: int | None = None
_METRO_HOUSING_TYPES = {"apartment", "아파트", "주택", "공동주택", "다세대", "연립", "도시형생활주택"}


def metro_transport_charge_rate(*, is_housing: bool, exclusive_area_sqm: float | None) -> float:
    """광역교통시설부담금 부과율(시행령 제16조의2): 주택 전용 85㎡ 이하 1%·초과 2%·주택 외 2%."""
    if not is_housing:
        return 0.02
    if exclusive_area_sqm is not None and exclusive_area_sqm <= 85.0:
        return 0.01
    return 0.02  # 85㎡ 초과 또는 전용면적 미상(보수적으로 2%)


def get_metro_transport_charge(
    *,
    sido_name: str,
    gfa_sqm: float,
    building_type: str = "apartment",
    exclusive_area_sqm: float | None = None,
    standard_build_cost_won_per_sqm: int | None = None,
) -> dict[str, Any]:
    """광역교통시설부담금 = 표준건축비 × 부과율 × 건축연면적(대도시권만).

    · 비대도시권 → amount_won=0(미부과·applicable False).
    · 표준건축비 미설정(고시값 미주입) 또는 연면적≤0 → amount_won=None(무목업·정직 unavailable).
    · 그 외 → 실산식 산정. (v1은 공제·감면 미반영 = 보수적 상한.)
    """
    is_housing = building_type in _METRO_HOUSING_TYPES
    sido_name = normalize_sido_short(sido_name)  # 완전명("서울특별시") 입력도 대도시권 정상 판정
    if sido_name not in METRO_AREA_SIDO:
        return {
            "amount_won": 0, "applicable": False, "source": "not_metro_area",
            "reason": f"{sido_name or '지역미상'} — 대도시권 아님(광역교통시설부담금 미부과)",
        }
    rate = metro_transport_charge_rate(is_housing=is_housing, exclusive_area_sqm=exclusive_area_sqm)
    scb = standard_build_cost_won_per_sqm or METRO_STANDARD_BUILD_COST_WON_PER_SQM
    if not scb or gfa_sqm <= 0:
        return {
            "amount_won": None, "applicable": True, "confidence": "unavailable", "rate": rate,
            "formula": "표준건축비 × 부과율 × 건축연면적 − 공제",
            "reason": ("표준건축비 국토부 고시값(제2024-192호 계열) 미설정 — "
                       "고시값 주입 시 '표준건축비×부과율×건축연면적'으로 산정"),
        }
    amount = int(round(scb * rate * gfa_sqm))
    return {
        "amount_won": amount, "applicable": True, "confidence": "regional", "rate": rate,
        "standard_build_cost_won_per_sqm": scb, "gfa_sqm": gfa_sqm, "source": "formula",
        "formula": "표준건축비 × 부과율 × 건축연면적 − 공제(v1 공제·감면 미반영)",
    }


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
) -> int | None:
    """상하수도 원인자부담금 단가 조회 (시군구 → 시도).

    ★반환 None = 등록된 지자체 단가 없음. 상하수도 원인자부담금은 수도법 §71·하수도법 §61이
    산정을 지자체 조례에 위임하므로 '전국 단일 표준값'이 존재하지 않는다. 미등록 지역에 임의
    폴백값을 반환하면 무목업 위반(지어낸 값)이므로 None을 돌려 소비처가 정직 처리하게 한다.
    """
    sido_short = normalize_sido_short(sido_name)  # 완전명 입력도 축약 키 테이블에 매칭
    sigungu_key = f"{sido_short}_{sigungu_name}"
    if sigungu_key in charge_map:
        return charge_map[sigungu_key]
    if sido_short in charge_map:
        return charge_map[sido_short]
    return None  # 조례 미등록 — 임의 전국폴백 금지(무목업)


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

# 별칭(하위호환): 현행 최신본 — (하한 만원, 세율, 누진공제 만원).
# 정본은 tax_rules_versions.json 'capital_gains_brackets'(시행일 메타 포함).
CAPITAL_GAINS_BRACKETS: list[tuple[float, float, float]] = [
    tuple(row) for row in get_rule("capital_gains_brackets")["value"]
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


# ── 종합부동산세: 종합합산 토지(나대지) 기준 ──
# 개발사업은 착공 전 토지가 통상 '나대지=종합합산' → 공제 5억, 누진 1/2/3%.
# (주택건설사업용 토지는 종부세 비과세 특례가 있을 수 있어 별도 적용 — note 명시)
# 정본은 tax_rules_versions.json 'land_comprehensive_tax'(시행일 메타 포함).


def _land_brackets_from_value(value: dict[str, Any]) -> list[tuple[float, float, int]]:
    """JSON 브래킷([한도(null=무한), 세율, 누진공제]) → 기존 튜플 구조 복원."""
    return [
        (float("inf") if row[0] is None else row[0], row[1], row[2])
        for row in value["brackets"]
    ]


_LAND_COMPREHENSIVE_CURRENT = get_rule("land_comprehensive_tax")["value"]

# 별칭(하위호환): 현행 최신본.
LAND_COMPREHENSIVE_DEDUCTION_WON = int(_LAND_COMPREHENSIVE_CURRENT["deduction_won"])  # 종합합산 토지 공제(공시가격 기준)
LAND_FAIR_MARKET_RATIO = float(_LAND_COMPREHENSIVE_CURRENT["fair_market_ratio"])      # 토지 공정시장가액비율(현행)
# (과세표준 한도, 세율, 누진공제) — 종합합산토지
LAND_COMPREHENSIVE_TAX_BRACKETS: list[tuple[float, float, int]] = (
    _land_brackets_from_value(_LAND_COMPREHENSIVE_CURRENT)
)


def calc_land_comprehensive_property_tax(
    assessed_value_won: int,
    *,
    deduction_won: int | None = None,
    fair_market_ratio: float | None = None,
    holding_years: int = 1,
    as_of: date | None = None,
) -> dict[str, Any]:
    """종합합산 토지 종합부동산세(연간·합산). 공제 이하면 0(구조적 정확).

    과세표준 = max(0, 공시가격합산 − 공제) × 공정시장가액비율 → 누진세율 적용.

    additive: as_of 지정 시 해당 시점 버전드 룰(공제·비율·브래킷) 적용.
    None이면 현행 별칭 사용 — 기존 동작 완전 동일. deduction_won/fair_market_ratio를
    명시하면 그 값이 버전값보다 우선한다(기존 호출 계약 유지).
    """
    if as_of is None:
        brackets = LAND_COMPREHENSIVE_TAX_BRACKETS
        default_deduction = LAND_COMPREHENSIVE_DEDUCTION_WON
        default_ratio = LAND_FAIR_MARKET_RATIO
    else:
        versioned = get_rule("land_comprehensive_tax", as_of=as_of)["value"]
        brackets = _land_brackets_from_value(versioned)
        default_deduction = int(versioned["deduction_won"])
        default_ratio = float(versioned["fair_market_ratio"])

    if deduction_won is None:
        deduction_won = default_deduction
    if fair_market_ratio is None:
        fair_market_ratio = default_ratio

    taxable = max(0.0, (assessed_value_won - deduction_won)) * fair_market_ratio
    annual = 0
    rate_applied = 0.0
    for limit, rate, prog in brackets:
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
