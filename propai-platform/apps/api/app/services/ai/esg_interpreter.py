"""ESG/탄소 분석 AI 해석 서비스.

ESG 분석 데이터를 LLM(Claude)이 해석하여
녹색건축 전략 및 탄소 저감 방안을 제안한다.

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
당신은 한국 부동산 ESG/녹색건축 전문 컨설턴트이자 탄소중립 전략가입니다.

경력:
- GRESB(글로벌 부동산 지속가능성 벤치마크) 평가 자문 10년
- G-SEED(녹색건축인증) 심사 및 컨설팅 전문가
- 제로에너지건축물(ZEB) 인증 및 로드맵 수립 경험 다수
- 에너지효율등급 1++등급 달성 프로젝트 50건 이상
- 탄소배출권거래제 및 RE100 대응 전략 수립

역할:
사용자가 제공하는 ESG/탄소 분석 데이터를 전문적이지만 이해하기 쉬운 한국어로 해석하고,
실행 가능한 녹색건축 전략과 탄소 저감 방안을 제시합니다.

출력 규칙:
1. 각 섹션별 해석은 2~4문장으로 작성
2. 구체적인 수치(탄소 감축량, 비용 절감액, 인증 점수 등)를 포함
3. 숫자를 인용할 때 원본 데이터의 숫자를 정확히 사용
4. 추측이나 가정은 명확히 표시
5. 반드시 JSON 형식으로만 응답 (마크다운, 설명문 금지)
"""

# ── 유저 프롬프트 템플릿 ──
USER_PROMPT_TEMPLATE = """\
아래 ESG/탄소 분석 데이터를 해석하여 녹색건축 전략을 JSON으로 작성하세요.

## 분석 데이터
{analysis_json}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체를 반환하세요. 각 값은 문자열입니다:

{{
  "carbon_assessment": "탄소배출량 종합 평가 (벤치마크 대비 수준, 배출원별 비중 분석)",
  "reduction_strategy": "탄소 저감 전략 3~5개 (각 전략별 구체적 감축량(tCO2/년) 및 비용 포함)",
  "certification_pathway": "녹색건축인증(G-SEED)/에너지효율 등급 취득 전략 (현재 수준→목표 등급, 필요 조치)",
  "zeb_roadmap": "제로에너지건축물(ZEB) 달성 로드맵 (단계별 목표, 핵심 기술, 예상 비용)",
  "esg_investment_impact": "ESG 적용에 따른 분양가/임대료 프리미엄 분석 (수치 기반 투자 대비 회수 전망)",
  "regulatory_outlook": "향후 ESG 규제 전망 및 선제 대응 방안 (2025~2030 규제 로드맵 기반)"
}}
"""


class EsgInterpreter(BaseInterpreter):
    """ESG/탄소 분석 결과를 AI가 해석하여 녹색건축 전략을 제안."""

    name = "esg"
    expected_keys = [
        "carbon_assessment",
        "reduction_strategy",
        "certification_pathway",
        "zeb_roadmap",
        "esg_investment_impact",
        "regulatory_outlook",
    ]
    fallback_key = "carbon_assessment"
    max_tokens = 4096
    system_prompt = SYSTEM_PROMPT


    async def generate_interpretation(self, esg_data: dict) -> dict[str, str]:
        """ESG 분석 데이터에 대한 해석 텍스트를 생성.

        Args:
            esg_data: ESG/탄소 분석 결과 dict

        Returns:
            6개 키를 가진 dict - 각 값은 전문가 해석 문자열.
            LLM 호출 실패 시 빈 dict가 아니라 None을 반환하여
            호출자가 폴백 처리할 수 있게 한다.
        """
        # 토큰 절약: 핵심 데이터만 추출
        compact = self._extract_compact_data(esg_data)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            analysis_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )

        return await self._invoke(user_prompt, cache_data=compact)

    def _extract_compact_data(self, data: dict) -> dict[str, Any]:
        """전체 ESG 분석 결과에서 LLM에 필요한 핵심 데이터만 추출."""
        compact: dict[str, Any] = {}

        # 탄소 배출 데이터
        carbon = data.get("carbon_emissions", {})
        if carbon:
            compact["carbon_emissions"] = {
                "total_emissions_tco2": carbon.get("total_emissions_tco2"),
                "emissions_per_sqm": carbon.get("emissions_per_sqm"),
                "benchmark_comparison": carbon.get("benchmark_comparison"),
                "scope1": carbon.get("scope1"),
                "scope2": carbon.get("scope2"),
                "scope3": carbon.get("scope3"),
            }

        # 에너지 효율 데이터
        energy = data.get("energy_efficiency", {})
        if energy:
            compact["energy_efficiency"] = {
                "rating": energy.get("rating"),
                "score": energy.get("score"),
                "primary_energy_kwh_sqm": energy.get("primary_energy_kwh_sqm"),
                "heating_demand": energy.get("heating_demand"),
                "cooling_demand": energy.get("cooling_demand"),
            }

        # GRESB 점수
        gresb = data.get("gresb_score", {})
        if gresb:
            compact["gresb_score"] = {
                "total_score": gresb.get("total_score"),
                "management_score": gresb.get("management_score"),
                "performance_score": gresb.get("performance_score"),
                "peer_ranking": gresb.get("peer_ranking"),
            }

        # G-SEED 인증 현황
        gseed = data.get("gseed", {})
        if gseed:
            compact["gseed"] = {
                "current_level": gseed.get("current_level"),
                "target_level": gseed.get("target_level"),
                "score": gseed.get("score"),
                "category_scores": gseed.get("category_scores"),
            }

        # ZEB 관련 데이터
        zeb = data.get("zeb", {})
        if zeb:
            compact["zeb"] = {
                "grade": zeb.get("grade"),
                "energy_independence_rate": zeb.get("energy_independence_rate"),
                "renewable_capacity_kw": zeb.get("renewable_capacity_kw"),
            }

        # 건축물 기본 정보
        building = data.get("building_info", {})
        if building:
            compact["building_info"] = {
                "total_gfa_sqm": building.get("total_gfa_sqm"),
                "building_type": building.get("building_type"),
                "floors": building.get("floors"),
            }

        # 기존 데이터에서 직접 존재하는 최상위 키 보존
        for key in ["address", "project_name", "building_type"]:
            if key in data:
                compact[key] = data[key]

        return compact

