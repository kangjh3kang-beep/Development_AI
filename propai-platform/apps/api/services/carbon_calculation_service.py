"""탄소 배출량 산출 서비스.

건축자재별 탄소 배출 계수를 적용하여
건물 생애주기 탄소 배출량을 산출한다.

흐름:
1. BIM/IFC 물량산출 결과 참조
2. 자재별 탄소 배출 계수 적용
3. 운영 단계 탄소 배출 추정
4. 탄소 저감 방안 제시
"""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings

logger = structlog.get_logger(__name__)

# ──────────────────────────────────────────────
# Ecoinvent v3.10 기반 주요 건축자재 GWP 계수 (kgCO2eq/kg)
# ──────────────────────────────────────────────
ECOINVENT_GWP_DB = {
    # 콘크리트
    "concrete_c30": {"gwp": 0.130, "unit": "kg", "category": "콘크리트", "name": "레미콘 C30"},
    "concrete_c40": {"gwp": 0.155, "unit": "kg", "category": "콘크리트", "name": "레미콘 C40"},
    "concrete_c50": {"gwp": 0.180, "unit": "kg", "category": "콘크리트", "name": "레미콘 C50"},
    "concrete_low_carbon": {"gwp": 0.090, "unit": "kg", "category": "콘크리트", "name": "저탄소 콘크리트"},
    # 철강
    "steel_rebar": {"gwp": 1.800, "unit": "kg", "category": "철강", "name": "철근"},
    "steel_structural": {"gwp": 2.100, "unit": "kg", "category": "철강", "name": "구조용 강재"},
    "steel_recycled": {"gwp": 0.700, "unit": "kg", "category": "철강", "name": "재활용 강재"},
    "stainless_steel": {"gwp": 6.150, "unit": "kg", "category": "철강", "name": "스테인리스강"},
    # 목재
    "timber_softwood": {"gwp": -1.500, "unit": "kg", "category": "목재", "name": "침엽수 목재"},
    "timber_glulam": {"gwp": -1.200, "unit": "kg", "category": "목재", "name": "집성목"},
    "timber_clt": {"gwp": -1.000, "unit": "kg", "category": "목재", "name": "CLT"},
    "plywood": {"gwp": 0.450, "unit": "kg", "category": "목재", "name": "합판"},
    # 단열재
    "insulation_eps": {"gwp": 3.300, "unit": "kg", "category": "단열재", "name": "EPS"},
    "insulation_xps": {"gwp": 3.800, "unit": "kg", "category": "단열재", "name": "XPS"},
    "insulation_mineral_wool": {"gwp": 1.200, "unit": "kg", "category": "단열재", "name": "미네랄울"},
    "insulation_cellulose": {"gwp": 0.300, "unit": "kg", "category": "단열재", "name": "셀룰로오스"},
    # 유리
    "glass_float": {"gwp": 1.200, "unit": "kg", "category": "유리", "name": "플로트유리"},
    "glass_low_e": {"gwp": 1.500, "unit": "kg", "category": "유리", "name": "로이유리"},
    "glass_triple": {"gwp": 2.000, "unit": "kg", "category": "유리", "name": "삼중유리"},
    # 벽돌/석재
    "brick_clay": {"gwp": 0.240, "unit": "kg", "category": "벽돌", "name": "점토벽돌"},
    "brick_concrete": {"gwp": 0.120, "unit": "kg", "category": "벽돌", "name": "콘크리트 블록"},
    "stone_granite": {"gwp": 0.700, "unit": "kg", "category": "석재", "name": "화강석"},
    # 시멘트
    "cement_opc": {"gwp": 0.900, "unit": "kg", "category": "시멘트", "name": "보통 포틀랜드 시멘트"},
    "cement_blended": {"gwp": 0.550, "unit": "kg", "category": "시멘트", "name": "혼합 시멘트"},
    # 알루미늄
    "aluminum_primary": {"gwp": 8.240, "unit": "kg", "category": "알루미늄", "name": "1차 알루미늄"},
    "aluminum_recycled": {"gwp": 0.700, "unit": "kg", "category": "알루미늄", "name": "재활용 알루미늄"},
    # 방수/도장
    "asphalt_waterproofing": {"gwp": 0.500, "unit": "kg", "category": "방수", "name": "아스팔트 방수"},
    "paint_acrylic": {"gwp": 2.500, "unit": "kg", "category": "도장", "name": "아크릴 도료"},
    # 기타
    "copper_pipe": {"gwp": 3.800, "unit": "kg", "category": "배관", "name": "동관"},
    "pvc_pipe": {"gwp": 2.300, "unit": "kg", "category": "배관", "name": "PVC관"},
}

