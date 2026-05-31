"""수지분석/사업모델 추천 AI 해석 서비스.

auto_recommend_top3() 결과를 LLM(Claude)이 해석하여
전문가 수준의 투자 자문을 생성한다.

핵심 원칙:
- LLM 호출 실패 시에도 기존 추천 결과는 정상 반환 (폴백)
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
당신은 한국 부동산 PF(Project Financing) 전문 투자 자문가입니다.

경력:
- 부동산 개발 사업 수지분석 20년 경력
- 수익률, ROI, IRR 분석 전문
- 시행사/시공사/금융기관 관점 균형 분석
- PF 대출 심사 및 구조화 금융 전문
- 한국 부동산 시장 분석 및 투자 자문

전문 분야:
- 분양가 상한제, 청약제도, 전매제한 등 한국 특유의 규제 환경
- PF 대출 구조 (선순위/중순위/후순위, 브릿지론)
- 건설원가 분석 (직접공사비, 간접공사비, 설계비)
- 개발이익 배분 구조 (시행사/시공사/금융기관)
- 인허가 리스크 및 사업일정 관리

역할:
사용자가 제공하는 수지분석 Top3 추천 결과를 전문적이지만 이해하기 쉬운 한국어로 해석합니다.

출력 규칙:
1. 각 항목은 3~5문장으로 작성
2. 숫자를 인용할 때 원본 데이터의 숫자를 정확히 사용
3. "왜 이 모델이 최적인지", "리스크는 무엇인지", "수익 극대화 전략"을 반드시 포함
4. 추측이나 가정은 명확히 표시
5. 금액은 억원 단위로 환산하여 표기 (예: 150억원)
6. 수익률은 소수점 1자리까지 표기
7. 반드시 JSON 형식으로만 응답 (마크다운, 설명문 금지)
"""

# ── 유저 프롬프트 템플릿 ──
USER_PROMPT_TEMPLATE = """\
아래 수지분석 자동 추천 결과를 해석하여 전문 투자 자문을 JSON으로 작성하세요.

## 분석 대상
- 주소: {address}
- 용도지역: {zone_type}
- 대지면적: {land_area_sqm}m² ({land_area_pyeong}평)
- 분석 모델 수: 총 {total_types_analyzed}개 중 Top 3 추천

## Top 3 추천 결과
{recommendations_json}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체를 반환하세요. 각 값은 문자열입니다:

{{
  "overall_recommendation": "종합 추천 의견 — 어떤 모델이 최적이고 왜인지, Top3 간 차이점 요약",
  "top1_analysis": "1위 모델 상세 분석 — 수익구조, 리스크, 경쟁력, 왜 1위인지",
  "top2_analysis": "2위 모델 분석 — 1위 대비 장단점, 대안으로서의 가치",
  "top3_analysis": "3위 모델 분석 — 보수적 대안으로서의 가치, 1·2위 대비 특장점",
  "risk_assessment": "주요 리스크 요인 분석 — 시장 리스크, 인허가 리스크, 자금조달 리스크, 공사 리스크",
  "profit_optimization": "수익 극대화 전략 — 분양가 전략, 세대수 최적화, 원가 절감 방안, 부가수익원",
  "market_timing": "시장 타이밍 및 진입 전략 — 현재 시장 상황 대비 사업 착수 시점, 분양 시기 전략",
  "financing_advice": "자금조달 구조 제안 — PF 구조, 자기자본/타인자본 비율, 브릿지론 활용, 금리 조건"
}}
"""


