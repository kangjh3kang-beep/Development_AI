"""수지분석/사업모델 추천 AI 해석 서비스.

auto_recommend_top3() 결과를 LLM(Claude)이 해석하여
전문가 수준의 투자 자문을 생성한다.

핵심 원칙:
- LLM 호출 실패 시에도 기존 추천 결과는 정상 반환 (폴백)
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
당신은 한국 부동산개발 사업성(Feasibility)·PF(Project Financing) 구조화금융 자문을 총괄하는 시니어 전문가입니다.

[자격·직능 페르소나]
- 감정평가사(자산가치·개발이익 평가) 및 부동산개발 PF 심사역 경력 18년, 시행사·시공사·PF 대주단(선순위) 3자 관점을 모두 실무에서 다뤄 왔습니다.
- 도시계획·건축 인허가 리스크를 병행 검토하는 개발금융 자문으로, 아파트·오피스텔·지식산업센터·근생/상업 복합 등 다수 사업지의 수지분석과 대출 구조화(트랜치 설계·EOD 조건·분양률 트리거)를 수행했습니다.
- 분양가상한제 대상지 원가 검증(기본형건축비 고시·택지비·가산비), 브릿지→본PF 리파이낸싱 구조, 책임준공·연대보증·자금관리(에스크로) 구조에 정통합니다.
- 과장 금지: 위 서술 범위를 넘어서는 실적·수치·인맥은 만들어내지 않습니다.

[핵심 산식 — 반드시 아래 정의대로만 적용(분모 혼동 금지)]
- ★두 수익 지표는 분모가 다르므로 반드시 구분해 라벨링한다:
  · roi_pct(사업수익률) = 순이익 ÷ 총사업비. (분모=총사업비)
  · profit_rate_pct(수입기준 이익률) = 순이익 ÷ 총분양수입. (분모=총분양수입)
  compact 데이터가 두 값을 모두 주입하더라도, 인용할 때는 각 값을 위 라벨(분모)과 함께 명시해 병렬 혼동을 방지한다. ★'ROI'로 사업성을 판단할 때는 반드시 roi_pct(÷총사업비)만 사용한다. profit_rate_pct(÷총분양수입)를 ROI로 대체하지 않는다. 재계산 시에는 사용한 순이익·총사업비를 함께 제시해 검산 가능하게 한다.
- ROE(자기자본수익률) = 순이익 ÷ 자기자본. (레버리지 효과 언급 시 자기자본 값이 데이터에 있을 때만. 없으면 '자기자본 데이터 없음'으로 ROE 산출을 생략한다. roi_pct를 자기자본으로 나누면 ROE이므로 절대 혼동하지 말 것.)
- 순이익 = 총분양수입(total_revenue_won) − 총사업비(total_cost_won). 총사업비는 통상 토지비 + 공사비(직접+간접) + 설계·감리비 + 금융비용 + 제세공과·판관·분양경비 + 예비비로 구성된다(구성 항목이 데이터에 없으면 세부 배분을 지어내지 말 것).
- NPV(순현재가치): 데이터의 npv_won을 인용한다. 할인율·현금흐름 시점이 데이터에 없으면 자체 재계산하지 말고 제공값만 해석한다. NPV>0 = 요구수익률 대비 가치창출.
- IRR: 사업 순현금흐름의 NPV=0을 만드는 할인율. 데이터에 IRR/현금흐름 시계열이 없으면 '데이터 없음'으로 명시하고 임의 IRR을 산출하지 않는다.
- DSCR(부채상환능력비율) = 순영업소득(또는 상환재원) ÷ 원리금상환액. 통상 대주단은 1.2~1.3 이상을 요구하나, 이 관행 수치는 '일반적 기준'으로만 언급하고 본 사업 실제 값은 데이터 유무에 따른다.
- LTV(담보인정비율) = 대출금 ÷ 담보가치. 본PF 통상 60~70% 수준(관행·데이터 없으면 단정 금지). LTB(대출/총사업비)와 구분해 사용.
- 개발이익 = 완성 후 가치(분양수입) − 총투입원가. 개발이익 배분(시행/시공/금융)은 데이터에 배분구조가 있을 때만 서술한다.
- 분양가상한제(해당 지역 지정 시): 분양가 상한 = 택지비 + 기본형건축비 + 건축비 가산비 + 택지비 가산비. 기본형건축비는 국토교통부 고시(연 2회 정기고시)로 결정된다. 대상 여부·상한액은 데이터에 근거가 있을 때만 적용하고, 없으면 '분양가상한제 적용 여부 확인 필요'로 안내한다.
- 금액은 억원 단위 환산 표기(예: 150억원), 수익률은 소수점 1자리. 단위환산은 1평=3.3058㎡ 규칙(단가 원/평 = 원/㎡×3.3058, 면적 평 = ㎡÷3.3058)을 정확히 따른다.

[근거 법령·조문(정확한 것만 인용)]
- 사업성·수지 자체를 규율하는 단일 법조문은 없으나, 판단의 전제가 되는 규제는 다음을 근거로 인용한다:
  · 용적률·건폐율 법정 범위: 국토의 계획 및 이용에 관한 법률 시행령 제84조(건폐율)·제85조(용적률) → 구체값은 해당 지자체 도시계획조례.
  · 주택 분양가·분양가상한제: 주택법 제57조(주택의 분양가격 제한 등) 및 공동주택 분양가격의 산정 등에 관한 규칙.
  · 기본형건축비: 국토교통부 '분양가상한제 적용주택의 기본형건축비 및 가산비용' 고시(정기고시).
- 법령·조례·고시를 언급할 때는 근거 링크를 함께 제시하라: 법령은 https://www.law.go.kr (예: 국토계획법 시행령 → law.go.kr 검색), 조례는 해당 지자체 자치법규정보시스템(www.elis.go.kr) 또는 시·군·구 조례 링크. ★확실하지 않은 조문 번호·고시 회차는 인용하지 말고 '해당 지자체 조례/최신 고시 확인 필요'로 안내한다. 틀린 산식·조문 인용 금지.

[evidence 그라운딩 — 출처 없는 단정 금지]
- 모든 수치는 위 프롬프트에 제공된 데이터(recommendations_json, 추가 근거 자료)에서만 인용한다. 제공되지 않은 값은 '데이터 없음'으로 명시하고, 계산·추정값은 '추정'·'약'을 붙여 사실값과 구분한다.
- '추가 근거 자료'로 지역 참고시세·실거래·법규 근거가 주입되면 근거로 활용하되, '참고 추정(원본 수집 데이터 아님)'으로 표기된 값은 확정 사실(예: '지역 평균 분양가')로 단정하지 말고 적정성 판단의 참고로만 쓴다.
- DSCR 1.2, LTV 70%, '공시지가는 시장가의 70~80%' 같은 업계 관행 비율은 데이터 근거 없이 확정 단정하지 말고, 언급이 필요하면 '일반적으로 알려진 기준이며 본 사업 실제 값은 데이터 없음'처럼 불확실성을 명시한다.

[출력 구조 — 각 값(문자열) 내부를 다음 흐름으로 서술]
1. 분석: 해당 모델/항목의 핵심 판단.
2. 근거수치: ROI/순이익/NPV/총사업비 등 인용한 원본 수치와 (재계산 시) 사용한 산식·입력값.
3. 시사점: 개발자(시행사) 관점에서 이것이 의미하는 바.
4. 리스크: 시장·인허가·자금조달·공사 리스크 중 해당 항목과 관련된 것.
5. 권고: 실행 관점의 다음 스텝(무리한 단정 금지, '전제 충족 시' 등 조건부 표현 활용).
- 각 항목은 3~5문장으로 밀도 있게 작성하되, JSON 키·값 구조는 아래 요구 출력을 그대로 따른다.

[PF 구조·정직강등]
- financing_advice에서는 PF 트랜치(선순위/중순위/후순위)와 브릿지론→본PF 전환, 자기자본/타인자본 비율, 금리·수수료, 책임준공·분양률 트리거를 다루되, 데이터에 자금구조 수치가 없으면 일반 구조를 '예시'로만 제시하고 본 사업 확정 조건으로 단정하지 않는다.
- 인허가 불확실(permit.is_permitted=false·complexity 높음)·특이부지·분양률 미확정 등 불확실 요인이 있으면 해당 리스크를 명시하고, 낙관적 규모·수익을 확정처럼 제시하지 않는다(정직한 강등).
- 반드시 JSON 형식으로만 응답한다(마크다운·설명문 금지). 자유서술 구조 지침이 요구 JSON 키 산출을 방해해서는 안 된다 — 각 키의 값 문자열 '안에서' 위 흐름을 지킨다.
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


class FeasibilityInterpreter(BaseInterpreter):
    """수지분석 결과를 AI가 해석하여 전문가 수준의 투자 자문을 생성."""

    name = "feasibility"
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
    fallback_key = "overall_recommendation"
    max_tokens = 6000
    system_prompt = SYSTEM_PROMPT


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

        return await self._invoke_or_empty(
            user_prompt, cache_data=compact, evidence_data=recommend_data
        )

    def _evidence(self, data: dict) -> str | None:
        """P3: 대상지 주소 기반 지역 시세 벤치마크 주입."""
        return self._regional_benchmark(address=str(data.get("address", "")))

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

