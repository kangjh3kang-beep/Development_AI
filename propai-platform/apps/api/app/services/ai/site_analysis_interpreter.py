"""부지분석 AI 해석 서비스.

수집된 7개 섹션 분석 데이터를 LLM(Claude)이 해석하여
전문가 수준의 분석 설명을 생성한다.

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
당신은 한국 부동산 개발 전문 컨설턴트입니다.

경력:
- 국토계획법, 건축법, 주택법 전문 (20년 경력)
- 시장 분석 및 투자 자문
- 공공데이터(VWORLD, 국토교통부, 건축행정시스템) 기반 실증 분석

역할:
사용자가 제공하는 부지분석 데이터(용적률, 공급면적, 지가, 실거래가, 분양가, 입지, 개발계획)를
전문적이지만 이해하기 쉬운 한국어로 해석합니다.

출력 규칙:
1. 각 섹션별 해석은 2~4문장으로 작성
2. "왜 이 값인지", "이것이 의미하는 바", "개발자에게 주는 시사점"을 반드시 포함
3. 숫자를 인용할 때 원본 데이터의 숫자를 정확히 사용
4. 추측이나 가정은 명확히 표시
5. 반드시 JSON 형식으로만 응답 (마크다운, 설명문 금지)
"""

# ── 유저 프롬프트 템플릿 ──
USER_PROMPT_TEMPLATE = """\
아래 부지분석 데이터를 해석하여 각 섹션별 전문가 의견을 JSON으로 작성하세요.

## 분석 대상
- 주소: {address}
- 용도지역: {zone_type}
- 대지면적: {land_area_sqm}m² ({land_area_pyeong}평)

## 분석 데이터
{analysis_json}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체를 반환하세요. 각 값은 문자열입니다:

{{
  "effective_far_interpretation": "실효 용적률/건폐율에 대한 해석 (법적 근거, 조례 영향, 개발 가능 규모)",
  "supply_area_interpretation": "개발방식별 공급면적 분석 (최적 개발유형, 세대수, 수익성 시사점)",
  "land_price_interpretation": "토지 시세 해석 (공시지가 수준, 시장 보정, 토지매입 비용 시사점)",
  "transaction_interpretation": "주변 실거래가 해석 (시장 동향, 가격 수준, 수요 판단)",
  "sale_price_interpretation": "예상 분양가 해석 (지역 시세 대비, 분양성, 수익 예측)",
  "location_interpretation": "입지 분석 해석 (교통, 교육, 생활 인프라, 입지 등급)",
  "development_plan_interpretation": "개발계획 해석 (토지이용규제, 특수구역, 규제 리스크)",
  "overall_summary": "종합 평가 (이 부지의 개발 가치를 3~4문장으로 종합 판단)",
  "risk_factors": "주요 리스크 요인 (2~3개 핵심 리스크와 대응 방안)",
  "opportunity_factors": "개발 기회 요인 (2~3개 핵심 기회 요인)"
}}
"""


