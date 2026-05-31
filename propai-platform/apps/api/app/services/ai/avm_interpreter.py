"""AVM(자동 시세 추정) AI 해석 서비스.

AVM 시세 추정 결과를 LLM(Claude)이 해석하여
가치 평가 내러티브와 투자 관점 분석을 생성한다.

핵심 원칙:
- LLM 호출 실패 시에도 기존 분석 결과는 정상 반환 (폴백)
- 토큰 절약을 위해 핵심 데이터만 추출하여 프롬프트에 포함
- timeout 10초
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import structlog

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


class AvmInterpreter:
    """AVM 시세 추정 결과를 AI가 해석하여 가치 평가 내러티브를 생성."""

    def __init__(self, *, timeout_sec: float = 90.0) -> None:
        self._timeout_sec = timeout_sec
        self._llm = None

    def _get_llm(self):
        """LLM 인스턴스를 지연 생성. llm_provider 우선, 없으면 직접 생성."""
        if self._llm is not None:
            return self._llm

        try:
            from app.services.ai.llm_provider import get_llm

            self._llm = get_llm(timeout=self._timeout_sec)
        except ImportError:
            from langchain_anthropic import ChatAnthropic

            from app.services.ai.key_sanitizer import get_clean_env_key

            self._llm = ChatAnthropic(
                model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
                anthropic_api_key=get_clean_env_key("ANTHROPIC_API_KEY"),
                temperature=0.3,
                max_tokens=4096,
                timeout=self._timeout_sec,
            )
        return self._llm

    async def generate_interpretation(self, avm_data: dict) -> dict[str, str]:
        """AVM 시세 추정 결과에 대한 해석 텍스트를 생성.

        Args:
            avm_data: AVM 시세 추정 결과 dict

        Returns:
            5개 키를 가진 dict - 각 값은 전문가 해석 문자열.
            LLM 호출 실패 시 빈 dict가 아니라 None을 반환하여
            호출자가 폴백 처리할 수 있게 한다.
        """
        llm = self._get_llm()

        # 토큰 절약: 핵심 데이터만 추출
        compact = self._extract_compact_data(avm_data)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            analysis_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )

        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        logger.info(
            "AVM AI 해석 요청",
            prompt_chars=len(user_prompt),
        )

        # timeout 적용하여 LLM 호출
        response = await asyncio.wait_for(
            llm.ainvoke(messages),
            timeout=self._timeout_sec,
        )

        raw_text = response.content if hasattr(response, "content") else str(response)
        result = self._parse_response(raw_text)

        logger.info(
            "AVM AI 해석 완료",
            keys=list(result.keys()),
        )
        return result

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

    def _parse_response(self, raw: str) -> dict[str, str]:
        """LLM 응답에서 JSON을 추출하여 파싱."""
        text = raw.strip()

        # ```json ... ``` 블록 제거
        if text.startswith("```"):
            lines = text.split("\n")
            start = 1
            end = len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end = i
                    break
            text = "\n".join(lines[start:end])

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start != -1 and brace_end != -1:
                try:
                    parsed = json.loads(text[brace_start : brace_end + 1])
                except json.JSONDecodeError:
                    logger.warning("AVM AI 응답 JSON 파싱 최종 실패", raw_length=len(raw))
                    return {"valuation_narrative": text[:500]}
            else:
                logger.warning("AVM AI 응답에서 JSON을 찾을 수 없음", raw_length=len(raw))
                return {"valuation_narrative": text[:500]}

        expected_keys = [
            "valuation_narrative",
            "comparable_explanation",
            "market_position",
            "appreciation_outlook",
            "investment_recommendation",
        ]

        result: dict[str, str] = {}
        for key in expected_keys:
            val = parsed.get(key)
            if val is not None:
                result[key] = str(val)

        return result
