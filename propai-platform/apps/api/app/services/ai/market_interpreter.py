"""시장분석 AI 해석 서비스.

수집된 시장 데이터(실거래가, 공시지가, 분양가)를 LLM(Claude)이 해석하여
전문가 수준의 시장 분석 내러티브를 생성한다.

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
당신은 한국 부동산 시장 분석 전문 컨설턴트입니다.

경력:
- 한국 부동산 시장 10년 이력 분석 전문가
- 실거래가, 공시지가, 분양가 상관관계 분석
- 금리, 대출규제, 세제 등 정책 변화의 시장 영향 분석
- 수도권 및 지방 광역시 권역별 시장 동향 전문
- 부동산 개발사업 시장성 검토 자문 다수

역할:
사용자가 제공하는 시장 데이터(실거래가 통계, 공시지가, 개발방식별 분양가)를
전문적이지만 이해하기 쉬운 한국어로 해석합니다.
단순 데이터 나열이 아닌, 데이터가 의미하는 시장 상황과 투자 시사점을 도출합니다.

출력 규칙:
1. 각 섹션별 해석은 3~5문장으로 작성
2. 숫자를 인용할 때 원본 데이터의 숫자를 정확히 사용
3. "왜 이런 시세인지", "향후 전망", "개발사업자에게 주는 시사점"을 반드시 포함
4. 추측이나 가정은 명확히 "~로 추정됩니다", "~가능성이 있습니다"로 표시
5. 반드시 JSON 형식으로만 응답 (마크다운, 설명문 금지)
"""

# ── 유저 프롬프트 템플릿 ──
USER_PROMPT_TEMPLATE = """\
아래 부동산 시장 데이터를 해석하여 전문가 수준의 시장 분석 내러티브를 JSON으로 작성하세요.

## 분석 대상
- 주소: {address}
- 용도지역: {zone_type}
- 대지면적: {land_area_sqm}m2 ({land_area_pyeong}평)

## 시장 데이터
{market_json}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체를 반환하세요. 각 값은 문자열입니다:

{{
  "market_overview": "해당 지역 부동산 시장 종합 현황 (지역 특성, 시세 수준, 시장 활성도를 3~5문장으로 서술)",
  "price_trend_analysis": "가격 추이 분석 및 전망 (실거래가-공시지가-분양가 상관관계, 가격 방향성, 근거를 3~5문장으로 서술)",
  "comparable_analysis": "주변 유사 물건 비교 분석 (물건유형별 시세 차이, 개발방식별 분양가 격차, 최적 개발유형 시사점을 3~5문장으로 서술)",
  "investment_insight": "투자 관점에서의 시사점 (토지 매입 적정가, 사업 수익성, 자금 조달 고려사항을 3~5문장으로 서술)",
  "risk_factors": "시장 리스크 요인 (금리, 규제, 공급과잉, 수요 변화 등 2~3개 핵심 리스크와 헤징 방안)",
  "timing_recommendation": "매수/개발 적기 판단 (현재 시점의 매수 적정성, 개발 착수 시기, 시장 사이클상 위치를 3~5문장으로 서술)"
}}
"""


