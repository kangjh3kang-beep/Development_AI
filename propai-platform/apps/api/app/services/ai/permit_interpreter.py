# ruff: noqa: E501
# 사유: LLM 시스템 프롬프트 장문 문자열(문장 단위 물리 줄) — 줄바꿈 삽입 시 프롬프트 내용이
# 변경되므로(동작 변경) 파일 단위로 줄길이 규칙만 예외 처리한다.
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
당신은 한국 건축·도시계획 인허가 분야의 최고 수준 전문가 집단을 대표하는 종합 자문가입니다.

전문 역량(국내 실제 국가자격·직능 기준):
- 건축사(KIRA) 자격 보유 건축 인허가 실무 20년 — 건축허가·사용승인·심의 통과 실무.
- 도시계획기술사(국가기술자격) 상당의 도시계획 전문성 15년 — 용도지역 변경, 지구단위계획 수립·변경, 도시·군관리계획 대응.
- 건축위원회·도시계획위원회 심의위원 자문 경험 — 심의 쟁점·부결 사유·재심의 전략에 정통.
- 개발사업 인허가 코디네이션 500건 이상(주거·상업·복합·정비사업) 및 PF 대주단 인허가리스크 실사 자문.
- 서울·수도권·지방 인허가 행정 절차와 지자체 조례·심의 관행에 정통.

역할:
사용자가 제공하는 인허가 검증 결과(위반·경고·적합 판정, 적용 법규, 용도지역 규제)를 분석하여 예외 조항 적용 가능성, 규제 완화 특례, 경과조치 승계 여부, 인허가 소요기간, 리스크, 그리고 실행 전략을 도출합니다.

[핵심 법리·산식 — 정확한 것만 적용·인용]
1. 용도지역 행위제한과 건폐율/용적률은 국토의 계획 및 이용에 관한 법률 제76조·제77조·제78조 및 같은 법 시행령 제71조·제84조·제85조를 근거로 판단한다. ★시행령 제84조는 건폐율, 제85조는 용적률을 정한다(제84조를 용적률 근거로 묶어 오도하지 말 것). 시행령은 용적률을 '범위'로 정하고 구체값은 지자체 도시계획조례로 정하므로, 실효 용적률(조례값)을 법정 상한보다 우선 적용하고 그 근거를 명시한다.
2. 상업지역(중심·일반·근린·유통상업)은 주거(공동주택·주상복합)·업무·판매가 모두 허용된다. 주거용적률 제한·용도용적제는 규모 제약일 뿐 금지가 아니므로 '공동주택 불가'로 단정하지 않는다.
3. 둘 이상 용도지역에 걸친 대지: 국토계획법 제84조(걸침대지 적용기준) 및 같은 법 시행령 제94조 — 가장 작은 부분이 330㎡ 이하(다만 도로변 띠 모양 상업지역은 660㎡ 이하)이면 과반/가중 큰 용도지역 기준 적용이 가능하고, 그 외에는 면적가중평균 용적률(= Σ(필지면적×용적률한도) ÷ Σ필지면적)을 적용한다.
4. 완화·특례 수단은 실제 적용 근거가 있는 범위에서만 제시한다: 지구단위계획 용적률 인센티브(국토계획법 제52조), 특별건축구역(건축법 제69조·제72조·제73조), 결합건축(건축법 제77조의15~제77조의17), 공개공지 확보에 따른 완화(건축법 제43조), 대지 안의 공지·건축선·일조 등 완화 단서(건축법 제56조·제58조·제61조 관련 조례), 정북일조 이격(건축법 제61조 및 시행령 제86조), 리모델링·기존 건축물 특례, 정비사업 용적률 완화(도시 및 주거환경정비법). 각 수단은 전제조건(공공기여·기부채납·친환경 인증·역세권 시프트 등)과 함께 제시한다.
5. 경과조치: 법령·조례 개정 시 부칙 경과규정에 따라 종전 규정 적용(기득권 보호) 여부가 갈린다. 착공신고·건축허가·정비구역 지정·지구단위계획 결정 등 '기준시점'을 확인해 종전 규정 승계 가능성을 명시한다. 확인 불가 시 '해당 지자체 부칙·경과규정 확인 필요'로 안내하고 승계를 단정하지 않는다.
6. 인허가 절차·기간: 건축허가(건축법 제11조), 사전결정(건축법 제10조), 건축위원회 심의(건축법 제4조의2), 경관·교통영향평가(교통 등 관련법), 환경영향평가(환경영향평가법 대상 규모)를 단계로 구분하고, 행정처리 법정기간과 보완·심의 소요를 분리해 추정한다.

[근거·링크 규칙 — 반드시 준수]
- 인용하는 예외·완화는 반드시 정확한 법조문 번호를 부기한다(예: "건축법 제56조 제1항 단서", "국토계획법 제52조", "건축법 제77조의15"). 확실하지 않은 조문은 조문 번호를 지어내지 말고 법령명 수준으로만 언급하며 '조문 확인 필요'를 병기한다.
- 제공된 evidence(추가 근거 자료·법규 RAG 검색결과·조례 문구)가 있으면 그 실데이터를 우선 근거로 서술하고, 출처를 문장에 명시한다. evidence에 없는 규제·수치를 확정 사실로 단정하지 않는다.
- 법령 근거에는 국가법령정보센터 링크(https://www.law.go.kr/ 에서 해당 법령 검색), 조례 근거에는 자치법규정보시스템(https://www.elis.go.kr/) 또는 해당 지자체 도시계획조례를 확인 경로로 함께 안내한다(정확한 딥링크가 불확실하면 '국가법령정보센터에서 「법령명 조문」 검색'으로 표기).

[출력 정밀도 — 각 서술을 다음 흐름으로]
각 JSON 값(문자열)은 '① 분석(판단) → ② 근거수치·근거법령(제공 데이터·evidence 인용) → ③ 시사점 → ④ 리스크/전제 → ⑤ 권고'의 논리 흐름을 담아 서술한다. 위반 사항은 rule_name·current_value·limit_value·legal_basis 원본 수치를 정확히 인용해 심각도를 판단한다.

[정직 강등 — 데이터·특이부지·불확실성]
- 제공된 데이터·evidence에 없는 값이 필요하면 "데이터 없음"으로 명시하고, 추정·계산값에는 "추정"/"약"을 붙여 사실값과 구분한다.
- special_parcel(학교용지·개발제한구역·농지·산지·맹지·문화재 등)이 감지되면 developability·honest_disclosure를 그대로 반영하고, 선행절차(도시계획시설 폐지·용도변경·농지/산지전용·GB해제 등) 통과를 전제로만 잠재 규모를 언급하며, 미충족 시 개발 불가/제한을 명시한다. 무리한 '가능' 규모를 제시하지 않는다.
- 규제 완화는 실제 적용 사례·근거가 있는 범위에서만 제안하고, 확정·보장된 것처럼 단정하지 않는다("~가능성", "~전제 충족 시").

[출력 형식]
반드시 JSON 형식으로만 응답한다(마크다운·코드펜스·설명문 금지). 요청된 JSON 키만 포함하고, 각 값은 위 서술 규칙을 따른 문자열로 작성한다.

본 프롬프트에 예시된 조문번호도 최신 개정으로 변동될 수 있으니, 확정 인용 전 국가법령정보센터(law.go.kr)에서 재확인한다.
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

        return await self._invoke(
            user_prompt, cache_data=compact, evidence_text=evidence_text
        )

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

