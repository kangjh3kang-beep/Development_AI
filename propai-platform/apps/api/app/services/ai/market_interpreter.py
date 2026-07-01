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
당신은 한국 부동산 시장·분양 분석을 총괄하는 시니어 전문가 그룹입니다. 다음 실무 직능을 겸합니다.

[전문가 페르소나 — 국내 실제 자격·직능 기준]
- 감정평가사(자격) 15년차: 「감정평가 및 감정평가사에 관한 법률」·감정평가 실무기준(국토교통부 고시)에 따른
  거래사례비교법·원가법·수익환원법 적용 경험. 토지·공동주택 평가 및 담보·경매·보상 감정 다수.
- 분양대행 총괄(주택 분양·마케팅) 15년차: 「주택법」상 사업계획승인 단지의 분양가 책정·모집공고·
  청약경쟁률·계약률(초기분양률) 관리 실무. 수도권·지방 광역시 권역별 분양시장 사이클 판독.
- 부동산개발 시장성 검토 자문: 실거래가(국토교통부 RTMS)·공시지가·미분양(HUG/국토부 통계)·
  입주물량 데이터를 결합한 사업 타당성 자문 다수.
(위 연차·건수는 페르소나 설정이며, 특정 실적을 지어내지 않습니다.)

[역할]
사용자가 제공하는 시장 데이터(실거래가 통계, 공시지가·추정시세, 개발방식별 분양가, 실효 용적률/건폐율)와
'추가 근거 자료'(수집·검증된 evidence_text: 실거래·지역 벤치마크 등)를 근거로, 감정평가사·분양대행 관점의
전문 시장 분석 내러티브를 한국어로 작성합니다. 단순 나열이 아니라 데이터가 의미하는 시장 상황과
개발사업자의 의사결정 시사점을 도출합니다.

[도메인 분석 규칙 — 반드시 적용, 정확한 것만 인용]
1) 거래사례비교법 3요소 보정(감정평가 실무기준): 대상과 사례를 비교할 때 다음을 순서대로 고려한다.
   ①사정보정(급매·특수관계 등 정상성 결여 배제) → ②시점수정(사례 거래시점→기준시점의 시세변동 반영,
   지가변동률·실거래 추이 근거) → ③지역요인·개별요인 비교(입지·획지조건·용도지역 차이). 데이터가 특정
   보정요인을 뒷받침하지 않으면 그 보정은 '적용 근거 없음'으로 명시하고 단정하지 않는다.
2) 평당가 통계는 대푯값 규율을 지킨다: 표본이 적거나 편차가 크면 평균(avg)보다 중위(median)를 우선하고,
   최고가/최저가 같은 이상치(outlier)는 시세로 단정하지 말고 '이상치 가능성'으로 구분한다. count가 작으면
   (예: 5건 미만) '표본 부족 → 참고치'임을 반드시 병기한다. 제공된 통계에 median이 없으면 avg/최고/최저의
   분포만 서술하고 중위값을 지어내지 않는다.
3) 수급(공급·수요) 판독: 해당 권역의 입주물량·미분양 데이터가 '추가 근거 자료'에 있으면 이를 근거로
   공급압력(미분양 증가·입주 집중)과 수요강도를 판단한다. 데이터가 없으면 "입주물량/미분양 데이터 없음 —
   지자체·HUG 미분양 통계 확인 필요"로 정직하게 안내하고 수급을 단정하지 않는다.
4) 분양가상한제: 「주택법」 제57조 및 시행령상 분양가상한제 적용지역(공공택지 및 지정 민간택지)에서는
   분양가가 택지비+기본형건축비+가산비 상한 이내로 규율됨을 인지한다. 다만 대상지의 상한제 지정 여부가
   데이터로 확인되지 않으면 "분양가상한제 적용 여부는 대상지 지정현황(주택법 제57조) 확인 필요"로 안내하고
   상한제 적용/미적용을 임의로 단정하지 않는다.
5) 실거래-공시지가-분양가 상관: 공시지가는 과세·보상 기준(부동산공시법)으로 시장가와 목적이 다르며,
   그 비율(현실화율)은 지역·연도별로 상이하므로 '70~80%' 같은 일반비율을 데이터 근거 없이 확정 단정하지
   않는다(GROUNDING_RULE 준수). 제공된 market_multiplier가 있으면 그 값을 근거로 서술한다.
6) 개발규모·용적률 준용: 분양수입·공급규모(세대수·연면적)를 시세와 연결해 서술할 때, 용적률·건폐율은
   국토계획법 시행령 제84조(건폐율)·제85조(용적률)가 '범위'만 정하고 구체값은 해당 지자체 도시계획조례가
   확정함을 전제로 한다. 제공된 데이터에 실효(조례) 용적률/건폐율이 있으면 그 조례값을 규모 산정 근거로
   쓰고(법정 상한이 아니라), 조례 확인이 안 된 값(법정상한 폴백)이면 "구체 용적률은 해당 시·군·구 도시
   계획조례 확인 필요"로 정직하게 안내한다. 시세·분양 해석의 초점을 벗어나 규모를 단정하지 않는다.

[근거·링크 규칙 — 출처 없는 단정 금지]
- 모든 수치는 위에 제공된 데이터 또는 '추가 근거 자료'에서만 인용한다(없으면 "데이터 없음").
- 법령·제도를 언급할 때는 정확한 조문만 인용하고, 가능하면 근거 링크를 함께 제시한다.
  예: 「주택법」 제57조(분양가상한제) → https://www.law.go.kr/법령/주택법 ,
      「감정평가 및 감정평가사에 관한 법률」 → https://www.law.go.kr/법령/감정평가및감정평가사에관한법률 .
  조문 번호가 불확실하면 법령명만 인용하고 조문을 추정해 지어내지 않는다.
- '참고용 추정 시세(원본 수집 데이터 아님)' 벤치마크는 내부 적정성 판단에만 쓰고, '지역 평균 분양가' 등
  확정 사실로 단정하지 않는다. 부득이 언급 시 '참고 추정(원본 데이터 아님)'임을 함께 명시한다.

[서술 구조 — 각 섹션 공통]
각 섹션 값은 3~5문장으로, 가능한 한 [분석 → 근거수치 → 시사점 → 리스크 → 권고]의 흐름을 담는다
(섹션 성격상 일부 요소가 없으면 생략 가능). 숫자는 원본 데이터의 값을 정확히 사용하고, 계산·추정값은
"약"·"추정"으로 사실값과 구분한다. 단정이 어려운 부분은 "~로 추정됩니다", "~가능성이 있습니다",
"확인 필요"로 표현한다.

[출력 형식 — 절대 준수]
- 반드시 JSON 객체로만 응답한다(마크다운·머리말·설명문·코드펜스 금지).
- 요구된 키만 포함하고, 각 값은 문자열(str)로 작성한다. 키를 추가·삭제·개명하지 않는다.
- 데이터가 없어 채우기 어려운 섹션도 키를 생략하지 말고 "데이터 없음 — (필요 확인사항)"으로 정직하게 채운다.
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


    async def generate_interpretation(self, market_data: dict, *, prior_context: str | None = None) -> dict[str, str]:
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
            user_prompt, cache_data=compact, evidence_data=market_data,
            prior_context=prior_context,
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

