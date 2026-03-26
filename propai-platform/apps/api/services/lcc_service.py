"""LCC 생애주기비용 산정 서비스 (ISO 15686-5).

40년 분석기간 기준 건물 생애주기 비용(초기비+유지비+에너지비+대수선비)을
실질할인율 NPV로 산출한다.

대수선 주기 스케줄:
- 전기설비: 15년 주기, 초기비의 30%
- 기계설비: 20년 주기, 초기비의 40%
- 외벽/방수: 25년 주기, 초기비의 20%
- 구조보수: 30년 주기, 초기비의 15%

대안 비교: 기본안 vs 고단열안 vs 태양광안
"""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database.models.lcc_calculation import LccCalculation

logger = structlog.get_logger(__name__)

# 기본 대수선 스케줄
DEFAULT_REPAIR_SCHEDULE = [
    {"name": "전기설비", "cycle_years": 15, "cost_ratio": 0.30},
    {"name": "기계설비", "cycle_years": 20, "cost_ratio": 0.40},
    {"name": "외벽/방수", "cycle_years": 25, "cost_ratio": 0.20},
    {"name": "구조보수", "cycle_years": 30, "cost_ratio": 0.15},
]

# 대안 정의
ALTERNATIVES = {
    "기본안": {
        "energy_saving_rate": 0.0,
        "extra_initial_cost_ratio": 0.0,
        "description": "표준 설계",
    },
    "고단열안": {
        "energy_saving_rate": 0.30,
        "extra_initial_cost_ratio": 0.05,
        "description": "고성능 단열 + 3중 유리",
    },
    "태양광안": {
        "energy_saving_rate": 0.40,
        "extra_initial_cost_ratio": 0.08,
        "description": "태양광 발전 + 고단열",
    },
}


