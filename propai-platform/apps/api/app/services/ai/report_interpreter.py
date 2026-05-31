"""보고서 내러티브 AI 해석 서비스.

파이프라인 7단계 결과를 종합하여 은행제출용/투자자용 보고서 내러티브를 생성한다.

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
당신은 한국 부동산 PF 대출 심사역 겸 투자 분석 전문가입니다.

경력:
- 부동산 프로젝트 파이낸싱 심사 15년 경력 (시중은행 PF팀)
- 부동산 투자 자문 및 펀드 운용 10년 경력
- 건설/부동산 개발 사업성 평가 전문가
- 은행 대출 심사 보고서, 투자 심사 보고서 수백 건 작성 경험

역할:
파이프라인 7단계 분석 결과(부지분석, 건축설계, 재무분석, 인허가, 공사비, 리스크, 법규)를
종합하여 은행 PF 심사역과 투자자가 의사결정에 활용할 수 있는 수준의 보고서 내러티브를 생성합니다.

출력 규칙:
1. 각 섹션은 3~5문장으로 핵심 판단 + 근거 수치를 포함
2. 숫자를 인용할 때 원본 데이터의 숫자를 정확히 사용
3. 은행 심사역 관점: 담보가치, 상환능력, 현금흐름 안정성에 초점
4. 투자자 관점: 수익률, 리스크 대비 수익, 출구전략에 초점
5. 추측이나 가정은 명확히 표시
6. 반드시 JSON 형식으로만 응답 (마크다운, 설명문 금지)
"""

# ── 유저 프롬프트 템플릿 ──
USER_PROMPT_TEMPLATE = """\
아래 부동산 개발 사업의 파이프라인 분석 결과를 종합하여 보고서 내러티브를 JSON으로 작성하세요.

## 프로젝트 개요
- 프로젝트명: {project_name}
- 주소: {address}
- 용도지역: {zone_type}
- 대지면적: {land_area_sqm}m²

## 파이프라인 분석 결과
{pipeline_json}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체를 반환하세요. 각 값은 문자열입니다:

{{
  "executive_summary": "경영진 요약 — 핵심 수치(사업비, 수익률, 분양가)와 투자 판단을 3~4문장으로",
  "site_narrative": "부지 분석 종합 평가 — 용적률, 건폐율, 입지 등급, 토지 시세를 종합",
  "financial_narrative": "재무 분석 종합 — 수익성(IRR, NPV), 자금조달 구조, 현금흐름 안정성",
  "risk_narrative": "리스크 종합 평가 — 시장/인허가/공사비/금리 리스크와 경감 방안",
  "recommendation_narrative": "최종 투자 추천 의견 — 투자 적합성, 조건부 승인 사항",
  "legal_compliance_narrative": "법규 적합성 종합 — 건축법/국토계획법/주택법 충족 여부, 인허가 전망"
}}
"""


