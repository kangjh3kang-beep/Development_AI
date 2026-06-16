"""G2B 입찰분석 AI 해석 서비스.

규칙기반 6엔진(도급 수지 Monte Carlo·QTO·용도지역·인허가·ESG·시장) 결과를
LLM(Claude)이 해석하여 투찰 전략·사업성·리스크·원가 경쟁력·종합 권고를
전문가 내러티브로 생성한다.

핵심 원칙(AVM interpreter 패턴 준수):
- LLM 호출 실패 시에도 기존 규칙기반 분석 결과는 정상 반환 (graceful fallback)
- 토큰 절약을 위해 핵심 수치만 추출하여 프롬프트에 포함
- API 키는 key_sanitizer 경유로 로드(오염 문자 방지)
- timeout 기본 15초
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

logger = structlog.get_logger()

# 모델 등급 매핑 (request.model_tier → 실제 모델 ID)
_MODEL_TIERS = {
    "standard": "claude-sonnet-4-5-20250929",
    "premium": "claude-opus-4-20250514",
}
_DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# ── 시스템 프롬프트 ──
SYSTEM_PROMPT = """\
당신은 한국 공공건설 입찰 전략 전문가이자 건설사업관리(CM) 컨설턴트입니다.

경력:
- 대형 건설사 견적·입찰팀 15년 경력 (조달청 나라장터 공사·용역 입찰 다수)
- 적격심사·종합심사낙찰제·적정 투찰가율 산정 전문
- 도급공사 실행예산·원가관리, 손익분기 분석
- 공공발주 리스크(발주처 신뢰도·경쟁강도·공사비 변동) 진단

역할:
규칙기반 분석 엔진이 산출한 입찰 수치(추정가격, 적정 투찰가율, 손익분기,
NPV/ROI/수익확률, 리스크 스코어, 지역 낙찰가율 통계 등)를 해석하여,
입찰 담당자가 '참여할지·얼마에 투찰할지'를 판단할 수 있는 실무 의견을 제시합니다.

출력 규칙:
1. 각 섹션은 2~4문장의 한국어로 작성
2. 제공된 수치(투찰가율·손익분기·NPV·ROI·리스크 점수)를 정확히 인용
3. 도급공사 현실(예정가격 대비 실행원가율, 낙찰가율-손익분기 마진)을 기준으로 분석
4. 데이터가 없거나 불확실하면 명확히 표시(과장·환상 금지)
5. 반드시 JSON 형식으로만 응답 (마크다운·설명문 금지)
6. 수익확률 100%·비현실적 고수익 같은 수치는 그대로 낙관하지 말고 근거를 비판적으로 검토
"""

# ── 유저 프롬프트 템플릿 ──
USER_PROMPT_TEMPLATE = """\
아래 공공입찰 분석 결과를 해석하여 입찰 의사결정 내러티브를 JSON으로 작성하세요.

## 분석 데이터
{analysis_json}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체를 반환하세요. 각 값은 한국어 문자열입니다:

{{
  "bid_strategy": "투찰 전략 — 적정 투찰가율(low/mid/high)의 근거, 지역 평균 낙찰가율 대비 포지셔닝, 권장 투찰 구간",
  "feasibility_view": "사업성 진단 — NPV/ROI/수익확률을 도급공사 관점에서 해석, 수주 매력도(낙찰가율-손익분기 마진)",
  "risk_assessment": "리스크 평가 — 공사비 변동/경쟁 강도/발주처 신뢰도 리스크를 종합하고 가장 큰 위협 식별",
  "cost_competitiveness": "원가 경쟁력 — 손익분기 낙찰가율 대비 시장가 여유, 실행원가 절감 필요성",
  "recommendation": "종합 권고 — 입찰 참여/조건부 참여/회피 중 하나의 명확한 의견과 핵심 근거 2~3가지"
}}
"""

_RESULT_KEYS = (
    "bid_strategy",
    "feasibility_view",
    "risk_assessment",
    "cost_competitiveness",
    "recommendation",
)


class BidInterpreter:
    """입찰 6엔진 분석 결과를 LLM이 해석하여 입찰 전략 내러티브를 생성."""

    def __init__(self, *, timeout_sec: float = 60.0) -> None:
        # 5개 섹션 한국어 해석(max_tokens 4096)은 생성에 25~50초가 걸릴 수 있어
        # 기본 타임아웃을 넉넉히 둔다(짧으면 asyncio.TimeoutError로 폴백됨).
        # max_tokens 2048은 풍부출력 중간 절단→JSON파싱실패 위험이 있어 4096으로 둔다.
        self._timeout_sec = timeout_sec

    def _resolve_model(self, model_tier: str) -> str:
        return _MODEL_TIERS.get(model_tier, _DEFAULT_MODEL)

    def _build_llm(self, model_id: str):
        """ChatAnthropic 인스턴스 생성. 키는 key_sanitizer 경유로 정상화."""
        from langchain_anthropic import ChatAnthropic

        from app.services.ai.key_sanitizer import get_clean_env_key

        api_key = get_clean_env_key("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

        return ChatAnthropic(
            model=model_id,
            anthropic_api_key=api_key,
            temperature=0.3,
            max_tokens=4096,
            timeout=self._timeout_sec,
        )

    async def generate_interpretation(
        self, analysis: dict, *, model_tier: str = "standard"
    ) -> dict[str, Any] | None:
        """입찰 분석 수치를 해석하여 내러티브 dict를 반환.

        Args:
            analysis: G2BBidAnalyzeResponse.model_dump() 또는 핵심 수치 dict.
            model_tier: "standard"(Sonnet) | "premium"(Opus).

        Returns:
            5개 해석 키 + model_used/generated를 담은 dict.
            LLM 호출 실패 시 None(호출자가 폴백 처리).
        """
        model_id = self._resolve_model(model_tier)
        try:
            llm = self._build_llm(model_id)
        except Exception as e:
            logger.warning("입찰 AI 해석 LLM 초기화 실패: %s", str(e)[:120])
            return None

        compact = self._extract_compact_data(analysis)
        user_prompt = USER_PROMPT_TEMPLATE.format(
            analysis_json=json.dumps(compact, ensure_ascii=False, indent=2),
        )

        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        try:
            logger.info("입찰 AI 해석 요청", model=model_id, prompt_chars=len(user_prompt))
            response = await asyncio.wait_for(
                llm.ainvoke(messages), timeout=self._timeout_sec
            )
            # 계측: BaseInterpreter 밖 직접 호출도 동일하게 토큰·과금 기록(best-effort)
            from app.services.ai.base_interpreter import record_llm_response_billing
            await record_llm_response_billing(llm, response, service="bid")
            raw_text = response.content if hasattr(response, "content") else str(response)
            result: dict[str, Any] = dict(self._parse_response(raw_text))
            result["model_used"] = model_id
            result["generated"] = True
            logger.info("입찰 AI 해석 완료", keys=list(result.keys()))
            return result
        except TimeoutError:
            logger.warning("입찰 AI 해석 타임아웃(%.0fs 초과)", self._timeout_sec)
            return None
        except Exception as e:
            logger.warning(
                "입찰 AI 해석 호출 실패: %s", f"{type(e).__name__}: {str(e)[:150]}"
            )
            return None

    def _extract_compact_data(self, data: dict) -> dict[str, Any]:
        """분석 결과에서 LLM에 필요한 핵심 수치만 추출(토큰 절약)."""
        compact: dict[str, Any] = {
            "공고명": data.get("bid_notice_nm"),
            "업무구분": data.get("bid_type"),
            "추정가격_원": data.get("estimated_price"),
            "적정투찰가율_퍼센트": {
                "low": data.get("recommended_bid_rate_low"),
                "mid": data.get("recommended_bid_rate_mid"),
                "high": data.get("recommended_bid_rate_high"),
            },
            "적정투찰가_원": data.get("recommended_bid_price"),
            "손익분기_낙찰가율_퍼센트": data.get("break_even_bid_rate"),
            "예상NPV_원": data.get("expected_npv"),
            "예상ROI_퍼센트": data.get("expected_roi"),
            "수익확률_퍼센트": data.get("profit_probability"),
            "리스크": {
                "공사비변동": data.get("risk_score_cost"),
                "발주처신뢰도": data.get("risk_score_trust"),
                "경쟁강도": data.get("risk_score_competition"),
                "종합": data.get("risk_score_total"),
            },
            "지역평균낙찰가율_퍼센트": data.get("region_avg_award_rate"),
            "유사입찰건수": data.get("similar_bids_count"),
        }

        # 정밀분석 섹션(있을 때만)
        spec = data.get("spec")
        if isinstance(spec, dict):
            compact["건축개요"] = {
                "건물유형": spec.get("building_type"),
                "연면적_제곱미터": spec.get("total_gfa_sqm"),
                "추정신뢰도": spec.get("confidence"),
                "추정출처": spec.get("source"),
            }
        cost = data.get("cost_breakdown")
        if isinstance(cost, dict):
            compact["원가"] = {
                "총공사비_원": cost.get("total_project_cost"),
                "직접비_원": cost.get("direct_cost"),
            }
        zoning = data.get("zoning")
        if isinstance(zoning, dict) and zoning.get("zone_type"):
            compact["용도지역"] = zoning.get("zone_type")
        esg = data.get("esg")
        if isinstance(esg, dict) and esg.get("grade"):
            compact["ESG등급"] = esg.get("grade")
        warns = data.get("analysis_warnings")
        if warns:
            compact["분석경고"] = warns[:5]

        # None 값 제거(토큰 절약)
        return {k: v for k, v in compact.items() if v is not None}

    def _parse_response(self, raw: str) -> dict[str, str]:
        """LLM 응답에서 JSON을 추출하여 dict로 파싱."""
        import re

        text = raw.strip()
        if "```" in text:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if match:
                text = match.group(1)

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                # 기대 키만 문자열로 정규화, 누락 키는 빈 문자열
                return {k: str(parsed.get(k, "")) for k in _RESULT_KEYS}
        except (ValueError, TypeError):
            pass

        # JSON 파싱 실패 시 전체 텍스트를 종합 권고에 할당
        return {k: ("" if k != "recommendation" else text[:800]) for k in _RESULT_KEYS}