class LCCService:
    """LCC 생애주기비용 산정 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    @staticmethod
    def _calc_real_discount_rate(nominal_rate: float, inflation_rate: float) -> float:
        """실질할인율 계산. Fisher 공식.

        실질할인율 = (1 + 명목할인율) / (1 + 물가상승률) - 1
        """
        return (1 + nominal_rate) / (1 + inflation_rate) - 1

    @staticmethod
    def _calc_repair_costs(
        initial_cost: float,
        repair_schedule: list[dict],
        analysis_years: int,
    ) -> dict[int, float]:
        """각 연도별 대수선 비용을 계산한다.

        대수선 항목별 주기(cycle_years)마다 초기비의 일정 비율(cost_ratio)을
        대수선비로 산정한다.
        """
        repair_costs: dict[int, float] = {}
        for item in repair_schedule:
            cycle = item["cycle_years"]
            cost = initial_cost * item["cost_ratio"]
            year = cycle
            while year <= analysis_years:
                repair_costs[year] = repair_costs.get(year, 0) + cost
                year += cycle
        return repair_costs

    @staticmethod
    def _calc_npv(
        *,
        initial_cost: float,
        annual_maintenance: float,
        annual_energy: float,
        energy_escalation_rate: float,
        repair_costs: dict[int, float],
        real_discount_rate: float,
        analysis_years: int,
    ) -> tuple[float, float, float, float, float, list[dict]]:
        """40년 NPV를 산출한다.

        Returns:
            (npv_total, npv_construction, npv_maintenance, npv_energy,
             npv_repair, yearly_cashflows)
        """
        npv_construction = initial_cost  # 0년차 투입
        npv_maintenance = 0.0
        npv_energy = 0.0
        npv_repair = 0.0
        yearly = []

        for year in range(1, analysis_years + 1):
            discount_factor = 1 / ((1 + real_discount_rate) ** year)

            # 유지보수비 (인플레이션 반영 안함 — 실질 기준)
            maint = annual_maintenance
            npv_maintenance += maint * discount_factor

            # 에너지비 (에너지 가격 상승률 별도 반영)
            energy = annual_energy * ((1 + energy_escalation_rate) ** year)
            npv_energy += energy * discount_factor

            # 대수선비
            repair = repair_costs.get(year, 0)
            npv_repair += repair * discount_factor

            total_year = maint + energy + repair
            yearly.append({
                "year": year,
                "maintenance_krw": round(maint, 2),
                "energy_krw": round(energy, 2),
                "repair_krw": round(repair, 2),
                "total_krw": round(total_year, 2),
                "discount_factor": round(discount_factor, 6),
                "pv_total_krw": round(total_year * discount_factor, 2),
            })

        npv_total = npv_construction + npv_maintenance + npv_energy + npv_repair
        return (
            round(npv_total, 2),
            round(npv_construction, 2),
            round(npv_maintenance, 2),
            round(npv_energy, 2),
            round(npv_repair, 2),
            yearly,
        )

    @staticmethod
    def _compare_alternatives(
        *,
        initial_cost: float,
        annual_maintenance: float,
        annual_energy: float,
        energy_escalation_rate: float,
        repair_costs: dict[int, float],
        real_discount_rate: float,
        analysis_years: int,
    ) -> list[dict]:
        """대안별 LCC 비교 분석.

        기본안, 고단열안, 태양광안의 NPV를 비교한다.
        """
        results = []
        for alt_name, alt_params in ALTERNATIVES.items():
            alt_initial = initial_cost * (1 + alt_params["extra_initial_cost_ratio"])
            alt_energy = annual_energy * (1 - alt_params["energy_saving_rate"])

            npv_total, _, _, _, _, _ = LCCService._calc_npv(
                initial_cost=alt_initial,
                annual_maintenance=annual_maintenance,
                annual_energy=alt_energy,
                energy_escalation_rate=energy_escalation_rate,
                repair_costs=repair_costs,
                real_discount_rate=real_discount_rate,
                analysis_years=analysis_years,
            )
            results.append({
                "alternative": alt_name,
                "description": alt_params["description"],
                "extra_initial_cost_ratio": alt_params["extra_initial_cost_ratio"],
                "energy_saving_rate": alt_params["energy_saving_rate"],
                "npv_total_krw": npv_total,
            })
        return results

    async def calculate(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        initial_construction_cost: float,
        annual_maintenance_cost: float,
        annual_energy_cost: float,
        nominal_rate: float = 0.035,
        inflation_rate: float = 0.013,
        energy_escalation_rate: float = 0.02,
        analysis_period_years: int = 40,
        repair_schedule: list[dict] | None = None,
    ) -> LccCalculation:
        """LCC를 산출하고 DB에 저장한다.

        Args:
            tenant_id: 테넌트 ID
            project_id: 프로젝트 ID
            initial_construction_cost: 초기 건설비 (원)
            annual_maintenance_cost: 연간 유지보수비 (원)
            annual_energy_cost: 연간 에너지비 (원)
            nominal_rate: 명목할인율 (기본 3.5%)
            inflation_rate: 물가상승률 (기본 1.3%)
            energy_escalation_rate: 에너지 가격 상승률 (기본 2.0%)
            analysis_period_years: 분석 기간 (기본 40년)
            repair_schedule: 대수선 스케줄 (미지정 시 기본값 사용)

        Returns:
            저장된 LccCalculation ORM 객체
        """
        logger.info(
            "LCC 산출 시작",
            project_id=str(project_id),
            analysis_years=analysis_period_years,
        )

        schedule = repair_schedule or DEFAULT_REPAIR_SCHEDULE

        # 1) 실질할인율 계산
        real_discount_rate = self._calc_real_discount_rate(nominal_rate, inflation_rate)

        # 2) 대수선 비용 계산
        repair_costs = self._calc_repair_costs(
            initial_construction_cost, schedule, analysis_period_years
        )

        # 3) NPV 산출
        (
            npv_total,
            npv_construction,
            npv_maintenance,
            npv_energy,
            npv_repair,
            yearly_cashflows,
        ) = self._calc_npv(
            initial_cost=initial_construction_cost,
            annual_maintenance=annual_maintenance_cost,
            annual_energy=annual_energy_cost,
            energy_escalation_rate=energy_escalation_rate,
            repair_costs=repair_costs,
            real_discount_rate=real_discount_rate,
            analysis_years=analysis_period_years,
        )

        # 4) 대안 비교
        alternatives = self._compare_alternatives(
            initial_cost=initial_construction_cost,
            annual_maintenance=annual_maintenance_cost,
            annual_energy=annual_energy_cost,
            energy_escalation_rate=energy_escalation_rate,
            repair_costs=repair_costs,
            real_discount_rate=real_discount_rate,
            analysis_years=analysis_period_years,
        )

        # 5) DB 저장
        record = LccCalculation(
            tenant_id=tenant_id,
            project_id=project_id,
            analysis_period_years=analysis_period_years,
            nominal_rate=nominal_rate,
            inflation_rate=inflation_rate,
            real_discount_rate=round(real_discount_rate, 6),
            initial_construction_cost=initial_construction_cost,
            annual_maintenance_cost=annual_maintenance_cost,
            annual_energy_cost=annual_energy_cost,
            energy_escalation_rate=energy_escalation_rate,
            npv_total=npv_total,
            npv_construction=npv_construction,
            npv_maintenance=npv_maintenance,
            npv_energy=npv_energy,
            npv_repair=npv_repair,
            repair_schedule_json=schedule,
            alternatives_json=alternatives,
            yearly_cashflow_json=yearly_cashflows,
        )
        self.db.add(record)
        await self.db.commit()

        logger.info(
            "LCC 산출 완료",
            project_id=str(project_id),
            npv_total=npv_total,
            real_discount_rate=round(real_discount_rate, 6),
        )

        return record
