"""RE100 이행률 추적 + K-ETS 배출권 비용 산출 서비스.

RE100 이행 경로:
- 2030: 60% 재생에너지
- 2040: 90% 재생에너지
- 2050: 100% 재생에너지

K-ETS (한국 배출권거래제):
- 기본 배출권 단가: 18,000원/tCO2eq
- 전력 배출계수(KR_GRID_EF): 0.4629 tCO2eq/MWh

RE100 조달 수단 5가지:
1. 자가발전 (태양광/풍력) -- 120,000원/MWh
2. PPA (전력구매계약) -- 100,000원/MWh
3. 녹색프리미엄 -- 50,000원/MWh
4. REC 구매 (신재생에너지 인증서) -- 80,000원/MWh
5. 지분투자 -- 150,000원/MWh
"""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database.models.re100_tracking import Re100Tracking

logger = structlog.get_logger(__name__)

# 상수
KR_GRID_EF = 0.4629  # tCO2eq/MWh (한국전력 2025)
DEFAULT_KTS_PRICE = 18_000  # 원/tCO2eq

# RE100 이행 목표
RE100_TARGETS: dict[int, float] = {
    2030: 0.60,
    2040: 0.90,
    2050: 1.00,
}

# 조달 수단별 단가 (원/MWh)
PROCUREMENT_COSTS: dict[str, dict] = {
    "자가발전": {"unit_cost_krw_mwh": 120_000, "description": "태양광/풍력 자가발전"},
    "PPA": {"unit_cost_krw_mwh": 100_000, "description": "전력구매계약 (Power Purchase Agreement)"},
    "녹색프리미엄": {"unit_cost_krw_mwh": 50_000, "description": "한전 녹색프리미엄 요금제"},
    "REC구매": {"unit_cost_krw_mwh": 80_000, "description": "신재생에너지 공급인증서 구매"},
    "지분투자": {"unit_cost_krw_mwh": 150_000, "description": "재생에너지 발전 지분투자"},
}