class ReportInterpreter:
    """파이프라인 전체 결과를 AI가 종합하여 보고서 내러티브를 생성."""

    def __init__(self, *, timeout_sec: float = 90.0) -> None:
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
            max_tokens=4096,
            timeout=self._timeout_sec,
        )
        return self._llm

    async def generate_report_narrative(self, pipeline_result: dict) -> dict[str, str]:
        """파이프라인 7단계 결과를 종합하여 보고서 내러티브를 생성.

        Args:
            pipeline_result: 파이프라인 전체 실행 결과 dict

        Returns:
            6개 키를 가진 dict — 각 값은 보고서 내러티브 문자열.
            LLM 호출 실패 시 빈 dict 반환하여 호출자가 폴백 처리.
        """
        try:
            llm = self._get_llm()
        except Exception as e:
            logger.warning("LLM 초기화 실패", error=str(e))
            return {}

        compact = self._extract_compact_data(pipeline_result)

        project_name = pipeline_result.get("project_name", "미지정 프로젝트")
        address = pipeline_result.get("address", "주소 미상")
        zone_type = pipeline_result.get("zone_type", "미상")
        land_area_sqm = pipeline_result.get("land_area_sqm", 0)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            project_name=project_name,
            address=address,
            zone_type=zone_type,
            land_area_sqm=land_area_sqm,
            pipeline_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )

        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        logger.info(
            "보고서 내러티브 AI 해석 요청",
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
                "보고서 내러티브 AI 해석 완료",
                project=project_name[:20],
                keys=list(result.keys()),
            )
            return result
        except Exception as e:
            logger.warning("보고서 내러티브 AI 해석 생성 실패", error=str(e))
            return {}

    def _extract_compact_data(self, data: dict) -> dict[str, Any]:
        """전체 파이프라인 결과에서 LLM에 필요한 핵심 데이터만 추출."""
        compact: dict[str, Any] = {}

        # 부지분석 요약
        site = data.get("site_analysis", {})
        if site:
            compact["site_analysis"] = {
                "effective_far_pct": site.get("effective_far", {}).get("effective_far_pct"),
                "effective_bcr_pct": site.get("effective_far", {}).get("effective_bcr_pct"),
                "land_price_per_sqm": site.get("land_prices", {}).get("estimated_market_per_sqm"),
                "total_land_value": site.get("land_prices", {}).get("total_estimated_value_won"),
                "location_grade": site.get("location", {}).get("grade"),
                "location_score": site.get("location", {}).get("location_score"),
            }

        # 건축설계 요약
        design = data.get("building_design", {})
        if design:
            compact["building_design"] = {
                "total_gfa_sqm": design.get("total_gfa_sqm"),
                "floor_count": design.get("floor_count"),
                "unit_count": design.get("unit_count"),
                "development_type": design.get("development_type"),
            }

        # 재무분석 요약
        finance = data.get("financial_analysis", {})
        if finance:
            compact["financial_analysis"] = {
                "total_project_cost": finance.get("total_project_cost"),
                "total_revenue": finance.get("total_revenue"),
                "net_profit": finance.get("net_profit"),
                "profit_rate_pct": finance.get("profit_rate_pct"),
                "irr_pct": finance.get("irr_pct"),
                "npv": finance.get("npv"),
                "dscr": finance.get("dscr"),
                "loan_amount": finance.get("loan_amount"),
                "equity_amount": finance.get("equity_amount"),
            }

        # 공사비 요약
        cost = data.get("construction_cost", {})
        if cost:
            compact["construction_cost"] = {
                "total_cost": cost.get("total_cost"),
                "cost_per_sqm": cost.get("cost_per_sqm"),
                "cost_per_pyeong": cost.get("cost_per_pyeong"),
                "major_items_top3": cost.get("major_items", [])[:3],
            }

        # 인허가 요약
        permit = data.get("permit_analysis", {})
        if permit:
            compact["permit_analysis"] = {
                "overall_feasibility": permit.get("overall_feasibility"),
                "violation_count": permit.get("violation_count"),
                "warning_count": permit.get("warning_count"),
                "estimated_duration_months": permit.get("estimated_duration_months"),
            }

        # 리스크 요약
        risk = data.get("risk_assessment", {})
        if risk:
            compact["risk_assessment"] = {
                "overall_risk_level": risk.get("overall_risk_level"),
                "risk_score": risk.get("risk_score"),
                "top_risks": risk.get("top_risks", [])[:3],
            }

        # 법규 검토 요약
        legal = data.get("legal_review", {})
        if legal:
            compact["legal_review"] = {
                "compliance_status": legal.get("compliance_status"),
                "issues": legal.get("issues", [])[:3],
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
                    logger.warning("보고서 AI 응답 JSON 파싱 최종 실패", raw_length=len(raw))
                    return {"executive_summary": text[:500]}
            else:
                logger.warning("보고서 AI 응답에서 JSON을 찾을 수 없음", raw_length=len(raw))
                return {"executive_summary": text[:500]}

        expected_keys = [
            "executive_summary",
            "site_narrative",
            "financial_narrative",
            "risk_narrative",
            "recommendation_narrative",
            "legal_compliance_narrative",
        ]

        result: dict[str, str] = {}
        for key in expected_keys:
            val = parsed.get(key)
            if val is not None:
                result[key] = str(val)

        return result
