"""세금 분석 AI 해석 서비스.

세금 계산 결과를 LLM(Claude)이 해석하여
절세 전략 및 사업구조별 세금 비교를 제안한다.

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
당신은 한국 부동산 세무 전문 세무사이자 공인회계사입니다.

경력:
- 부동산 개발/투자 세무 자문 20년
- 취득세, 양도소득세, 종합부동산세, 법인세 전문
- 부동산 PF, 리츠(REITs), 부동산펀드 세무구조 설계
- 국세청 세무조사 대응 및 조세불복 경험 다수
- 부동산 관련 조세특례제한법, 지방세법 전문

역할:
사용자가 제공하는 세금 계산 결과를 전문적이지만 이해하기 쉬운 한국어로 해석하고,
합법적인 절세 전략과 사업구조 최적화 방안을 제시합니다.

출력 규칙:
1. 각 섹션별 해석은 2~4문장으로 작성
2. 구체적인 수치(세액, 세율, 절감액 등)를 포함
3. 숫자를 인용할 때 원본 데이터의 숫자를 정확히 사용
4. 추측이나 가정은 명확히 표시
5. 반드시 JSON 형식으로만 응답 (마크다운, 설명문 금지)
6. 절세 전략은 반드시 적법한 범위 내에서 제시
"""

# ── 유저 프롬프트 템플릿 ──
USER_PROMPT_TEMPLATE = """\
아래 세금 계산 결과를 해석하여 절세 전략을 JSON으로 작성하세요.

## 분석 데이터
{analysis_json}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체를 반환하세요. 각 값은 문자열입니다:

{{
  "tax_summary": "세금 부담 종합 분석 (총 세부담액, 실효세율, 주요 세목별 비중)",
  "optimization_strategy": "절세 전략 (법인/개인 선택, 사업구조 개편, 세액공제/감면 활용 등 3~5개)",
  "entity_comparison": "사업주체별(개인/법인/조합/리츠) 세금 비교 (각 구조의 장단점, 최적 구조 추천)",
  "timing_strategy": "양도/취득 시점에 따른 세금 영향 (보유기간, 중과세 여부, 최적 매각 시점)",
  "deduction_opportunities": "공제/감면 적용 가능 항목 (조세특례제한법, 지방세특례제한법 근거 포함)",
  "risk_factors": "세무 리스크 요인 (세무조사 가능성, 추징 리스크, 비적격 합병/분할 리스크 등)"
}}
"""


