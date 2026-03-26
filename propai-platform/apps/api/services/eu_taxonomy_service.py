"""EU Taxonomy 적합성 검증 서비스.

EU 택소노미 기술 심사 기준(TSC)에 따라 건축물의
기후변화 완화/적응 적합성을 검증한다.

6대 환경목표:
1. 기후변화 완화 (Climate Change Mitigation)
2. 기후변화 적응 (Climate Change Adaptation)
3. 수자원 및 해양자원 (Water and Marine Resources)
4. 순환경제 (Circular Economy)
5. 오염 방지 (Pollution Prevention)
6. 생태계 보호 (Biodiversity and Ecosystems)

DNSH (Do No Significant Harm) 원칙 + Minimum Social Safeguards
"""

from dataclasses import dataclass, field
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings

logger = structlog.get_logger(__name__)

# TSC 기준값
NZEB_BASELINE_KWH_M2 = 120.0  # 한국 NZEB 기준 (kWh/m2/yr)
TSC_PED_THRESHOLD = NZEB_BASELINE_KWH_M2 * 0.90  # NZEB -10% = 108
TSC_RE_THRESHOLD = 0.20  # 재생에너지 비율 20% 이상
TSC_WASTE_RECYCLING_THRESHOLD = 0.70  # 건설 폐기물 재활용 70%
TSC_GREEN_RATIO_THRESHOLD = 0.30  # 녹지율 30%
TSC_WATER_USAGE_THRESHOLD = 500.0  # 일일 물 사용량 기준 (L/person/day)


@dataclass
class BuildingData:
    """건축물 데이터. EU Taxonomy 검증 입력."""

    primary_energy_demand_kwh_m2: float  # 1차 에너지 소요량
    renewable_energy_ratio: float  # 재생에너지 비율 (0~1)
    embodied_carbon_kgco2e_m2: float  # 내재탄소 (kgCO2e/m2)
    water_usage_liters_per_day: float  # 일일 물 사용량
    waste_recycling_rate: float  # 건설 폐기물 재활용률 (0~1)
    green_ratio: float  # 녹지율 (0~1)
    has_climate_risk_assessment: bool  # 기후위험 평가 여부
    has_social_safeguards: bool  # 사회적 안전장치 (ILO 핵심 노동 기준)
    gross_floor_area_sqm: float  # 연면적 (m2)


@dataclass
class TaxonomyCriterion:
    """개별 검증 기준 결과."""

    name: str
    category: str  # "TSC", "DNSH", "MSS"
    passed: bool
    actual_value: float | str
    threshold: float | str
    rationale: str


@dataclass
class TaxonomyResult:
    """EU Taxonomy 검증 종합 결과."""

    alignment: str  # "Aligned", "Partially Aligned", "Not Aligned"
    criteria: list[TaxonomyCriterion]
    passed_count: int
    total_count: int
    recommendations: list[str]