class MarketInterpreter(BaseInterpreter):
    """시장 데이터를 AI가 해석하여 전문가 수준의 시장 분석 내러티브를 생성."""

    name = "market"
    expected_keys = [
        "market_overview",
        "price_trend_analysis",
        "comparable_analysis",
        "investment_insight",
        "risk_factors",
        "timing_recommendation",
    ]
    fallback_key = "market_overview"
    max_tokens = 4096
    system_prompt = SYSTEM_PROMPT

    # 폴백 시 반환할 기본 키 목록
    EXPECTED_KEYS = [
        "market_overview",
        "price_trend_analysis",
        "comparable_analysis",
        "investment_insight",
        "risk_factors",
        "timing_recommendation",
    ]


    async def generate_interpretation(self, market_data: dict) -> dict[str, str]:
        """실거래가/시세 데이터를 해석하여 시장 분석 내러티브를 생성.

        Args:
            market_data: 시장 관련 데이터를 포함하는 dict.
                필수/선택 키:
                - address (str): 분석 대상 주소
                - zone_type (str): 용도지역
                - land_area_sqm (float): 대지면적(m2)
                - transaction_prices (dict): 물건유형별 실거래가 통계
                - land_prices (dict): 공시지가 및 추정 시세
                - sale_prices (list[dict]): 개발방식별 분양가

        Returns:
            6개 키를 가진 dict -- 각 값은 전문가 해석 문자열.
            LLM 호출 실패 시 None을 반환하여 호출자가 폴백 처리할 수 있게 한다.
        """
        # 토큰 절약: 핵심 데이터만 추출
        compact = self._extract_compact_data(market_data)

        address = market_data.get("address", "주소 미상")
        zone_type = market_data.get("zone_type", "미상")
        land_area_sqm = market_data.get("land_area_sqm", 0)
        land_area_pyeong = round(land_area_sqm / 3.305785, 1)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            address=address,
            zone_type=zone_type,
            land_area_sqm=land_area_sqm,
            land_area_pyeong=land_area_pyeong,
            market_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )

        return await self._invoke(
            user_prompt, cache_data=compact, evidence_data=market_data
        )

    def _evidence(self, data: dict) -> str | None:
        """P3: 대상지 주소 기반 지역 시세 벤치마크 주입."""
        return self._regional_benchmark(address=str(data.get("address", "")))

    def _extract_compact_data(self, data: dict) -> dict[str, Any]:
        """시장 데이터에서 LLM에 필요한 핵심 데이터만 추출.

        토큰 절약을 위해 불필요한 상세 데이터(items 배열 등)를 제거.
        """
        compact: dict[str, Any] = {}

        # 실거래가 통계 (items 배열 제외, 통계값만)
        txn = data.get("transaction_prices", {})
        if txn and not txn.get("error"):
            compact_txn: dict[str, Any] = {}
            for prop_type, detail in txn.items():
                if isinstance(detail, dict) and "count" in detail:
                    compact_txn[prop_type] = {
                        "count": detail.get("count"),
                        "avg_price_10k": detail.get("avg_price_10k"),
                        "max_price_10k": detail.get("max_price_10k"),
                        "min_price_10k": detail.get("min_price_10k"),
                    }
            if compact_txn:
                compact["transaction_prices"] = compact_txn

        # 공시지가 및 추정 시세
        lp = data.get("land_prices", {})
        if lp:
            compact["land_prices"] = {
                "official_price_per_sqm": lp.get("official_price_per_sqm"),
                "official_price_per_pyeong": lp.get("official_price_per_pyeong"),
                "total_official_value_won": lp.get("total_official_value_won"),
                "estimated_market_per_sqm": lp.get("estimated_market_per_sqm"),
                "estimated_market_per_pyeong": lp.get("estimated_market_per_pyeong"),
                "total_estimated_value_won": lp.get("total_estimated_value_won"),
                "market_multiplier": lp.get("market_multiplier"),
            }

        # 분양가 -- 상위 5개 (다양한 개발방식 비교를 위해)
        sale = data.get("sale_prices", [])
        if sale:
            compact["sale_prices"] = [
                {
                    "type_name": s.get("type_name"),
                    "sale_price_per_pyeong_man": s.get("sale_price_per_pyeong_man"),
                    "sale_price_per_sqm_man": s.get("sale_price_per_sqm_man"),
                }
                for s in sale[:5]
            ]
            compact["sale_prices_total_count"] = len(sale)

        # 용적률/건폐율 (수익성 판단에 필요)
        far = data.get("effective_far", {})
        if far:
            compact["effective_far_pct"] = far.get("effective_far_pct")
            compact["effective_bcr_pct"] = far.get("effective_bcr_pct")

        return compact

