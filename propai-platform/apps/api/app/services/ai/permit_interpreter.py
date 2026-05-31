"""인허가 AI 해석 서비스.

인허가 검증 결과에서 예외 조항/완화 가능성을 AI가 분석한다.

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
당신은 한국 건축 인허가 전문 행정사 겸 도시계획 전문가입니다.

경력:
- 건축 인허가 행정사 18년 경력 (주거/상업/복합 건축물)
- 도시계획 전문가 15년 경력 (용도지역 변경, 지구단위계획)
- 건축법, 국토계획법, 주택법, 도시정비법 전문
- 인허가 예외 조항 및 규제 완화 특례 적용 경험 500건 이상
- 서울/수도권/지방 인허가 행정 절차 및 관행에 정통

역할:
사용자가 제공하는 인허가 검증 결과(법규 위반 사항, 경고, 적합 판정)를 분석하여
예외 조항 적용 가능성, 규제 완화 특례, 인허가 전략을 제시합니다.

출력 규칙:
1. 예외 조항은 반드시 관련 법조문 번호를 인용 (예: "건축법 제56조 제1항 단서")
2. 규제 완화는 실제 적용 사례가 있는 범위에서만 제안
3. 기간 추정은 행정 절차와 보완 기간을 구분하여 제시
4. 숫자를 인용할 때 원본 데이터의 숫자를 정확히 사용
5. 추측이나 가정은 명확히 표시
6. 반드시 JSON 형식으로만 응답 (마크다운, 설명문 금지)
"""

# ── 유저 프롬프트 템플릿 ──
USER_PROMPT_TEMPLATE = """\
아래 인허가 검증 결과를 분석하여 예외 조항/완화 가능성과 인허가 전략을 JSON으로 작성하세요.

## 프로젝트 개요
- 주소: {address}
- 용도지역: {zone_type}
- 건물 유형: {building_type}
- 연면적: {total_gfa_sqm}m²
- 층수: {floor_count}층

## 인허가 검증 결과
{permit_json}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체를 반환하세요. 각 값은 문자열입니다:

{{
  "permit_assessment": "인허가 난이도 종합 평가 — 위반 사항 수, 심각도, 전체적인 인허가 가능성 판단",
  "exception_analysis": "적용 가능한 예외 조항 분석 — 각 위반 사항별 관련 법조문 예외/단서 조항 검토",
  "relaxation_options": "규제 완화/특례 적용 가능성 — 지구단위계획, 특별건축구역, 결합건축 등 완화 수단",
  "timeline_estimate": "인허가 소요 기간 추정 — 건축허가, 사전심의, 환경영향평가 등 단계별 소요 기간",
  "risk_factors": "인허가 리스크 요인 — 주민 반대, 일조권, 교통영향평가, 행정 지연 등",
  "strategy_recommendation": "인허가 전략 제안 — 사전협의, 분할 신청, 설계 변경 등 최적 전략"
}}
"""


class PermitInterpreter(BaseInterpreter):
    """인허가 검증 결과를 AI가 해석하여 예외 조항/완화 가능성을 분석."""

    name = "permit"
    expected_keys = [
        "permit_assessment",
        "exception_analysis",
        "relaxation_options",
        "timeline_estimate",
        "risk_factors",
        "strategy_recommendation",
    ]
    fallback_key = "permit_assessment"
    max_tokens = 4096
    system_prompt = SYSTEM_PROMPT


    async def generate_interpretation(
        self, permit_data: dict, *, evidence_text: str | None = None
    ) -> dict[str, str]:
        """인허가 검증 결과를 해석하여 예외 조항/완화 가능성을 분석.

        Args:
            permit_data: 인허가 검증 결과 dict
            evidence_text: P3 — 호출처가 async로 만든 근거(법규 RAG 검색결과 등)를
                그대로 부착. None이면 미부착.

        Returns:
            6개 키를 가진 dict — 각 값은 해석 문자열.
            LLM 호출 실패 시 빈 dict 반환하여 호출자가 폴백 처리.
        """
        compact = self._extract_compact_data(permit_data)

        address = permit_data.get("address", "주소 미상")
        zone_type = permit_data.get("zone_type", "미상")
        building_type = permit_data.get("building_type", "미상")
        total_gfa_sqm = permit_data.get("total_gfa_sqm", 0)
        floor_count = permit_data.get("floor_count", 0)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            address=address,
            zone_type=zone_type,
            building_type=building_type,
            total_gfa_sqm=total_gfa_sqm,
            floor_count=floor_count,
            permit_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )

        return await self._invoke(user_prompt, cache_data=compact)

    def _extract_compact_data(self, data: dict) -> dict[str, Any]:
        """인허가 검증 결과에서 LLM에 필요한 핵심 데이터만 추출."""
        compact: dict[str, Any] = {}

        # 전체 판정
        compact["overall_feasibility"] = data.get("overall_feasibility")
        compact["violation_count"] = data.get("violation_count", 0)
        compact["warning_count"] = data.get("warning_count", 0)
        compact["pass_count"] = data.get("pass_count", 0)

        # 위반 사항 목록 (전체)
        violations = data.get("violations", [])
        if violations:
            compact["violations"] = [
                {
                    "rule_name": v.get("rule_name"),
                    "category": v.get("category"),
                    "severity": v.get("severity"),
                    "current_value": v.get("current_value"),
                    "limit_value": v.get("limit_value"),
                    "description": v.get("description"),
                    "legal_basis": v.get("legal_basis"),
                }
                for v in violations
            ]

        # 경고 사항 목록 (상위 5개)
        warnings = data.get("warnings", [])
        if warnings:
            compact["warnings"] = [
                {
                    "rule_name": w.get("rule_name"),
                    "category": w.get("category"),
                    "current_value": w.get("current_value"),
                    "limit_value": w.get("limit_value"),
                    "margin_pct": w.get("margin_pct"),
                    "description": w.get("description"),
                }
                for w in warnings[:5]
            ]

        # 적합 항목 요약 (카테고리별 개수만)
        passes = data.get("passes", [])
        if passes:
            categories: dict[str, int] = {}
            for p in passes:
                cat = p.get("category", "기타")
                categories[cat] = categories.get(cat, 0) + 1
            compact["pass_categories"] = categories

        # 적용 법규 목록
        regulations = data.get("applied_regulations", [])
        if regulations:
            compact["applied_regulations"] = [
                {
                    "name": r.get("name"),
                    "code": r.get("code"),
                    "category": r.get("category"),
                }
                for r in regulations[:10]
            ]

        # 용도지역 관련 규제
        zoning = data.get("zoning_constraints", {})
        if zoning:
            compact["zoning_constraints"] = {
                "zone_type": zoning.get("zone_type"),
                "allowed_uses": zoning.get("allowed_uses", [])[:5],
                "max_far_pct": zoning.get("max_far_pct"),
                "max_bcr_pct": zoning.get("max_bcr_pct"),
                "max_height_m": zoning.get("max_height_m"),
            }

        return compact

