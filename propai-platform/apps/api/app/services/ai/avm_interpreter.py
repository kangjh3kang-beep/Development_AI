"""AVM(자동 시세 추정) AI 해석 서비스.

AVM 시세 추정 결과를 LLM(Claude)이 해석하여
가치 평가 내러티브와 투자 관점 분석을 생성한다.

핵심 원칙:
- LLM 호출 실패 시에도 기존 분석 결과는 정상 반환 (폴백)
- 토큰 절약을 위해 핵심 데이터만 추출하여 프롬프트에 포함
- timeout 10초
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.services.ai.base_interpreter import BaseInterpreter

logger = structlog.get_logger()

# ── 시스템 프롬프트 ──
SYSTEM_PROMPT = """\
당신은 한국 부동산 감정평가사이자 가치평가 전문가입니다.

경력:
- 감정평가법인 소속 감정평가사 15년 경력
- IDW(소득접근법), 거래사례비교법, 원가법 기반 평가 전문
- 수익환원법(DCF) 기반 상업용/투자용 부동산 가치 평가
- 법원 감정, 보상평가, 담보평가 경험 다수
- 부동산 시장 분석 및 가격 전망 리포트 발간

역할:
사용자가 제공하는 AVM(자동 시세 추정) 결과를 전문적이지만 이해하기 쉬운 한국어로 해석하고,
시세 추정의 신뢰도, 비교 사례, 시장 포지셔닝, 향후 전망을 분석합니다.

출력 규칙:
1. 각 섹션별 해석은 2~4문장으로 작성
2. 구체적인 수치(평당가, 총액, 변동률 등)를 포함
3. 숫자를 인용할 때 원본 데이터의 숫자를 정확히 사용
4. 추측이나 가정은 명확히 표시
5. 반드시 JSON 형식으로만 응답 (마크다운, 설명문 금지)
6. 감정평가 3방식(비교, 수익, 원가)을 기반으로 분석
"""

# ── 유저 프롬프트 템플릿 ──
USER_PROMPT_TEMPLATE = """\
아래 AVM 시세 추정 결과를 해석하여 가치 평가 내러티브를 JSON으로 작성하세요.

## 분석 데이터
{analysis_json}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체를 반환하세요. 각 값은 문자열입니다:

{{
  "valuation_narrative": "시세 추정 근거 및 신뢰도 분석 (추정 모델, 데이터 품질, 신뢰구간 해석)",
  "comparable_explanation": "비교 사례 분석 (유사 물건 거래 사례, 보정 요인, 비교 타당성 평가)",
  "market_position": "시장 내 포지셔닝 (해당 지역/유형에서의 가격 수준, 상위/중위/하위 몇 % 위치)",
  "appreciation_outlook": "향후 가치 상승/하락 전망 (지역 개발 호재/악재, 시장 사이클, 예상 변동률)",
  "investment_recommendation": "투자 관점 종합 의견 (매수/보유/매도 의견, 적정 매입가, 기대수익률)"
}}
"""


class AvmInterpreter(BaseInterpreter):
    """AVM 시세 추정 결과를 AI가 해석하여 가치 평가 내러티브를 생성."""

    name = "avm"
    expected_keys = [
        "valuation_narrative",
        "comparable_explanation",
        "market_position",
        "appreciation_outlook",
        "investment_recommendation",
    ]
    fallback_key = "valuation_narrative"
    max_tokens = 4096
    system_prompt = SYSTEM_PROMPT

    async def generate_interpretation(self, avm_data: dict) -> dict[str, str]:
        """AVM 시세 추정 결과에 대한 해석 텍스트를 생성.

        Args:
            avm_data: AVM 시세 추정 결과 dict

        Returns:
            5개 키를 가진 dict - 각 값은 전문가 해석 문자열.
            LLM 호출 실패 시 빈 dict 반환(호출자 폴백).
        """
        compact = self._extract_compact_data(avm_data)
        user_prompt = USER_PROMPT_TEMPLATE.format(
            analysis_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )
        return await self._invoke(
            user_prompt, cache_data=compact, evidence_data=avm_data
        )

    def _evidence(self, data: dict) -> str | None:
        """P3: 대상지 주소 기반 지역 시세 벤치마크 주입."""
        return self._regional_benchmark(address=str(data.get("address", "")))

    def _extract_compact_data(self, data: dict) -> dict[str, Any]:
        """전체 AVM 결과에서 LLM에 필요한 핵심 데이터만 추출."""
        compact: dict[str, Any] = {}

        # 추정 시세
        estimate = data.get("estimated_value", {})
        if estimate:
            compact["estimated_value"] = {
                "value_won": estimate.get("value_won"),
                "value_per_sqm_won": estimate.get("value_per_sqm_won"),
                "value_per_pyeong_won": estimate.get("value_per_pyeong_won"),
                "confidence_score": estimate.get("confidence_score"),
                "confidence_interval_low": estimate.get("confidence_interval_low"),
                "confidence_interval_high": estimate.get("confidence_interval_high"),
                "valuation_date": estimate.get("valuation_date"),
            }

        # 비교 사례 (상위 5개만)
        comparables = data.get("comparables", [])
        if comparables:
            compact["comparables_top5"] = [
                {
                    "address": c.get("address"),
                    "transaction_price_won": c.get("transaction_price_won"),
                    "price_per_sqm_won": c.get("price_per_sqm_won"),
                    "transaction_date": c.get("transaction_date"),
                    "area_sqm": c.get("area_sqm"),
                    "similarity_score": c.get("similarity_score"),
                    "distance_m": c.get("distance_m"),
                }
                for c in comparables[:5]
            ]
            compact["comparables_total_count"] = len(comparables)

        # 시장 통계
        market = data.get("market_statistics", {})
        if market:
            compact["market_statistics"] = {
                "avg_price_per_sqm": market.get("avg_price_per_sqm"),
                "median_price_per_sqm": market.get("median_price_per_sqm"),
                "percentile_rank": market.get("percentile_rank"),
                "price_trend_pct": market.get("price_trend_pct"),
                "transaction_volume": market.get("transaction_volume"),
                "supply_demand_ratio": market.get("supply_demand_ratio"),
            }

        # 가격 이력
        history = data.get("price_history", [])
        if history:
            # 최근 5건만
            compact["price_history_recent"] = [
                {
                    "date": h.get("date"),
                    "price_won": h.get("price_won"),
                    "price_per_sqm_won": h.get("price_per_sqm_won"),
                    "change_pct": h.get("change_pct"),
                }
                for h in history[-5:]
            ]

        # 개발 호재/악재
        factors = data.get("value_factors", {})
        if factors:
            compact["value_factors"] = {
                "positive_factors": factors.get("positive_factors", []),
                "negative_factors": factors.get("negative_factors", []),
            }

        # 물건 기본 정보
        for key in [
            "address",
            "property_type",
            "area_sqm",
            "floor",
            "building_age_years",
            "land_area_sqm",
        ]:
            if key in data:
                compact[key] = data[key]

        return compact