class Re100TrackerService:
    """RE100 이행률 추적 및 K-ETS 비용 산출 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    @staticmethod
    def _calc_re100_rate(renewable_mwh: float, total_mwh: float) -> float:
        """RE100 이행률을 계산한다.

        Args:
            renewable_mwh: 재생에너지 전력량 (MWh)
            total_mwh: 총 전력 사용량 (MWh)

        Returns:
            RE100 이행률 (0.0 ~ 1.0). 소수점 4자리 반올림.
        """
        if total_mwh <= 0:
            return 0.0
        return round(min(1.0, renewable_mwh / total_mwh), 4)

    @staticmethod
    def _calc_emissions(
        total_mwh: float, renewable_mwh: float, grid_ef: float = KR_GRID_EF
    ) -> tuple[float, float, float]:
        """배출량을 계산한다.

        Args:
            total_mwh: 총 전력 사용량 (MWh)
            renewable_mwh: 재생에너지 전력량 (MWh)
            grid_ef: 전력 배출계수 (tCO2eq/MWh)

        Returns:
            (total_emissions, baseline_emissions, excess_emissions)
            - total_emissions: 실제 배출량 (비재생 전력만)
            - baseline_emissions: RE100 100% 달성 시 배출량 (0)
            - excess_emissions: 초과 배출량 = total - baseline
        """
        non_renewable_mwh = max(0, total_mwh - renewable_mwh)
        total_emissions = round(non_renewable_mwh * grid_ef, 4)
        baseline_emissions = 0.0  # RE100 100% = 0 배출
        excess_emissions = total_emissions  # 전량 초과
        return total_emissions, baseline_emissions, excess_emissions

    @staticmethod
    def _calc_kts_cost(excess_tco2eq: float, unit_price: int = DEFAULT_KTS_PRICE) -> float:
        """K-ETS 배출권 비용을 산출한다.

        Args:
            excess_tco2eq: 초과 배출량 (tCO2eq)
            unit_price: 배출권 단가 (원/tCO2eq)

        Returns:
            K-ETS 총 비용 (원). 소수점 0자리 반올림.
        """
        if excess_tco2eq <= 0:
            return 0.0
        return round(excess_tco2eq * unit_price, 0)

    @staticmethod
    def _compare_procurement(
        additional_renewable_mwh: float,
    ) -> list[dict]:
        """RE100 조달 수단별 비용 비교.

        Args:
            additional_renewable_mwh: 추가 필요 재생에너지량 (MWh)

        Returns:
            조달 수단별 비용 비교 리스트. 비용 오름차순 정렬.
        """
        results = []
        for name, info in PROCUREMENT_COSTS.items():
            cost = additional_renewable_mwh * info["unit_cost_krw_mwh"]
            results.append({
                "method": name,
                "description": info["description"],
                "unit_cost_krw_mwh": info["unit_cost_krw_mwh"],
                "total_cost_krw": round(cost, 0),
            })
        # 비용 오름차순 정렬
        return sorted(results, key=lambda x: x["total_cost_krw"])

    @staticmethod
    def _generate_roadmap(
        current_re100_rate: float,
        total_mwh: float,
        tracking_year: int,
    ) -> list[dict]:
        """RE100 이행 로드맵을 생성한다.

        Args:
            current_re100_rate: 현재 RE100 이행률 (0.0 ~ 1.0)
            total_mwh: 총 전력 사용량 (MWh)
            tracking_year: 추적 연도

        Returns:
            연도별 목표, 갭, 추가 필요량, 연간 증가 필요량 리스트.
        """
        roadmap = []
        for target_year, target_rate in sorted(RE100_TARGETS.items()):
            if target_year <= tracking_year:
                continue
            gap = max(0, target_rate - current_re100_rate)
            additional_mwh = gap * total_mwh
            years_left = target_year - tracking_year
            annual_increase_mwh = additional_mwh / years_left if years_left > 0 else 0

            roadmap.append({
                "target_year": target_year,
                "target_rate": target_rate,
                "current_gap": round(gap, 4),
                "additional_renewable_mwh": round(additional_mwh, 2),
                "annual_increase_mwh": round(annual_increase_mwh, 2),
            })
        return roadmap

    async def track(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        tracking_year: int,
        total_electricity_mwh: float,
        renewable_electricity_mwh: float,
        kts_unit_price_krw: int = DEFAULT_KTS_PRICE,
    ) -> Re100Tracking:
        """RE100 이행률을 추적하고 K-ETS 비용을 산출한다.

        Args:
            tenant_id: 테넌트 ID
            project_id: 프로젝트 ID
            tracking_year: 추적 연도
            total_electricity_mwh: 총 전력 사용량 (MWh)
            renewable_electricity_mwh: 재생에너지 전력량 (MWh)
            kts_unit_price_krw: K-ETS 배출권 단가 (원/tCO2eq)

        Returns:
            저장된 Re100Tracking 레코드
        """
        logger.info(
            "RE100 이행률 추적 시작",
            project_id=str(project_id),
            tracking_year=tracking_year,
            total_mwh=total_electricity_mwh,
            renewable_mwh=renewable_electricity_mwh,
        )

        # 1. RE100 이행률 계산
        re100_rate = self._calc_re100_rate(
            renewable_electricity_mwh, total_electricity_mwh
        )

        # 2. 배출량 계산
        total_emissions, baseline_emissions, excess_emissions = self._calc_emissions(
            total_electricity_mwh, renewable_electricity_mwh
        )

        # 3. K-ETS 비용 산출
        kts_total_cost = self._calc_kts_cost(excess_emissions, kts_unit_price_krw)

        # 4. 조달 수단별 비용 비교 (비재생 전력량 = 추가 필요 재생에너지량)
        non_renewable_mwh = max(0, total_electricity_mwh - renewable_electricity_mwh)
        procurement_breakdown = self._compare_procurement(non_renewable_mwh)

        # 5. 이행 로드맵 생성
        roadmap = self._generate_roadmap(re100_rate, total_electricity_mwh, tracking_year)

        # 6. 요약 텍스트 생성
        summary = (
            f"{tracking_year}년 RE100 이행률: {re100_rate * 100:.1f}% "
            f"(재생 {renewable_electricity_mwh:.1f} / 전체 {total_electricity_mwh:.1f} MWh). "
            f"초과 배출량: {excess_emissions:.2f} tCO2eq, "
            f"K-ETS 비용: {kts_total_cost:,.0f}원."
        )

        # 7. DB 저장
        record = Re100Tracking(
            tenant_id=tenant_id,
            project_id=project_id,
            tracking_year=tracking_year,
            total_electricity_mwh=total_electricity_mwh,
            renewable_electricity_mwh=renewable_electricity_mwh,
            re100_rate=re100_rate,
            grid_emission_factor=KR_GRID_EF,
            total_emissions_tco2eq=total_emissions,
            baseline_emissions_tco2eq=baseline_emissions,
            excess_emissions_tco2eq=excess_emissions,
            kts_unit_price_krw=kts_unit_price_krw,
            kts_total_cost_krw=kts_total_cost,
            procurement_breakdown_json=procurement_breakdown,
            roadmap_json=roadmap,
            summary=summary,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)

        logger.info(
            "RE100 이행률 추적 완료",
            project_id=str(project_id),
            re100_rate=re100_rate,
            kts_cost=kts_total_cost,
        )

        return record