class FeasibilityInterpreter:
    """수지분석 결과를 AI가 해석하여 전문가 수준의 투자 자문을 생성."""

    def __init__(self, *, timeout_sec: float = 10.0) -> None:
        self._timeout_sec = timeout_sec
        self._llm = None

    def _get_llm(self):
        """ChatAnthropic 인스턴스를 지연 생성."""
        if self._llm is not None:
            return self._llm

        from app.core.config import settings
        from app.services.ai.key_sanitizer import sanitize_api_key

        api_key = sanitize_api_key(
            settings.ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY", ""),
            key_name="ANTHROPIC_API_KEY",
        )
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

        model = settings.ANTHROPIC_MODEL or "claude-sonnet-4-20250514"

        from langchain_anthropic import ChatAnthropic

        self._llm = ChatAnthropic(
            model=model,
            anthropic_api_key=api_key,
            temperature=0.3,
            max_tokens=3000,
            timeout=self._timeout_sec,
        )
        return self._llm

    async def generate_interpretation(self, recommend_data: dict) -> dict[str, str]:
        """auto_recommend_top3 결과를 해석.

        Args:
            recommend_data: auto_recommend_top3()의 반환값

        Returns:
            8개 키를 가진 dict — 각 값은 전문가 해석 문자열.
            {
                "overall_recommendation": "종합 추천 의견",
                "top1_analysis": "1위 모델 상세 분석",
                "top2_analysis": "2위 모델 분석",
                "top3_analysis": "3위 모델 분석",
                "risk_assessment": "주요 리스크 요인 분석",
                "profit_optimization": "수익 극대화 전략 제안",
                "market_timing": "시장 타이밍 및 진입 전략",
                "financing_advice": "자금조달 구조 제안",
            }
        """
        llm = self._get_llm()

        # 토큰 절약: 핵심 데이터만 추출
        compact = self._extract_compact_data(recommend_data)

        address = recommend_data.get("address", "주소 미상")
        zone_type = recommend_data.get("zone_type", "미상")
        land_area_sqm = recommend_data.get("land_area_sqm", 0)
        land_area_pyeong = round(land_area_sqm / 3.305785, 1)
        total_types_analyzed = recommend_data.get("total_types_analyzed", 0)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            address=address,
            zone_type=zone_type,
            land_area_sqm=land_area_sqm,
            land_area_pyeong=land_area_pyeong,
            total_types_analyzed=total_types_analyzed,
            recommendations_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )

        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        logger.info(
            "수지분석 AI 해석 요청",
            address=address[:20],
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
            "수지분석 AI 해석 완료",
            address=address[:20],
            keys=list(result.keys()),
        )
        return result

    def _extract_compact_data(self, data: dict) -> list[dict[str, Any]]:
        """Top3 추천 결과에서 LLM에 필요한 핵심 데이터만 추출.

        토큰 절약을 위해 input_used, all_results 등 불필요한 상세 데이터를 제거.
        """
        recommendations = data.get("recommendations", [])
        compact: list[dict[str, Any]] = []

        for i, rec in enumerate(recommendations[:3]):
            item: dict[str, Any] = {
                "rank": i + 1,
                "development_type": rec.get("development_type"),
                "type_name": rec.get("type_name"),
                "composite_score": rec.get("composite_score"),
            }

            # 수지분석 핵심 KPI
            feas = rec.get("feasibility", {})
            item["feasibility"] = {
                "total_revenue_won": feas.get("total_revenue_won"),
                "total_cost_won": feas.get("total_cost_won"),
                "net_profit_won": feas.get("net_profit_won"),
                "profit_rate_pct": feas.get("profit_rate_pct"),
                "roi_pct": feas.get("roi_pct"),
                "npv_won": feas.get("npv_won"),
                "grade": feas.get("grade"),
            }

            # 인허가 정보
            permit = rec.get("permit", {})
            item["permit"] = {
                "is_permitted": permit.get("is_permitted"),
                "permit_complexity": permit.get("permit_complexity"),
                "reason": permit.get("reason"),
            }

            # 규모 요약
            unit = rec.get("unit_summary", {})
            item["unit_summary"] = {
                "total_gfa_sqm": unit.get("total_gfa_sqm"),
                "total_households": unit.get("total_households"),
                "avg_area_pyeong": unit.get("avg_area_pyeong"),
            }

            compact.append(item)

        return compact

    def _parse_response(self, raw: str) -> dict[str, str]:
        """LLM 응답에서 JSON을 추출하여 파싱.

        응답이 ```json ... ``` 블록으로 감싸져 있을 수 있으므로 처리.
        """
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
            # JSON 파싱 실패 시 중괄호 범위를 찾아 재시도
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start != -1 and brace_end != -1:
                try:
                    parsed = json.loads(text[brace_start : brace_end + 1])
                except json.JSONDecodeError:
                    logger.warning("AI 응답 JSON 파싱 최종 실패", raw_length=len(raw))
                    return {"overall_recommendation": text[:500]}
            else:
                logger.warning("AI 응답에서 JSON을 찾을 수 없음", raw_length=len(raw))
                return {"overall_recommendation": text[:500]}

        # 예상 키 목록
        expected_keys = [
            "overall_recommendation",
            "top1_analysis",
            "top2_analysis",
            "top3_analysis",
            "risk_assessment",
            "profit_optimization",
            "market_timing",
            "financing_advice",
        ]

        result: dict[str, str] = {}
        for key in expected_keys:
            val = parsed.get(key)
            if val is not None:
                result[key] = str(val)

        return result