class TaxInterpreter:
    """세금 계산 결과를 AI가 해석하여 절세 전략을 제안."""

    def __init__(self, *, timeout_sec: float = 45.0) -> None:
        self._timeout_sec = timeout_sec
        self._llm = None

    def _get_llm(self):
        """LLM 인스턴스를 지연 생성. llm_provider 우선, 없으면 직접 생성."""
        if self._llm is not None:
            return self._llm

        try:
            from app.services.ai.llm_provider import get_llm

            # timeout을 명시 전달 — 미전달 시 get_llm 기본값 10s라 세무 6섹션 생성이
            # APITimeoutError로 끊긴다(세무 프롬프트가 길어 ~30s+ 소요).
            self._llm = get_llm(timeout=self._timeout_sec)
        except ImportError:
            from langchain_anthropic import ChatAnthropic

            from app.services.ai.key_sanitizer import get_clean_env_key

            self._llm = ChatAnthropic(
                model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
                anthropic_api_key=get_clean_env_key("ANTHROPIC_API_KEY"),
                temperature=0.3,
                max_tokens=2048,
                timeout=self._timeout_sec,
            )
        return self._llm

    async def generate_interpretation(self, tax_data: dict) -> dict[str, str]:
        """세금 계산 결과에 대한 해석 텍스트를 생성.

        Args:
            tax_data: 세금 계산 결과 dict

        Returns:
            6개 키를 가진 dict - 각 값은 전문가 해석 문자열.
            LLM 호출 실패 시 빈 dict가 아니라 None을 반환하여
            호출자가 폴백 처리할 수 있게 한다.
        """
        llm = self._get_llm()

        # 토큰 절약: 핵심 데이터만 추출
        compact = self._extract_compact_data(tax_data)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            analysis_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )

        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        logger.info(
            "세금 AI 해석 요청",
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
            "세금 AI 해석 완료",
            keys=list(result.keys()),
        )
        return result

    def _extract_compact_data(self, data: dict) -> dict[str, Any]:
        """전체 세금 계산 결과에서 LLM에 필요한 핵심 데이터만 추출."""
        compact: dict[str, Any] = {}

        # 취득세
        acq = data.get("acquisition_tax", {})
        if acq:
            compact["acquisition_tax"] = {
                "tax_amount_won": acq.get("tax_amount_won"),
                "tax_rate_pct": acq.get("tax_rate_pct"),
                "taxable_value_won": acq.get("taxable_value_won"),
                "surtax_included": acq.get("surtax_included"),
                "heavy_tax_applied": acq.get("heavy_tax_applied"),
            }

        # 양도소득세
        transfer = data.get("transfer_tax", {})
        if transfer:
            compact["transfer_tax"] = {
                "tax_amount_won": transfer.get("tax_amount_won"),
                "tax_rate_pct": transfer.get("tax_rate_pct"),
                "taxable_gain_won": transfer.get("taxable_gain_won"),
                "holding_period_years": transfer.get("holding_period_years"),
                "long_term_deduction_pct": transfer.get("long_term_deduction_pct"),
                "heavy_tax_applied": transfer.get("heavy_tax_applied"),
            }

        # 종합부동산세
        comp_tax = data.get("comprehensive_property_tax", {})
        if comp_tax:
            compact["comprehensive_property_tax"] = {
                "tax_amount_won": comp_tax.get("tax_amount_won"),
                "tax_rate_pct": comp_tax.get("tax_rate_pct"),
                "assessed_value_won": comp_tax.get("assessed_value_won"),
                "deduction_won": comp_tax.get("deduction_won"),
            }

        # 법인세
        corp = data.get("corporate_tax", {})
        if corp:
            compact["corporate_tax"] = {
                "tax_amount_won": corp.get("tax_amount_won"),
                "effective_rate_pct": corp.get("effective_rate_pct"),
                "taxable_income_won": corp.get("taxable_income_won"),
            }

        # 재산세
        prop = data.get("property_tax", {})
        if prop:
            compact["property_tax"] = {
                "tax_amount_won": prop.get("tax_amount_won"),
                "tax_rate_pct": prop.get("tax_rate_pct"),
            }

        # 부가가치세
        vat = data.get("vat", {})
        if vat:
            compact["vat"] = {
                "tax_amount_won": vat.get("tax_amount_won"),
                "input_vat_won": vat.get("input_vat_won"),
                "output_vat_won": vat.get("output_vat_won"),
            }

        # 세금 합계
        total = data.get("total_tax", {})
        if total:
            compact["total_tax"] = {
                "total_amount_won": total.get("total_amount_won"),
                "effective_rate_pct": total.get("effective_rate_pct"),
            }

        # 거래 기본 정보
        for key in [
            "property_value_won",
            "property_type",
            "entity_type",
            "holding_period_years",
            "acquisition_date",
            "transfer_date",
            "address",
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
                    logger.warning("세금 AI 응답 JSON 파싱 최종 실패", raw_length=len(raw))
                    return {"tax_summary": text[:500]}
            else:
                logger.warning("세금 AI 응답에서 JSON을 찾을 수 없음", raw_length=len(raw))
                return {"tax_summary": text[:500]}

        expected_keys = [
            "tax_summary",
            "optimization_strategy",
            "entity_comparison",
            "timing_strategy",
            "deduction_opportunities",
            "risk_factors",
        ]

        result: dict[str, str] = {}
        for key in expected_keys:
            val = parsed.get(key)
            if val is not None:
                result[key] = str(val)

        return result
