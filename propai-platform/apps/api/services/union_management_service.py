"""재건축 조합원 분담금 산정 서비스.

비례율법 기반 분담금 계산.
LLM으로 비용 시나리오 분석 및 조합원 설명 자료 생성.

흐름:
1. 기존 자산 평가 (감정가)
2. 비례율 계산: 비례율 = 총사업비 / 총감정가
3. 개인 분담금 = 입주 희망 면적 평균분양가 - 개인 감정가 × 비례율
"""

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings

logger = structlog.get_logger(__name__)


class UnionContributionResult:
    """조합원 분담금 산정 결과."""
    def __init__(
        self,
        proportional_rate: float,
        individual_contribution: float,
        total_project_cost: float,
        breakdown: dict,
        scenarios: list[dict],
    ):
        self.proportional_rate = proportional_rate
        self.individual_contribution = individual_contribution
        self.total_project_cost = total_project_cost
        self.breakdown = breakdown
        self.scenarios = scenarios


class UnionManagementService:
    """재건축 조합원 분담금 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    def _calculate_proportional_rate(
        self,
        total_project_cost: float,
        total_appraised_value: float,
    ) -> float:
        """비례율을 계산한다. 비례율 = (총 사업비 + 총 분양수입) / 총 감정가."""
        if total_appraised_value == 0:
            return 1.0
        return total_project_cost / total_appraised_value

    def _calculate_contribution(
        self,
        target_area_sqm: float,
        avg_sale_price_per_sqm: float,
        individual_appraised_value: float,
        proportional_rate: float,
    ) -> float:
        """개인 분담금을 계산한다."""
        target_value = target_area_sqm * avg_sale_price_per_sqm
        credit = individual_appraised_value * proportional_rate
        return max(0, target_value - credit)

    async def _generate_scenarios(
        self,
        base_contribution: float,
        proportional_rate: float,
        target_area_sqm: float,
    ) -> list[dict]:
        """LLM으로 분담금 시나리오를 생성한다."""
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            model="claude-sonnet-4-5-20250929",
            api_key=self.settings.anthropic_api_key,
            temperature=0.3,
        )

        prompt = f"""재건축 조합 전문가로서, 다음 조건에 대해 3가지 시나리오를 분석하세요.

## 기본 조건
- 기본 분담금: {base_contribution:,.0f}원
- 비례율: {proportional_rate:.2%}
- 목표 면적: {target_area_sqm}㎡

## 시나리오 유형
1. 낙관적 (분양가 상승, 사업비 절감)
2. 기본 (현재 조건 유지)
3. 비관적 (분양가 하락, 사업비 증가)

각 시나리오에 대해 예상 분담금과 주요 변동 요인을 JSON 배열로 반환:
[{{"scenario": "...", "contribution": 숫자, "factors": ["..."]}}]"""

        try:
            response = await llm.ainvoke(prompt)
            import json
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            scenarios: list[dict[str, Any]] = json.loads(content.strip())
            return scenarios
        except Exception:
            return [
                {"scenario": "기본", "contribution": base_contribution, "factors": ["현재 조건 유지"]},
            ]

    async def calculate_contribution(
        self,
        project_id: UUID,
        tenant_id: UUID,
        total_project_cost: float,
        total_appraised_value: float,
        individual_appraised_value: float,
        target_area_sqm: float,
        avg_sale_price_per_sqm: float,
    ) -> UnionContributionResult:
        """조합원 분담금을 산정한다."""
        logger.info("조합원 분담금 산정 시작", project_id=str(project_id))

        # 비례율 계산
        proportional_rate = self._calculate_proportional_rate(
            total_project_cost, total_appraised_value,
        )

        # 개인 분담금 계산
        contribution = self._calculate_contribution(
            target_area_sqm, avg_sale_price_per_sqm,
            individual_appraised_value, proportional_rate,
        )

        breakdown = {
            "target_value": target_area_sqm * avg_sale_price_per_sqm,
            "credit": individual_appraised_value * proportional_rate,
            "contribution": contribution,
        }

        # 시나리오 생성
        scenarios = await self._generate_scenarios(
            contribution, proportional_rate, target_area_sqm,
        )

        logger.info("조합원 분담금 산정 완료", contribution=contribution)

        return UnionContributionResult(
            proportional_rate=proportional_rate,
            individual_contribution=contribution,
            total_project_cost=total_project_cost,
            breakdown=breakdown,
            scenarios=scenarios,
        )