# ──────────────────────────────────────────────
# 탄소 등급 기준 (kgCO2eq/m² 기준)
# ──────────────────────────────────────────────
CARBON_GRADE_THRESHOLDS = {
    "A+": 300,   # <= 300
    "A": 500,    # <= 500
    "B": 700,    # <= 700
    "C": 1000,   # <= 1000
    "D": float("inf"),  # > 1000
}

# ──────────────────────────────────────────────
# 고탄소 → 저탄소 대안 매핑
# ──────────────────────────────────────────────
LOW_CARBON_ALTERNATIVES = {
    "concrete_c30": ["concrete_low_carbon"],
    "concrete_c40": ["concrete_low_carbon"],
    "concrete_c50": ["concrete_low_carbon"],
    "steel_rebar": ["steel_recycled"],
    "steel_structural": ["steel_recycled"],
    "aluminum_primary": ["aluminum_recycled"],
    "insulation_eps": ["insulation_mineral_wool", "insulation_cellulose"],
    "insulation_xps": ["insulation_mineral_wool", "insulation_cellulose"],
    "cement_opc": ["cement_blended"],
    "glass_float": ["glass_low_e"],
}

# 건축자재별 탄소 배출 계수 (kgCO2e/단위)
_CARBON_FACTORS = {
    "IfcWall": {"factor": 120.0, "unit": "m³", "description": "콘크리트 벽체"},
    "IfcSlab": {"factor": 130.0, "unit": "m³", "description": "콘크리트 슬래브"},
    "IfcBeam": {"factor": 140.0, "unit": "m³", "description": "콘크리트 보"},
    "IfcColumn": {"factor": 150.0, "unit": "m³", "description": "콘크리트 기둥"},
    "IfcWindow": {"factor": 45.0, "unit": "m²", "description": "유리 창호"},
    "IfcDoor": {"factor": 35.0, "unit": "m²", "description": "문"},
    "IfcRoof": {"factor": 110.0, "unit": "m²", "description": "지붕"},
    "IfcStair": {"factor": 100.0, "unit": "m³", "description": "계단"},
}


class CarbonCalculationResult:
    """탄소 산출 결과."""
    def __init__(
        self,
        total_embodied_carbon: float,
        total_operational_carbon: float,
        breakdown: list[dict],
        reduction_tips: list[str],
    ):
        self.total_embodied_carbon = total_embodied_carbon
        self.total_operational_carbon = total_operational_carbon
        self.total_carbon = total_embodied_carbon + total_operational_carbon
        self.breakdown = breakdown
        self.reduction_tips = reduction_tips


