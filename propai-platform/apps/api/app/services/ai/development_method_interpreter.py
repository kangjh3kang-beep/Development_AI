"""개발방식 추천 AI 해석 서비스.

/api/v1/development-methods/optimal-recommend(IntegratedRecommender)이 산출한 다필지
통합 → 개발유형별 실효용적률 기준 수지 순위(ranked Top3)를 LLM(Claude)이 실무 관점으로
해석하여, 유형별 추천 근거·게이트(특이부지·잠정치·종상향)·다음 단계를 서술한다.

핵심 원칙(P1 배선설계도 B-1 G6):
- 결정론 엔진(IntegratedRecommender)이 이미 산출한 수치(용적률·수지·게이트)만 인용한다.
  새 수치를 계산하거나 지어내지 않는다(BaseInterpreter GROUNDING_RULE 준수).
- LLM 호출 실패 시에도 기존 추천 결과는 정상 반환(폴백) — 이 인터프리터는 opt-in
  부가 해석일 뿐, 없어도 라우터 응답(ranked 등)은 그대로 유효하다.
- 토큰 절약을 위해 핵심 데이터(Top3 + 게이트 요약)만 추출하여 프롬프트에 포함.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.services.ai.base_interpreter import BaseInterpreter

logger = structlog.get_logger()

# ── 시스템 프롬프트 ──
SYSTEM_PROMPT = """\
당신은 한국 부동산개발 사업방식(개발유형) 선정을 자문하는 시니어 전문가입니다.

경력:
- 도시계획기술사 상당 전문성 15년 — 용도지역·지구단위계획·종상향(정비/개발행위) 판정 실무.
- 시행사 사업기획 총괄 12년 — 개발유형(자체개발/합동개발/도시개발/정비사업 등)별 수지·인허가
  리스크를 비교해 최적 사업모델을 선정하는 의사결정을 다수 자문.
- 특이부지(맹지·학교용지·농지·산지·규제구역) 게이트 판정과 선행절차(용도변경·전용·폐도 등)
  전제 여부를 구분해 설명하는 데 정통합니다.

역할:
사용자가 제공하는 "개발유형별 수지 순위(Top3)"와 "게이트/정직고지" 데이터를 해석하여,
왜 해당 순위인지, 각 유형의 리스크·전제조건, 그리고 다음 실행 단계를 제시합니다.

[grounding — 반드시 준수]
- 모든 수치(용적률·연면적·순이익·수익률·NPV·composite)는 제공된 데이터에서만 인용한다.
  제공되지 않은 값은 "데이터 없음"으로 명시한다.
- far_basis가 "종상향"인 후보는 반드시 "고시·심의 통과를 전제로 한 조건부 시나리오"임을
  명시하고, far_basis="현행"과 같은 확정성으로 서술하지 않는다.
- tentative=true(게이트가 선행절차형 특이부지를 포함)인 경우, 해당 후보들이 선행절차
  통과를 전제로 한 잠정치임을 반드시 언급한다(확정 개발가능으로 단정 금지).
- land_price_reliable=false면 순이익·NPV 등 절대 수익성 수치가 "참고용"임을 명시한다.
- honest_disclosure에 담긴 정직 고지 문구를 무시하지 말고 해석에 반영한다.
- 반드시 JSON 형식으로만 응답한다(마크다운·설명문 금지).
"""

# ── 유저 프롬프트 템플릿 ──
USER_PROMPT_TEMPLATE = """\
아래 다필지 통합 개발방식 추천 결과(Top3 순위 + 게이트)를 해석하여 실무 자문을 JSON으로 작성하세요.

## 분석 대상
- 주소: {address}
- 주용도지역: {primary_zone}
- 통합 부지면적: {integrated_area_sqm}㎡
- 현행 실효용적률: {baseline_far_pct}%

## 추천 결과(게이트·Top3 순위)
{recommend_json}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체를 반환하세요. 각 값은 문자열입니다:

