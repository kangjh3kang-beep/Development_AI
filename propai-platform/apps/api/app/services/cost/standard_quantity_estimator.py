"""건축 개요 기반 표준 물량 추정 엔진.

건축 개요만으로 표준 물량을 추정하는 개산견적 엔진.
IFC 도면 없이도 건물유형+연면적+층수만으로 주요 공종 물량을 추정한다.
추후 IFC 업로드 시 실제 물량으로 대체된다.

참조: 한국건설기술연구원 건축공사 표준물량 기준
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class QuantityItem:
    """추정 물량 항목."""

    work_code: str
    item_name: str
    spec: str
    unit: str
    quantity: float
    mat_unit: float   # 재료 단가 (원)
    labor_unit: float  # 노무 단가 (원)
    exp_unit: float    # 경비 단가 (원)

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_code": self.work_code,
            "item_name": self.item_name,
            "spec": self.spec,
            "unit": self.unit,
            "quantity": self.quantity,
            "mat_unit": self.mat_unit,
            "labor_unit": self.labor_unit,
            "exp_unit": self.exp_unit,
        }


# ── 건물유형별 ㎡당 표준 물량 (개산 기준) ──

STANDARD_QUANTITIES: dict[str, dict[str, float]] = {
    "아파트": {
        "concrete_m3_per_sqm": 0.45,     # 콘크리트
        "rebar_kg_per_sqm": 75,          # 철근
        "formwork_sqm_per_sqm": 2.8,     # 거푸집
        "masonry_sqm_per_sqm": 0.5,      # 조적
        "waterproof_sqm_per_sqm": 0.15,  # 방수
        "window_sqm_per_sqm": 0.12,      # 창호
        "mep_ratio": 0.35,               # 기계설비 비율
        "elec_ratio": 0.15,              # 전기설비 비율
    },
    "오피스텔": {
        "concrete_m3_per_sqm": 0.42,
        "rebar_kg_per_sqm": 70,
        "formwork_sqm_per_sqm": 2.6,
        "masonry_sqm_per_sqm": 0.45,
        "waterproof_sqm_per_sqm": 0.12,
        "window_sqm_per_sqm": 0.18,
        "mep_ratio": 0.38,
        "elec_ratio": 0.17,
    },
    "근린생활시설": {
        "concrete_m3_per_sqm": 0.35,
        "rebar_kg_per_sqm": 55,
        "formwork_sqm_per_sqm": 2.2,
        "masonry_sqm_per_sqm": 0.55,
        "waterproof_sqm_per_sqm": 0.10,
        "window_sqm_per_sqm": 0.20,
        "mep_ratio": 0.30,
        "elec_ratio": 0.15,
    },
    "다세대주택": {
        "concrete_m3_per_sqm": 0.38,
        "rebar_kg_per_sqm": 60,
        "formwork_sqm_per_sqm": 2.4,
        "masonry_sqm_per_sqm": 0.48,
        "waterproof_sqm_per_sqm": 0.14,
        "window_sqm_per_sqm": 0.13,
        "mep_ratio": 0.32,
        "elec_ratio": 0.14,
    },
    "공동주택": {
        "concrete_m3_per_sqm": 0.43,
        "rebar_kg_per_sqm": 72,
        "formwork_sqm_per_sqm": 2.7,
        "masonry_sqm_per_sqm": 0.50,
        "waterproof_sqm_per_sqm": 0.14,
        "window_sqm_per_sqm": 0.12,
        "mep_ratio": 0.34,
        "elec_ratio": 0.15,
    },
}

# ── 구조유형별 보정계수 ──

STRUCTURE_FACTORS: dict[str, float] = {
    "RC": 1.00,   # 철근콘크리트 (기준)
    "SRC": 1.15,  # 철골철근콘크리트
    "SC": 1.10,   # 철골
    "PC": 0.92,   # 프리캐스트 콘크리트
    "목구조": 0.70,
}

# ── 2026년 기준 자재 단가 (원) ──

UNIT_PRICES_2026: dict[str, dict[str, float]] = {
    "concrete": {
        "spec": "25-24-15 레미콘",
        "unit": "m3",
        "mat_unit": 85_000,
        "labor_unit": 35_000,
        "exp_unit": 12_000,
    },
    "rebar": {
        "spec": "SD400 D10~D25",
        "unit": "ton",
        "mat_unit": 950_000,
        "labor_unit": 280_000,
        "exp_unit": 70_000,
    },
    "formwork": {
        "spec": "유로폼 (1회용)",
        "unit": "m2",
        "mat_unit": 12_000,
        "labor_unit": 22_000,
        "exp_unit": 4_000,
    },
    "masonry": {
        "spec": "시멘트벽돌 190×90×57",
        "unit": "m2",
        "mat_unit": 18_000,
        "labor_unit": 32_000,
        "exp_unit": 5_000,
    },
    "waterproof": {
        "spec": "우레탄 방수",
        "unit": "m2",
        "mat_unit": 15_000,
        "labor_unit": 18_000,
        "exp_unit": 3_000,
    },
    "window": {
        "spec": "AL 이중창 24mm 로이",
        "unit": "m2",
        "mat_unit": 180_000,
        "labor_unit": 45_000,
        "exp_unit": 15_000,
    },
}


class StandardQuantityEstimator:
    """건축 개요만으로 표준 물량을 추정하는 개산견적 엔진.

    IFC 도면 없이도 건물유형+연면적+층수만으로 주요 공종 물량을 추정한다.
    추후 IFC 업로드 시 실제 물량으로 대체된다.
    """

    def estimate(
        self,
        building_type: str,
        total_gfa_sqm: float,
        floor_count_above: int,
        floor_count_below: int = 1,
        structure_type: str = "RC",
    ) -> list[dict[str, Any]]:
        """건축 개요로 공종별 물량을 추정한다.

        Args:
            building_type: 건물유형 (아파트/오피스텔/근린생활시설/다세대주택/공동주택)
            total_gfa_sqm: 연면적 (㎡)
            floor_count_above: 지상 층수
            floor_count_below: 지하 층수 (기본 1)
            structure_type: 구조유형 (RC/SRC/SC/PC/목구조)

        Returns:
            CostItem 호환 dict 리스트
        """
        # 1. 건물유형별 표준물량 참조
        std = STANDARD_QUANTITIES.get(building_type, STANDARD_QUANTITIES["공동주택"])

        # 2. 구조유형 보정계수
        struct_factor = STRUCTURE_FACTORS.get(structure_type, 1.0)

        # 3. 고층 보정계수 (15층 이상 시 구조비 증가)
        height_factor = 1.0
        if floor_count_above >= 15:
            height_factor = 1.0 + (floor_count_above - 15) * 0.008
        elif floor_count_above >= 30:
            height_factor = 1.12 + (floor_count_above - 30) * 0.005

        # 4. 지하층 보정 (지하 면적을 총 연면적의 일정 비율로 추정)
        underground_area = total_gfa_sqm * (floor_count_below * 0.15)
        effective_area = total_gfa_sqm + underground_area * 0.3  # 지하는 30% 가중

        # 5. 공종별 물량 산출
        items: list[dict[str, Any]] = []

        # 5-1. 콘크리트
        concrete_qty = effective_area * std["concrete_m3_per_sqm"] * struct_factor * height_factor
        prices = UNIT_PRICES_2026["concrete"]
        items.append(QuantityItem(
            work_code="01-콘크리트",
            item_name="레미콘 타설",
            spec=prices["spec"],
            unit=prices["unit"],
            quantity=round(concrete_qty, 1),
            mat_unit=prices["mat_unit"],
            labor_unit=prices["labor_unit"],
            exp_unit=prices["exp_unit"],
        ).to_dict())

        # 5-2. 철근
        rebar_qty_kg = effective_area * std["rebar_kg_per_sqm"] * struct_factor * height_factor
        rebar_qty_ton = rebar_qty_kg / 1000
        prices = UNIT_PRICES_2026["rebar"]
        items.append(QuantityItem(
            work_code="02-철근",
            item_name="철근 가공 및 조립",
            spec=prices["spec"],
            unit=prices["unit"],
            quantity=round(rebar_qty_ton, 2),
            mat_unit=prices["mat_unit"],
            labor_unit=prices["labor_unit"],
            exp_unit=prices["exp_unit"],
        ).to_dict())

        # 5-3. 거푸집
        formwork_qty = effective_area * std["formwork_sqm_per_sqm"] * struct_factor
        prices = UNIT_PRICES_2026["formwork"]
        items.append(QuantityItem(
            work_code="03-거푸집",
            item_name="거푸집 설치 및 해체",
            spec=prices["spec"],
            unit=prices["unit"],
            quantity=round(formwork_qty, 1),
            mat_unit=prices["mat_unit"],
            labor_unit=prices["labor_unit"],
            exp_unit=prices["exp_unit"],
        ).to_dict())

        # 5-4. 조적
        masonry_qty = total_gfa_sqm * std["masonry_sqm_per_sqm"]
        prices = UNIT_PRICES_2026["masonry"]
        items.append(QuantityItem(
            work_code="04-조적",
            item_name="벽돌 쌓기",
            spec=prices["spec"],
            unit=prices["unit"],
            quantity=round(masonry_qty, 1),
            mat_unit=prices["mat_unit"],
            labor_unit=prices["labor_unit"],
            exp_unit=prices["exp_unit"],
        ).to_dict())

        # 5-5. 방수
        waterproof_qty = total_gfa_sqm * std["waterproof_sqm_per_sqm"]
        prices = UNIT_PRICES_2026["waterproof"]
        items.append(QuantityItem(
            work_code="05-방수",
            item_name="우레탄 방수",
            spec=prices["spec"],
            unit=prices["unit"],
            quantity=round(waterproof_qty, 1),
            mat_unit=prices["mat_unit"],
            labor_unit=prices["labor_unit"],
            exp_unit=prices["exp_unit"],
        ).to_dict())

        # 5-6. 창호
        window_qty = total_gfa_sqm * std["window_sqm_per_sqm"]
        prices = UNIT_PRICES_2026["window"]
        items.append(QuantityItem(
            work_code="06-창호",
            item_name="알루미늄 이중창",
            spec=prices["spec"],
            unit=prices["unit"],
            quantity=round(window_qty, 1),
            mat_unit=prices["mat_unit"],
            labor_unit=prices["labor_unit"],
            exp_unit=prices["exp_unit"],
        ).to_dict())

        # 5-7. 기계설비 (직접비 대비 비율로 산출)
        structural_direct = sum(
            it["quantity"] * (it["mat_unit"] + it["labor_unit"] + it["exp_unit"])
            for it in items
        )
        mep_cost = structural_direct * std["mep_ratio"]
        items.append(QuantityItem(
            work_code="07-기계설비",
            item_name="기계설비 일식",
            spec="공조/위생/소방",
            unit="식",
            quantity=1,
            mat_unit=round(mep_cost * 0.55),
            labor_unit=round(mep_cost * 0.35),
            exp_unit=round(mep_cost * 0.10),
        ).to_dict())

        # 5-8. 전기설비
        elec_cost = structural_direct * std["elec_ratio"]
        items.append(QuantityItem(
            work_code="08-전기설비",
            item_name="전기설비 일식",
            spec="수변전/조명/통신",
            unit="식",
            quantity=1,
            mat_unit=round(elec_cost * 0.50),
            labor_unit=round(elec_cost * 0.35),
            exp_unit=round(elec_cost * 0.15),
        ).to_dict())

        return items

    def estimate_summary(
        self,
        building_type: str,
        total_gfa_sqm: float,
        floor_count_above: int,
        floor_count_below: int = 1,
        structure_type: str = "RC",
    ) -> dict[str, Any]:
        """물량 추정 요약 정보를 반환한다."""
        items = self.estimate(
            building_type=building_type,
            total_gfa_sqm=total_gfa_sqm,
            floor_count_above=floor_count_above,
            floor_count_below=floor_count_below,
            structure_type=structure_type,
        )

        total_direct = sum(
            it["quantity"] * (it["mat_unit"] + it["labor_unit"] + it["exp_unit"])
            for it in items
        )
        total_pyeong = total_gfa_sqm / 3.3058

        return {
            "building_type": building_type,
            "structure_type": structure_type,
            "total_gfa_sqm": total_gfa_sqm,
            "total_gfa_pyeong": round(total_pyeong, 1),
            "floor_count_above": floor_count_above,
            "floor_count_below": floor_count_below,
            "item_count": len(items),
            "estimated_direct_cost": round(total_direct),
            "estimated_direct_cost_per_pyeong": round(total_direct / total_pyeong) if total_pyeong > 0 else 0,
            "items": items,
        }