class CarbonCalculationService:
    """탄소 배출량 산출 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    # ──────────────────────────────────────────────
    # T3-1: Ecoinvent GWP 조회 / 탄소 등급 산출
    # ──────────────────────────────────────────────

    @staticmethod
    def grade_carbon(total_kgco2e: float, gross_floor_area_sqm: float) -> dict:
        """탄소 등급을 산출한다."""
        if gross_floor_area_sqm <= 0:
            return {"intensity_kgco2e_m2": 0, "grade": "N/A"}
        intensity = total_kgco2e / gross_floor_area_sqm
        grade = "D"
        for g, threshold in CARBON_GRADE_THRESHOLDS.items():
            if intensity <= threshold:
                grade = g
                break
        return {"intensity_kgco2e_m2": round(intensity, 2), "grade": grade}

    @staticmethod
    def lookup_gwp(material_key: str) -> dict | None:
        """Ecoinvent GWP DB에서 자재를 검색한다."""
        return ECOINVENT_GWP_DB.get(material_key)

    @staticmethod
    def calculate_material_carbon(material_key: str, weight_kg: float) -> float:
        """자재별 탄소 배출량을 계산한다."""
        entry = ECOINVENT_GWP_DB.get(material_key)
        if not entry:
            return 0.0
        return round(weight_kg * entry["gwp"], 4)

    # ──────────────────────────────────────────────
    # T3-2: 저탄소 자재 자동 추천
    # ──────────────────────────────────────────────

    @staticmethod
    def recommend_low_carbon_alternatives(material_keys: list[str]) -> list[dict]:
        """고탄소 자재에 대한 저탄소 대안을 추천한다."""
        recommendations = []
        for key in material_keys:
            original = ECOINVENT_GWP_DB.get(key)
            alternatives = LOW_CARBON_ALTERNATIVES.get(key, [])
            if original and alternatives:
                for alt_key in alternatives:
                    alt = ECOINVENT_GWP_DB.get(alt_key)
                    if alt:
                        reduction = round((1 - alt["gwp"] / original["gwp"]) * 100, 1) if original["gwp"] > 0 else 0
                        recommendations.append({
                            "original_material": key,
                            "original_name": original["name"],
                            "original_gwp": original["gwp"],
                            "alternative_material": alt_key,
                            "alternative_name": alt["name"],
                            "alternative_gwp": alt["gwp"],
                            "gwp_reduction_percent": reduction,
                        })
        return sorted(recommendations, key=lambda x: x["gwp_reduction_percent"], reverse=True)

    # ──────────────────────────────────────────────
    # 기존 메서드
    # ──────────────────────────────────────────────

    def _calculate_embodied_carbon(self, material_breakdown: list[dict]) -> tuple[float, list[dict]]:
        """내재 탄소(생산 단계)를 계산한다."""
        breakdown = []
        total = 0.0

        for material in material_breakdown:
            element_type = material.get("type", "")
            factor_info = _CARBON_FACTORS.get(element_type)

            if factor_info:
                # 체적 또는 면적 기반 계산
                quantity = material.get("volume_m3", 0) or material.get("area_sqm", 0)
                carbon = quantity * factor_info["factor"]
                total += carbon
                breakdown.append({
                    "element_type": element_type,
                    "description": factor_info["description"],
                    "quantity": quantity,
                    "unit": factor_info["unit"],
                    "factor": factor_info["factor"],
                    "carbon_kgco2e": carbon,
                })

        return total, breakdown

    def _estimate_operational_carbon(self, total_area_sqm: float, lifespan_years: int = 60) -> float:
        """운영 단계 탄소 배출을 추정한다.

        한국 평균 건물 에너지 사용량 기준: ~120 kWh/㎡/년
        전력 탄소 배출 계수: ~0.46 kgCO2e/kWh (한국전력 2025)
        """
        annual_energy_kwh = total_area_sqm * 120  # kWh/년
        annual_carbon = annual_energy_kwh * 0.46    # kgCO2e/년
        return annual_carbon * lifespan_years

    async def _generate_reduction_tips(self, total_carbon: float, breakdown: list[dict]) -> list[str]:
        """탄소 저감 방안을 생성한다."""
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            model="claude-sonnet-4-5-20250929",
            api_key=self.settings.anthropic_api_key,
            temperature=0.3,
        )

        top_emitters = sorted(breakdown, key=lambda x: x["carbon_kgco2e"], reverse=True)[:3]
        top_text = "\n".join(
            f"- {e['description']}: {e['carbon_kgco2e']:,.0f} kgCO2e"
            for e in top_emitters
        )

        prompt = f"""건축 탄소 저감 전문가로서, 다음 건물의 탄소 저감 방안 5가지를 제시하세요.

총 탄소 배출량: {total_carbon:,.0f} kgCO2e
주요 배출원:
{top_text}

한국어로 간결하게 작성하세요."""

        try:
            response = await llm.ainvoke(prompt)
            tips = [
                line.strip().lstrip("0123456789.•-·) ")
                for line in response.content.strip().split("\n")
                if line.strip() and len(line.strip()) > 5
            ]
            return tips[:5]
        except Exception:
            return ["저탄소 콘크리트 사용 검토", "재생에너지 도입 검토", "단열 성능 강화"]

    async def calculate(
        self,
        project_id: UUID,
        tenant_id: UUID,
        material_breakdown: list[dict],
        total_area_sqm: float,
    ) -> CarbonCalculationResult:
        """탄소 배출량을 산출한다."""
        logger.info("탄소 산출 시작", project_id=str(project_id))

        embodied, breakdown = self._calculate_embodied_carbon(material_breakdown)
        operational = self._estimate_operational_carbon(total_area_sqm)
        total = embodied + operational

        tips = await self._generate_reduction_tips(total, breakdown)

        logger.info("탄소 산출 완료", total_kgco2e=total)

        return CarbonCalculationResult(
            total_embodied_carbon=embodied,
            total_operational_carbon=operational,
            breakdown=breakdown,
            reduction_tips=tips,
        )