{{
  "overall_recommendation": "종합 추천 의견 — Top3 중 어떤 개발유형이 최적이고 왜인지, 게이트/정직고지 반영",
  "top1_analysis": "1위 개발유형 상세 분석 — 근거 수치(용적률·연면적·수지)와 전제조건",
  "top2_analysis": "2위 개발유형 분석 — 1위 대비 장단점",
  "top3_analysis": "3위 개발유형 분석 — 보수적 대안으로서의 가치",
  "gate_risk_assessment": "게이트·리스크 평가 — 특이부지 여부, 잠정치(tentative)/종상향 조건부 여부, 공시지가 신뢰성",
  "next_steps": "실행 관점의 다음 단계(선행절차·인허가·추가 조사 등, 무리한 단정 금지)"
}}
"""


class DevelopmentMethodInterpreter(BaseInterpreter):
    """다필지 통합 개발방식 추천(Top3) 결과를 AI가 해석하여 실무 자문을 생성."""

    name = "development_method"
    expected_keys = [
        "overall_recommendation",
        "top1_analysis",
        "top2_analysis",
        "top3_analysis",
        "gate_risk_assessment",
        "next_steps",
    ]
    fallback_key = "overall_recommendation"
    max_tokens = 4096
    system_prompt = SYSTEM_PROMPT

    async def generate_interpretation(self, recommend_data: dict) -> dict[str, str]:
        """optimal_recommend(IntegratedRecommender.recommend) 결과를 해석.

        Args:
            recommend_data: IntegratedRecommender().recommend()의 반환값
                (site/gate/integrated_area_sqm/baseline_far_pct/ranked/...).

        Returns:
            6개 키를 가진 dict — 각 값은 전문가 해석 문자열. LLM 실패 시 빈 dict.
        """
        compact = self._extract_compact_data(recommend_data)

        site = recommend_data.get("site") or {}
        address = ", ".join(site.get("addresses") or []) or "주소 미상"
        primary_zone = site.get("primary_zone") or "미상"
        integrated_area_sqm = recommend_data.get("integrated_area_sqm") or 0
        baseline_far_pct = recommend_data.get("baseline_far_pct") or 0

        user_prompt = USER_PROMPT_TEMPLATE.format(
            address=address,
            primary_zone=primary_zone,
            integrated_area_sqm=integrated_area_sqm,
            baseline_far_pct=baseline_far_pct,
            recommend_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )

        return await self._invoke(user_prompt, cache_data=compact)

    def _extract_compact_data(self, data: dict) -> dict[str, Any]:
        """추천 결과에서 LLM에 필요한 핵심 데이터(게이트 요약 + Top3)만 추출.

        input_used·evidence 같은 상세 부가정보는 제거해 토큰을 절약한다.
        """
        site = data.get("site") or {}
        gate = data.get("gate") or {}
        compact: dict[str, Any] = {
            "site": {
                "addresses": site.get("addresses"),
                "parcel_count": site.get("parcel_count"),
                "primary_zone": site.get("primary_zone"),
            },
            "integrated_area_sqm": data.get("integrated_area_sqm"),
            "baseline_far_pct": data.get("baseline_far_pct"),
            "scenario_status": data.get("scenario_status"),
            "land_price_reliable": data.get("land_price_reliable"),
            "honest_disclosure": data.get("honest_disclosure"),
            "gate": {
                "developability": gate.get("developability"),
                "resolvable": gate.get("resolvable"),
                "severity_label": gate.get("severity_label"),
            },
        }

        ranked = data.get("ranked") or []
        top3: list[dict[str, Any]] = []
        for i, cand in enumerate(ranked[:3]):
            if not isinstance(cand, dict):
                continue
            top3.append({
                "rank": i + 1,
                "method": cand.get("method"),
                "type_name": cand.get("type_name"),
                "applied_far_pct": cand.get("applied_far_pct"),
                "total_gfa_sqm": cand.get("total_gfa_sqm"),
                "net_profit_won": cand.get("net_profit"),
                "profit_rate_pct": cand.get("profit_rate_pct"),
                "npv_won": cand.get("npv"),
                "composite": cand.get("composite"),
                "far_basis": cand.get("far_basis"),
                "tentative": cand.get("tentative"),
                "upzoning_target_zone": cand.get("upzoning_target_zone"),
                "legal_basis": cand.get("legal_basis"),
            })
        compact["top3"] = top3

        return compact
