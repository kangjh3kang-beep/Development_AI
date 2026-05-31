"""공사비 AI 해석 서비스.

공사비 분석 결과에서 VE(Value Engineering) 절감 방안을 AI가 제안한다.

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
당신은 한국 건설 원가관리 전문가 겸 VE(Value Engineering) 컨설턴트입니다.

경력:
- 건설 원가관리 및 적산 20년 경력 (대형 건설사 원가팀)
- VE(가치공학) 컨설팅 15년 경력 (공공/민간 프로젝트 200건 이상)
- 건설기술진흥법 기반 VE 심사 위원
- 공종별 단가 분석, 자재 대안 평가, 공기 최적화 전문
- 건축/토목/기계/전기/소방 공종 원가 통합 분석 가능

역할:
사용자가 제공하는 공사비 분석 데이터(공종별 비용, 자재비, 노무비, 경비)를 분석하여
구체적인 VE 절감 방안, 자재 대안, 공기 단축 가능성, 리스크 요인을 제시합니다.

출력 규칙:
1. 절감 방안은 반드시 구체적 금액 추정을 포함 (예: "약 1.2억 원 절감 가능")
2. 자재 대안은 품질 동등성을 보장하는 범위에서만 제안
3. 공기 단축은 공정 간섭을 고려한 현실적 범위로 제한
4. 숫자를 인용할 때 원본 데이터의 숫자를 정확히 사용
5. 추측이나 가정은 명확히 표시
6. 반드시 JSON 형식으로만 응답 (마크다운, 설명문 금지)
"""

# ── 유저 프롬프트 템플릿 ──
USER_PROMPT_TEMPLATE = """\
아래 공사비 분석 데이터를 해석하여 VE 절감 방안과 원가 분석 의견을 JSON으로 작성하세요.

## 프로젝트 개요
- 프로젝트명: {project_name}
- 건물 유형: {building_type}
- 연면적: {total_gfa_sqm}m²
- 층수: {floor_count}층

## 공사비 분석 데이터
{cost_json}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체를 반환하세요. 각 값은 문자열입니다:

{{
  "cost_analysis": "공사비 구성 분석 — 공종별 비중, 이상치 진단, 유사 프로젝트 대비 수준 평가",
  "ve_suggestions": "VE 절감 방안 3~5개 — 각 방안별 예상 절감 금액, 품질 영향도, 실현 가능성을 포함",
  "material_advice": "자재 대안 제안 — 품질 유지하면서 비용을 절감할 수 있는 구체적 자재 교체 방안",
  "schedule_impact": "공기 단축 가능성 분석 — Fast-track 공법, 공정 중첩, PC 공법 등 검토",
  "risk_factors": "공사비 리스크 요인 — 물가상승률, 인건비 변동, 원자재 수급, 환율 영향 분석"
}}
"""


class CostInterpreter:
    """공사비 분석 결과를 AI가 해석하여 VE 절감 방안을 제안."""

    def __init__(self, *, timeout_sec: float = 45.0) -> None:
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
            max_tokens=2048,
            timeout=self._timeout_sec,
        )
        return self._llm

    async def generate_interpretation(self, cost_data: dict) -> dict[str, str]:
        """공사비 분석 결과를 해석하여 VE 절감 방안을 생성.

        Args:
            cost_data: 공사비 분석 결과 dict

        Returns:
            5개 키를 가진 dict — 각 값은 해석 문자열.
            LLM 호출 실패 시 빈 dict 반환하여 호출자가 폴백 처리.
        """
        try:
            llm = self._get_llm()
        except Exception as e:
            logger.warning("LLM 초기화 실패", error=str(e))
            return {}

        compact = self._extract_compact_data(cost_data)

        project_name = cost_data.get("project_name", "미지정 프로젝트")
        building_type = cost_data.get("building_type", "미상")
        total_gfa_sqm = cost_data.get("total_gfa_sqm", 0)
        floor_count = cost_data.get("floor_count", 0)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            project_name=project_name,
            building_type=building_type,
            total_gfa_sqm=total_gfa_sqm,
            floor_count=floor_count,
            cost_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )

        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        logger.info(
            "공사비 AI 해석 요청",
            project=project_name[:20],
            prompt_chars=len(user_prompt),
        )

        try:
            response = await asyncio.wait_for(
                llm.ainvoke(messages),
                timeout=self._timeout_sec,
            )

            raw_text = response.content if hasattr(response, "content") else str(response)
            result = self._parse_response(raw_text)

            logger.info(
                "공사비 AI 해석 완료",
                project=project_name[:20],
                keys=list(result.keys()),
            )
            return result
        except Exception as e:
            logger.warning("공사비 AI 해석 생성 실패", error=str(e))
            return {}

    def _extract_compact_data(self, data: dict) -> dict[str, Any]:
        """공사비 분석 결과에서 LLM에 필요한 핵심 데이터만 추출."""
        compact: dict[str, Any] = {}

        # 총 공사비
        compact["total_cost"] = data.get("total_cost")
        compact["cost_per_sqm"] = data.get("cost_per_sqm")
        compact["cost_per_pyeong"] = data.get("cost_per_pyeong")

        # 공종별 비용 — 상위 10개
        items = data.get("cost_items", [])
        if items:
            sorted_items = sorted(
                items,
                key=lambda x: x.get("amount", 0),
                reverse=True,
            )
            compact["cost_items_top10"] = [
                {
                    "category": item.get("category"),
                    "subcategory": item.get("subcategory"),
                    "amount": item.get("amount"),
                    "ratio_pct": item.get("ratio_pct"),
                    "unit_price": item.get("unit_price"),
                }
                for item in sorted_items[:10]
            ]
            compact["cost_items_total_count"] = len(items)

        # 비용 구성 비율
        breakdown = data.get("cost_breakdown", {})
        if breakdown:
            compact["cost_breakdown"] = {
                "material_cost": breakdown.get("material_cost"),
                "labor_cost": breakdown.get("labor_cost"),
                "expense_cost": breakdown.get("expense_cost"),
                "overhead_cost": breakdown.get("overhead_cost"),
                "profit": breakdown.get("profit"),
                "material_ratio_pct": breakdown.get("material_ratio_pct"),
                "labor_ratio_pct": breakdown.get("labor_ratio_pct"),
            }

        # 공종별 요약
        by_trade = data.get("cost_by_trade", {})
        if by_trade:
            compact["cost_by_trade"] = {
                trade: {
                    "amount": detail.get("amount"),
                    "ratio_pct": detail.get("ratio_pct"),
                }
                for trade, detail in by_trade.items()
                if isinstance(detail, dict)
            }

        # 단가 비교 (벤치마크)
        benchmark = data.get("benchmark", {})
        if benchmark:
            compact["benchmark"] = {
                "avg_cost_per_sqm": benchmark.get("avg_cost_per_sqm"),
                "deviation_pct": benchmark.get("deviation_pct"),
                "comparison_projects": benchmark.get("comparison_projects", [])[:3],
            }

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
                    logger.warning("공사비 AI 응답 JSON 파싱 최종 실패", raw_length=len(raw))
                    return {"cost_analysis": text[:500]}
            else:
                logger.warning("공사비 AI 응답에서 JSON을 찾을 수 없음", raw_length=len(raw))
                return {"cost_analysis": text[:500]}

        expected_keys = [
            "cost_analysis",
            "ve_suggestions",
            "material_advice",
            "schedule_impact",
            "risk_factors",
        ]

        result: dict[str, str] = {}
        for key in expected_keys:
            val = parsed.get(key)
            if val is not None:
                result[key] = str(val)

        return result
