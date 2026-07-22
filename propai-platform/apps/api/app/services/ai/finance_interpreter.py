"""개발금융(PF) AI 해석 서비스.

/api/v2/feasibility/development-finance(finance_cost_engine 재사용 — PF/브릿지론·LTV·DSCR)
산출 결과를 LLM(Claude)이 실무 관점으로 해석하여, 자금구조 평가·금리 민감도·리스크·
실행 권고를 서술한다.

핵심 원칙(P1 배선설계도 B-1 G6):
- 결정론 엔진(_build_development_finance)이 이미 계산한 수치(PF/브릿지 금액·금리·이자·
  LTV·DSCR)만 인용한다. 새 금융계산·재추정을 하지 않는다(BaseInterpreter GROUNDING_RULE 준수).
- LLM 호출 실패 시에도 기존 산출 결과는 정상 반환(폴백) — 이 인터프리터는 opt-in
  부가 해석일 뿐, 없어도 라우터 응답(pf_loan/bridge_loan/ltv/dscr 등)은 그대로 유효하다.
- 토큰 절약을 위해 핵심 데이터만 추출하여 프롬프트에 포함.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.services.ai.base_interpreter import BaseInterpreter

logger = structlog.get_logger()

# ── 시스템 프롬프트 ──
SYSTEM_PROMPT = """\
당신은 한국 부동산개발 PF(Project Financing) 구조화금융을 자문하는 시니어 심사역입니다.

경력:
- 부동산개발 PF 심사역 경력 18년 — 브릿지론→본PF 전환 구조, 트랜치(선순위/중순위/후순위)
  설계, LTV·DSCR 심사 기준 실무.
- 시행사·시공사·대주단(선순위) 3자 관점을 모두 실무에서 다뤄왔습니다.
- 책임준공·연대보증·분양률 트리거 같은 대주단 통상 조건에 정통합니다.
- 과장 금지: 위 서술 범위를 넘어서는 실적·수치·인맥은 만들어내지 않습니다.

[핵심 정의 — 반드시 아래대로만 적용]
- LTV(담보인정비율) = 총부채(브릿지+PF) ÷ 총사업비. 본PF 통상 60~70% 수준(관행이며 데이터
  근거 없이 본 사업 실제 값을 단정하지 않는다).
- DSCR(부채상환능력비율) = 연 순영업소득(NOI) ÷ 연 원리금상환액. 대주단은 통상 1.2~1.3
  이상을 요구하나, 이는 "일반적 기준"으로만 언급하고 데이터에 dscr 값이 없으면 "데이터
  없음(분양형 사업이라 NOI 미적용)"으로 명시한다.
- 자기자본비율(equity_ratio) = 자기자본 ÷ 총사업비. 레버리지(총부채/자기자본)를 언급할
  때는 이 값과 total_debt_won만 사용해 재계산하고, 사용한 산식을 함께 제시한다.

[grounding — 반드시 준수]
- 모든 수치(금액·금리·LTV·DSCR·기간)는 제공된 데이터에서만 인용한다. 없는 값은 "데이터
  없음"으로 명시하고, 임의로 채우지 않는다.
- dscr가 null이면 "DSCR 데이터 없음(분양형 사업 등 NOI 미제공)"으로 명시하고 임의 산출하지 않는다.
- 금리 민감도를 논할 때는 데이터의 rate(pf_loan.rate, bridge_loan.rate)를 기준으로 "±1%p
  변동 시 연간 이자 영향"처럼 데이터 값에 기반한 방향성만 서술하고, 새로운 금리 수치를
  단정적으로 제시하지 않는다.
- 반드시 JSON 형식으로만 응답한다(마크다운·설명문 금지).
"""

# ── 유저 프롬프트 템플릿 ──
USER_PROMPT_TEMPLATE = """\
아래 개발금융(PF) 산출 결과를 해석하여 전문 자문을 JSON으로 작성하세요.

## 개발금융 산출 데이터
{finance_json}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체를 반환하세요. 각 값은 문자열입니다:

{{
  "structure_analysis": "자금구조 분석 — 브릿지/PF 금액·비중, 자기자본비율, 트랜치 구조 평가",
  "rate_sensitivity": "금리 민감도 해석 — 현재 금리(pf_loan.rate/bridge_loan.rate) 기준 변동 영향 방향성",
  "risk_assessment": "리스크 평가 — LTV·DSCR 수준, 상환재원, 만기 구조 리스크",
  "recommendation": "실행 권고 — 자금조달 전략·트랜치 조정·대주단 협상 포인트(조건부 표현 활용)"
}}
"""


class FinanceInterpreter(BaseInterpreter):
    """개발금융(PF) 산출 결과를 AI가 해석하여 자금구조 자문을 생성."""

    name = "finance"
    expected_keys = [
        "structure_analysis",
        "rate_sensitivity",
        "risk_assessment",
        "recommendation",
    ]
    fallback_key = "structure_analysis"
    max_tokens = 4096
    system_prompt = SYSTEM_PROMPT

    async def generate_interpretation(self, finance_data: dict) -> dict[str, str]:
        """development-finance(_build_development_finance) 결과를 해석.

        Args:
            finance_data: _build_development_finance()의 반환값
                (total_project_cost_won/equity_won/pf_loan/bridge_loan/ltv/dscr 등).

        Returns:
            4개 키를 가진 dict — 각 값은 전문가 해석 문자열. LLM 실패 시 빈 dict.
        """
        compact = self._extract_compact_data(finance_data)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            finance_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )

        return await self._invoke_or_empty(user_prompt, cache_data=compact)

    def _extract_compact_data(self, data: dict) -> dict[str, Any]:
        """개발금융 산출 결과에서 LLM에 필요한 핵심 데이터만 추출."""
        pf = data.get("pf_loan") or {}
        bridge = data.get("bridge_loan") or {}
        return {
            "total_project_cost_won": data.get("total_project_cost_won"),
            "equity_won": data.get("equity_won"),
            "equity_ratio": data.get("equity_ratio"),
            "pf_loan": {
                "amount_won": pf.get("amount_won"),
                "rate": pf.get("rate"),
                "interest_won": pf.get("interest_won"),
                "guarantee_fee_won": pf.get("guarantee_fee_won"),
                "months": pf.get("months"),
                "total_cost_won": pf.get("total_cost_won"),
            },
            "bridge_loan": {
                "amount_won": bridge.get("amount_won"),
                "rate": bridge.get("rate"),
                "interest_won": bridge.get("interest_won"),
                "arrangement_fee_won": bridge.get("arrangement_fee_won"),
                "months": bridge.get("months"),
                "total_cost_won": bridge.get("total_cost_won"),
            },
            "total_debt_won": data.get("total_debt_won"),
            "ltv": data.get("ltv"),
            "dscr": data.get("dscr"),
            "annual_debt_service_won": data.get("annual_debt_service_won"),
            "total_financing_cost_won": data.get("total_financing_cost_won"),
        }