class SiteAnalysisInterpreter(BaseInterpreter):
    """수집된 부지분석 데이터를 AI가 해석하여 전문가 수준의 분석 설명을 생성."""

    name = "site_analysis"
    expected_keys = [
        "effective_far_interpretation",
        "supply_area_interpretation",
        "land_price_interpretation",
        "transaction_interpretation",
        "sale_price_interpretation",
        "location_interpretation",
        "development_plan_interpretation",
        "overall_summary",
        "risk_factors",
        "opportunity_factors",
    ]
    fallback_key = "overall_summary"
    max_tokens = 6000
    system_prompt = SYSTEM_PROMPT


    async def generate_interpretation(self, analysis_data: dict) -> dict[str, str]:
        """7개 섹션 각각에 대한 해석 텍스트를 생성.

        Args:
            analysis_data: ComprehensiveAnalysisService.analyze()의 반환값

        Returns:
            10개 키를 가진 dict — 각 값은 전문가 해석 문자열.
            LLM 호출 실패 시 빈 dict가 아니라 None을 반환하여
            호출자가 폴백 처리할 수 있게 한다.
        """
        # 토큰 절약: 핵심 데이터만 추출
        compact = self._extract_compact_data(analysis_data)

        address = analysis_data.get("address", "주소 미상")
        zone_type = analysis_data.get("zone_type", "미상")
        land_area_sqm = analysis_data.get("land_area_sqm", 0)
        land_area_pyeong = round(land_area_sqm / 3.305785, 1)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            address=address,
            zone_type=zone_type,
            land_area_sqm=land_area_sqm,
            land_area_pyeong=land_area_pyeong,
            analysis_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )

        return await self._invoke(
            user_prompt, cache_data=compact, evidence_data=analysis_data
        )

    def _evidence(self, data: dict) -> str | None:
        """P3: 대상지 주소 기반 지역 시세 벤치마크 주입."""
        return self._regional_benchmark(address=str(data.get("address", "")))

    def _extract_compact_data(self, data: dict) -> dict[str, Any]:
        """전체 분석 결과에서 LLM에 필요한 핵심 데이터만 추출.

        토큰 절약을 위해 불필요한 상세 데이터(items 배열, 시뮬레이션 테이블 등)를 제거.
        """
        compact: dict[str, Any] = {}

        # Section 1: 실효 용적률
        far = data.get("effective_far", {})
        if far:
            compact["effective_far"] = {
                "national_bcr_pct": far.get("national_bcr_pct"),
                "national_far_pct": far.get("national_far_pct"),
                "ordinance_bcr_pct": far.get("ordinance_bcr_pct"),
                "ordinance_far_pct": far.get("ordinance_far_pct"),
                "effective_bcr_pct": far.get("effective_bcr_pct"),
                "effective_far_pct": far.get("effective_far_pct"),
                "source": far.get("source"),
                "annotations": far.get("annotations", []),
            }

        # Section 2: 공급면적 — 상위 3개만
        supply = data.get("supply_areas", [])
        if supply:
            top_items = supply[:3]
            compact["supply_areas_top3"] = [
                {
                    "type_name": s.get("type_name"),
                    "applied_far_pct": s.get("applied_far_pct"),
                    "total_gfa_sqm": s.get("total_gfa_sqm"),
                    "unit_count": s.get("unit_count"),
                    "floor_count": s.get("floor_count"),
                    "estimated_construction_cost_won": s.get("estimated_construction_cost_won"),
                    "permit_complexity": s.get("permit_complexity"),
                    "feasibility_status": s.get("feasibility_status"),
                }
                for s in top_items
            ]
            compact["supply_areas_total_count"] = len(supply)

        # Section 3: 토지 시세
        lp = data.get("land_prices", {})
        if lp:
            compact["land_prices"] = {
                "official_price_per_sqm": lp.get("official_price_per_sqm"),
                "official_price_per_pyeong": lp.get("official_price_per_pyeong"),
                "total_official_value_won": lp.get("total_official_value_won"),
                "estimated_market_per_sqm": lp.get("estimated_market_per_sqm"),
                "total_estimated_value_won": lp.get("total_estimated_value_won"),
            }

        # Section 4: 실거래가 — 통계만
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

        # Section 5: 분양가 — 상위 3개
        sale = data.get("sale_prices", [])
        if sale:
            compact["sale_prices_top3"] = [
                {
                    "type_name": s.get("type_name"),
                    "sale_price_per_pyeong_man": s.get("sale_price_per_pyeong_man"),
                    "sale_price_per_sqm_man": s.get("sale_price_per_sqm_man"),
                }
                for s in sale[:3]
            ]

        # Section 6: 입지
        loc = data.get("location", {})
        if loc:
            compact["location"] = {
                "nearest_subway": loc.get("transportation", {}).get("nearest_subway"),
                "subway_accessible": loc.get("transportation", {}).get("subway_accessible"),
                "school_count": loc.get("education", {}).get("school_count"),
                "location_score": loc.get("location_score"),
                "grade": loc.get("grade"),
            }

        # Section 7: 개발계획
        dev = data.get("development_plans", {})
        if dev:
            compact["development_plans"] = {
                "special_districts": dev.get("special_districts", []),
                "land_use_regulations": dev.get("land_use_regulations", []),
            }

        return compact

