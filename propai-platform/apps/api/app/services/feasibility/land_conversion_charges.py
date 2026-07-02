"""토지 전용(농지·산지) 부담금 산식 브리지 — 순수 계산 모듈.

계획서: docs/LEGAL_ENGINE_SLOPE_FOREST_PLAN_2026-07-02.md §T4

원칙(비협상):
- 무날조: 연도별 고시 단가(대체산림자원조성비)는 하드코딩 금지 —
  ``ForestChargeRates`` 명시 주입 없으면 amount=None + 산식 설명만 반환.
- 설명가능성: 모든 반환 dict에 formula / basis / legal_ref_key /
  confidence / limitations 동반.
- 순수함수: I/O·전역상태 없음, 동일 입력 → 동일 출력(결정론).

legal_ref_key는 app.services.legal.legal_reference_registry 의 키 문자열만
참조한다(레지스트리 등록은 A-registry 담당 — 본 모듈은 키 결합만).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ForestChargeRates",
    "calc_farmland_preservation_charge",
    "calc_forest_replacement_charge",
]

# 농지보전부담금 산정기준(농지법 시행령 제53조 위임 산정방식 — 개별공시지가 비율×전용면적,
# ㎡당 상한 50,000원). ★비율은 농업진흥지역 구분에 따라 다르다: 진흥지역 내 30%, 진흥지역
# 밖 20%. 단일 30% 적용은 진흥지역 밖 농지에 과다산정이 되므로 구분 분기가 필요하다.
# 상한액(㎡당 5만원)은 법령상 고정 수치(18년째 동결).
_FARMLAND_RATE_IN_ZONE = 0.30       # 농업진흥지역 내
_FARMLAND_RATE_OUTSIDE = 0.20       # 농업진흥지역 밖
_FARMLAND_CAP_WON_PER_M2 = 50_000.0

_FOREST_TYPES = ("준보전산지", "보전산지", "산지전용제한지역")


@dataclass(frozen=True)
class ForestChargeRates:
    """대체산림자원조성비 연도별 고시 단가(원/㎡) — 호출자 명시 주입 전용.

    산림청이 매년 고시하는 단가이므로 본 모듈은 어떤 기본값도 내장하지
    않는다(무날조). 값은 '산림청 대체산림자원조성비 부과기준 고시'에서
    확인 후 주입할 것.
    """

    year: int
    junbojeon_won_per_m2: float  # 준보전산지
    bojeon_won_per_m2: float  # 보전산지
    restricted_won_per_m2: float  # 산지전용제한지역


def _validate_non_negative(**values: float) -> None:
    for name, value in values.items():
        if value is None or value < 0:
            raise ValueError(f"{name} must be a non-negative number, got {value!r}")


def calc_farmland_preservation_charge(
    *,
    official_land_price_per_m2: float,
    conversion_area_m2: float,
    in_agricultural_promotion_zone: bool | None = None,
) -> dict:
    """농지보전부담금 추정액(원) — 개별공시지가×비율(㎡당 5만원 캡)×전용면적.

    ★비율은 농업진흥지역 구분에 따라 다르다: 진흥지역 내 30%, 진흥지역 밖 20%.
    구분을 모르면(None) 안전측(높은) 30%를 적용하되 limitations에 '밖이면 20%'를
    정직 고지한다(무날조: 없는 구분을 지어내지 않고 가정을 명시).

    Args:
        official_land_price_per_m2: 개별공시지가(원/㎡).
        conversion_area_m2: 농지전용 면적(㎡).
        in_agricultural_promotion_zone: 농업진흥지역 내 여부. True=30%, False=20%,
            None=구분 미확인(30% 적용 + 정직 고지).

    Returns:
        설명가능성 필드(formula/basis/legal_ref_key/confidence/limitations)를
        동반한 추정 결과 dict. confidence="estimated" — 감면·부과 시점 등
        미반영이므로 실제 부과액은 관할청 산정으로 확정된다.
    """
    _validate_non_negative(
        official_land_price_per_m2=official_land_price_per_m2,
        conversion_area_m2=conversion_area_m2,
    )
    # 진흥지역 밖만 확정될 때 20%, 그 외(진흥지역 내 또는 미확인)는 30%(안전측).
    rate = _FARMLAND_RATE_OUTSIDE if in_agricultural_promotion_zone is False else _FARMLAND_RATE_IN_ZONE
    rate_pct = round(rate * 100)
    zone_label = (
        "농업진흥지역 내" if in_agricultural_promotion_zone is True
        else "농업진흥지역 밖" if in_agricultural_promotion_zone is False
        else "농업진흥지역 구분 미확인(안전측 30% 적용)"
    )
    raw_per_m2 = official_land_price_per_m2 * rate
    cap_applied = raw_per_m2 > _FARMLAND_CAP_WON_PER_M2
    per_m2 = _FARMLAND_CAP_WON_PER_M2 if cap_applied else raw_per_m2
    amount = per_m2 * conversion_area_m2
    limitations = [
        "감면(농지법 제38조 제6항 등 감면 대상·비율) 미반영 — 실제 부과액은 감면 적용 시 감소할 수 있음",
        "개별공시지가는 부과 시점 고시가 기준 — 입력 시점과 다를 수 있음",
        "실제 부과액은 관할 행정청(한국농어촌공사 수납) 산정으로 확정됨",
    ]
    if in_agricultural_promotion_zone is None:
        limitations.insert(
            0,
            "농업진흥지역 구분 미확인 — 안전측 30% 적용. 진흥지역 '밖' 농지는 20%이므로 "
            "구분 확정 시 재산정 필요(밖이면 과다산정).",
        )
    return {
        "charge_name": "농지보전부담금",
        "amount_won": amount,
        "per_m2_won": per_m2,
        "cap_applied": cap_applied,
        "rate_pct": rate_pct,
        "agri_promotion_zone": zone_label,
        "inputs": {
            "개별공시지가_원_per_m2": official_land_price_per_m2,
            "전용면적_m2": conversion_area_m2,
        },
        "formula": (
            f"농지보전부담금 = 개별공시지가 × {rate_pct}% (㎡당 상한 50,000원) × 전용면적 "
            f"[{zone_label}]"
        ),
        "basis": (
            "농지법 제38조(농지보전부담금) 및 농지법 시행령 제53조의 부과기준 — "
            "개별공시지가의 30%(농업진흥지역 내)/20%(밖), ㎡당 상한 50,000원"
        ),
        "legal_ref_key": "farmland_preservation_charge",
        "confidence": "estimated",
        "limitations": limitations,
    }


def calc_forest_replacement_charge(
    *,
    official_land_price_per_m2: float,
    conversion_area_m2: float,
    forest_type: str = "준보전산지",
    rates: ForestChargeRates | None = None,
) -> dict:
    """대체산림자원조성비 추정액(원) — (연도별 고시 단가 + 공시지가×0.1%)×면적.

    연도별 고시 단가는 산림청 고시이므로 본 함수에 내장하지 않는다(무날조).
    ``rates`` 를 명시 주입하지 않으면 amount_won=None 과 산식 설명·고시 확인
    안내만 반환한다.

    Args:
        official_land_price_per_m2: 개별공시지가(원/㎡).
        conversion_area_m2: 산지전용 면적(㎡).
        forest_type: "준보전산지" | "보전산지" | "산지전용제한지역".
        rates: 연도별 고시 단가(명시 주입 필수 — 미주입 시 amount=None).
    """
    _validate_non_negative(
        official_land_price_per_m2=official_land_price_per_m2,
        conversion_area_m2=conversion_area_m2,
    )
    if forest_type not in _FOREST_TYPES:
        raise ValueError(
            f"forest_type must be one of {_FOREST_TYPES}, got {forest_type!r}"
        )

    formula = (
        "대체산림자원조성비 = (연도별 고시 단가[원/㎡] + 개별공시지가 × 0.1%) × 전용면적"
    )
    basis = (
        "산지관리법 제19조(대체산림자원조성비) 및 산림청 연도별 "
        "'대체산림자원조성비 부과기준' 고시 — 단가는 준보전산지/보전산지/"
        "산지전용제한지역별로 상이"
    )
    common = {
        "charge_name": "대체산림자원조성비",
        "forest_type": forest_type,
        "inputs": {
            "개별공시지가_원_per_m2": official_land_price_per_m2,
            "전용면적_m2": conversion_area_m2,
        },
        "formula": formula,
        "basis": basis,
        "legal_ref_key": "forest_replacement_charge",
    }

    if rates is None:
        return {
            **common,
            "amount_won": None,
            "per_m2_won": None,
            "rates_year": None,
            "confidence": "unavailable",
            "limitations": [
                "연도별 고시 단가 미주입 — 산림청 '대체산림자원조성비 부과기준' 고시에서 "
                "해당 연도 단가 확인 후 ForestChargeRates로 주입해야 산정 가능"
                "(무날조 원칙상 단가 추정 금지)",
                "감면(산지관리법 제19조 감면 대상) 미반영",
            ],
        }

    unit_by_type = {
        "준보전산지": rates.junbojeon_won_per_m2,
        "보전산지": rates.bojeon_won_per_m2,
        "산지전용제한지역": rates.restricted_won_per_m2,
    }
    unit = unit_by_type[forest_type]
    # ★개별공시지가 반영비율 = 1000분의1(0.1%). 2024.7.1 개정으로 1000분의10(1%)→1000분의1로
    #   축소(공시지가 급등 부담완화). 이전엔 0.01(구법)이었으나 현행은 0.001이다.
    per_m2 = unit + official_land_price_per_m2 * 0.001
    amount = per_m2 * conversion_area_m2
    return {
        **common,
        "amount_won": amount,
        "per_m2_won": per_m2,
        "rates_year": rates.year,
        "confidence": "estimated",
        "limitations": [
            "감면(산지관리법 제19조 감면 대상·비율) 미반영 — 실제 부과액은 감면 적용 시 감소할 수 있음",
            "공시지가 가산분(0.1%=1000분의1, 2024.7.1 개정) 상한 등 연도별 고시의 세부 부과기준 미반영 가능 — 해당 연도 고시 원문 확인 필요",
            f"주입 단가 기준연도={rates.year} — 부과 시점 연도 고시와 다르면 재확인 필요",
        ],
    }