class EuTaxonomyChecker:
    """EU Taxonomy 적합성 검증 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    @staticmethod
    def _check_ped(building: BuildingData) -> TaxonomyCriterion:
        """1차 에너지 소요량 검증 (TSC).

        PED <= NZEB -10% (108 kWh/m2/yr) 이면 통과.
        """
        passed = building.primary_energy_demand_kwh_m2 <= TSC_PED_THRESHOLD
        return TaxonomyCriterion(
            name="1차 에너지 소요량 (PED)",
            category="TSC",
            passed=passed,
            actual_value=building.primary_energy_demand_kwh_m2,
            threshold=TSC_PED_THRESHOLD,
            rationale=(
                f"PED {building.primary_energy_demand_kwh_m2} kWh/m2 "
                f"{'<=' if passed else '>'} "
                f"기준 {TSC_PED_THRESHOLD} kWh/m2 (NZEB -10%)"
            ),
        )

    @staticmethod
    def _check_re(building: BuildingData) -> TaxonomyCriterion:
        """재생에너지 비율 검증 (TSC).

        재생에너지 비율 >= 20% 이면 통과.
        """
        passed = building.renewable_energy_ratio >= TSC_RE_THRESHOLD
        return TaxonomyCriterion(
            name="재생에너지 비율",
            category="TSC",
            passed=passed,
            actual_value=building.renewable_energy_ratio,
            threshold=TSC_RE_THRESHOLD,
            rationale=(
                f"재생에너지 비율 {building.renewable_energy_ratio:.1%} "
                f"{'>=' if passed else '<'} "
                f"기준 {TSC_RE_THRESHOLD:.0%}"
            ),
        )

    @staticmethod
    def _check_embodied_carbon(building: BuildingData) -> TaxonomyCriterion:
        """내재탄소 공개 여부 검증 (TSC).

        내재탄소(EC) 값이 0보다 크면 공개 의무 충족으로 판정한다.
        """
        passed = building.embodied_carbon_kgco2e_m2 > 0
        return TaxonomyCriterion(
            name="내재탄소 공개 (EC Disclosure)",
            category="TSC",
            passed=passed,
            actual_value=building.embodied_carbon_kgco2e_m2,
            threshold="공개 필수 (> 0)",
            rationale=(
                f"내재탄소 {building.embodied_carbon_kgco2e_m2} kgCO2e/m2 — "
                f"{'공개됨' if passed else '미공개 (0 이하)'}"
            ),
        )

    @staticmethod
    def _check_water(building: BuildingData) -> TaxonomyCriterion:
        """수자원 사용량 검증 (DNSH).

        일일 물 사용량 <= 500 L/person/day 이면 통과.
        """
        passed = building.water_usage_liters_per_day <= TSC_WATER_USAGE_THRESHOLD
        return TaxonomyCriterion(
            name="수자원 사용량",
            category="DNSH",
            passed=passed,
            actual_value=building.water_usage_liters_per_day,
            threshold=TSC_WATER_USAGE_THRESHOLD,
            rationale=(
                f"일일 물 사용량 {building.water_usage_liters_per_day} L/person/day "
                f"{'<=' if passed else '>'} "
                f"기준 {TSC_WATER_USAGE_THRESHOLD} L/person/day"
            ),
        )

    @staticmethod
    def _check_waste(building: BuildingData) -> TaxonomyCriterion:
        """건설 폐기물 재활용률 검증 (DNSH).

        재활용률 >= 70% 이면 통과.
        """
        passed = building.waste_recycling_rate >= TSC_WASTE_RECYCLING_THRESHOLD
        return TaxonomyCriterion(
            name="건설 폐기물 재활용률",
            category="DNSH",
            passed=passed,
            actual_value=building.waste_recycling_rate,
            threshold=TSC_WASTE_RECYCLING_THRESHOLD,
            rationale=(
                f"재활용률 {building.waste_recycling_rate:.0%} "
                f"{'>=' if passed else '<'} "
                f"기준 {TSC_WASTE_RECYCLING_THRESHOLD:.0%}"
            ),
        )

    @staticmethod
    def _check_biodiversity(building: BuildingData) -> TaxonomyCriterion:
        """녹지율 검증 (DNSH).

        녹지율 >= 30% 이면 통과.
        """
        passed = building.green_ratio >= TSC_GREEN_RATIO_THRESHOLD
        return TaxonomyCriterion(
            name="녹지율 (생태계 보호)",
            category="DNSH",
            passed=passed,
            actual_value=building.green_ratio,
            threshold=TSC_GREEN_RATIO_THRESHOLD,
            rationale=(
                f"녹지율 {building.green_ratio:.0%} "
                f"{'>=' if passed else '<'} "
                f"기준 {TSC_GREEN_RATIO_THRESHOLD:.0%}"
            ),
        )

    @staticmethod
    def _check_climate_adaptation(building: BuildingData) -> TaxonomyCriterion:
        """기후변화 적응 검증 (DNSH).

        기후위험 평가(Climate Risk Assessment) 수행 여부를 확인한다.
        """
        passed = building.has_climate_risk_assessment
        return TaxonomyCriterion(
            name="기후변화 적응 (기후위험 평가)",
            category="DNSH",
            passed=passed,
            actual_value="수행" if passed else "미수행",
            threshold="수행 필수",
            rationale=(
                f"기후위험 평가 {'수행됨' if passed else '미수행'} — "
                f"{'DNSH 충족' if passed else 'DNSH 미충족'}"
            ),
        )

    @staticmethod
    def _check_social_safeguards(building: BuildingData) -> TaxonomyCriterion:
        """최소 사회적 안전장치 검증 (MSS).

        ILO 핵심 노동 기준, OECD 다국적기업 가이드라인,
        UN 기업과 인권 이행원칙 준수 여부를 확인한다.
        """
        passed = building.has_social_safeguards
        return TaxonomyCriterion(
            name="최소 사회적 안전장치 (MSS)",
            category="MSS",
            passed=passed,
            actual_value="준수" if passed else "미준수",
            threshold="준수 필수",
            rationale=(
                f"ILO/OECD/UN 기준 {'준수' if passed else '미준수'} — "
                f"{'MSS 충족' if passed else 'MSS 미충족'}"
            ),
        )

    @staticmethod
    def _determine_alignment(criteria: list[TaxonomyCriterion]) -> str:
        """적합성 판정.

        - Aligned: TSC 전체 + DNSH 전체 + MSS 전체 통과
        - Partially Aligned: TSC 중 하나라도 통과
        - Not Aligned: TSC 전부 실패
        """
        tsc_criteria = [c for c in criteria if c.category == "TSC"]
        dnsh_criteria = [c for c in criteria if c.category == "DNSH"]
        mss_criteria = [c for c in criteria if c.category == "MSS"]

        tsc_all_pass = all(c.passed for c in tsc_criteria)
        dnsh_all_pass = all(c.passed for c in dnsh_criteria)
        mss_all_pass = all(c.passed for c in mss_criteria)

        if tsc_all_pass and dnsh_all_pass and mss_all_pass:
            return "Aligned"
        elif any(c.passed for c in tsc_criteria):
            return "Partially Aligned"
        else:
            return "Not Aligned"

    @staticmethod
    def _generate_recommendations(criteria: list[TaxonomyCriterion]) -> list[str]:
        """실패한 기준에 대한 개선 권고사항을 생성한다."""
        recommendations = []
        for criterion in criteria:
            if not criterion.passed:
                if criterion.name == "1차 에너지 소요량 (PED)":
                    recommendations.append(
                        f"1차 에너지 소요량을 {TSC_PED_THRESHOLD} kWh/m2 이하로 낮추세요. "
                        f"고단열, 고기밀, BEMS 도입을 권장합니다."
                    )
                elif criterion.name == "재생에너지 비율":
                    recommendations.append(
                        f"재생에너지 비율을 {TSC_RE_THRESHOLD:.0%} 이상으로 확대하세요. "
                        f"태양광, 지열 시스템 도입을 검토하세요."
                    )
                elif criterion.name == "내재탄소 공개 (EC Disclosure)":
                    recommendations.append(
                        "내재탄소(Embodied Carbon) 데이터를 산출·공개하세요. "
                        "EN 15978 또는 LCA 도구를 활용하세요."
                    )
                elif criterion.name == "수자원 사용량":
                    recommendations.append(
                        f"일일 물 사용량을 {TSC_WATER_USAGE_THRESHOLD} L/person/day 이하로 절감하세요. "
                        f"절수기구, 중수도, 빗물 재활용 시스템을 도입하세요."
                    )
                elif criterion.name == "건설 폐기물 재활용률":
                    recommendations.append(
                        f"건설 폐기물 재활용률을 {TSC_WASTE_RECYCLING_THRESHOLD:.0%} 이상으로 "
                        f"높이세요. 선별 해체, 재활용 계획을 수립하세요."
                    )
                elif criterion.name == "녹지율 (생태계 보호)":
                    recommendations.append(
                        f"녹지율을 {TSC_GREEN_RATIO_THRESHOLD:.0%} 이상 확보하세요. "
                        f"옥상녹화, 벽면녹화, 생태연못 등을 검토하세요."
                    )
                elif criterion.name == "기후변화 적응 (기후위험 평가)":
                    recommendations.append(
                        "기후위험 평가(Climate Risk Assessment)를 수행하세요. "
                        "TCFD 프레임워크 기반 시나리오 분석을 권장합니다."
                    )
                elif criterion.name == "최소 사회적 안전장치 (MSS)":
                    recommendations.append(
                        "ILO 핵심 노동 기준 및 UN 기업과 인권 이행원칙 준수를 "
                        "확인하고 관련 정책을 수립·공개하세요."
                    )
        return recommendations

    @staticmethod
    def check(building: BuildingData) -> TaxonomyResult:
        """EU Taxonomy 적합성을 검증한다.

        Args:
            building: 건축물 데이터

        Returns:
            TaxonomyResult — 적합성 판정, 개별 기준 결과, 권고사항
        """
        criteria = [
            EuTaxonomyChecker._check_ped(building),
            EuTaxonomyChecker._check_re(building),
            EuTaxonomyChecker._check_embodied_carbon(building),
            EuTaxonomyChecker._check_water(building),
            EuTaxonomyChecker._check_waste(building),
            EuTaxonomyChecker._check_biodiversity(building),
            EuTaxonomyChecker._check_climate_adaptation(building),
            EuTaxonomyChecker._check_social_safeguards(building),
        ]
        alignment = EuTaxonomyChecker._determine_alignment(criteria)
        recommendations = EuTaxonomyChecker._generate_recommendations(criteria)
        passed_count = sum(1 for c in criteria if c.passed)

        logger.info(
            "EU Taxonomy 검증 완료",
            alignment=alignment,
            passed=passed_count,
            total=len(criteria),
        )

        return TaxonomyResult(
            alignment=alignment,
            criteria=criteria,
            passed_count=passed_count,
            total_count=len(criteria),
            recommendations=recommendations,
        )
