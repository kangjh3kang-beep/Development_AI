"""전문가 패널 + 검증 서비스 (다관점 분석·토론·통합).

분석 결과/맥락을 입력받아, 분석 유형별 관련 전문가(설계사·디벨로퍼·인허가공무원·
도시개발·지구단위·부동산학교수·법률가·정비전문가 등) 관점에서 분석하고 쟁점을
토론한 뒤 통합 결론과 검증(반론·리스크·신뢰도)을 제시한다.

- mode="single": 1회 LLM 호출(빠름·저렴, 기본). 다관점+토론+검증을 구조화 출력.
- mode="deep": 전문가별 병렬 LLM + 통합·검증 호출(정밀·고비용).
LLM 실패 시 graceful 폴백.
"""

import asyncio
import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 분석 유형별 전문가 배치
ROSTERS: dict[str, list[dict[str, str]]] = {
    "permit": [
        {"role": "인허가 행정공무원", "lens": "인허가 절차·행정 처리 가능성·민원 관점"},
        {"role": "건축사", "lens": "건축법·설계 적합성·기술적 실현 가능성"},
        {"role": "정비사업 전문가", "lens": "정비·소규모정비 사업성·조합/주민 동의 관점"},
        {"role": "부동산 법률가", "lens": "법적 리스크·소송·권리관계 관점"},
        {"role": "디벨로퍼", "lens": "사업 수익성·일정·리스크 관점"},
    ],
    "regulation": [
        {"role": "도시계획 전문가", "lens": "상위계획 정합성·용도지역·도시관리계획 관점"},
        {"role": "지구단위계획 전문가", "lens": "지구단위·인센티브·공공기여 관점"},
        {"role": "인허가 행정공무원", "lens": "조례 적용·행정 재량·심의 관점"},
        {"role": "부동산 법률가", "lens": "규제 충돌·법적 제약·구제수단 관점"},
    ],
    "market": [
        {"role": "부동산학 교수", "lens": "시장 구조·수급·가격 형성 이론 관점"},
        {"role": "디벨로퍼", "lens": "실수요·분양성·타이밍 관점"},
        {"role": "감정평가사", "lens": "적정 시세·평가·담보가치 관점"},
        {"role": "분양마케팅 전문가", "lens": "수요층·분양전략·경쟁상품 관점"},
    ],
    "feasibility": [
        {"role": "디벨로퍼", "lens": "총사업비·수지·자금조달 관점"},
        {"role": "PF 금융 전문가", "lens": "대출가능성·금융구조·리스크 관점"},
        {"role": "시공/적산 전문가", "lens": "공사비·공기·시공 리스크 관점"},
        {"role": "부동산학 교수", "lens": "투자수익·민감도·시장 사이클 관점"},
    ],
    "site": [
        {"role": "도시개발 전문가", "lens": "입지·개발 잠재력·기반시설 관점"},
        {"role": "건축사", "lens": "용도지역 한도·배치·설계 가능성 관점"},
        {"role": "디벨로퍼", "lens": "최유효이용·사업화 관점"},
        {"role": "감정평가사", "lens": "토지가치·공시지가·시세 관점"},
    ],
    "cost": [
        {"role": "시공/적산 전문가", "lens": "공종별 물량·단가·적산 정확성 관점"},
        {"role": "건설사업관리(CM)", "lens": "공기·공정·간접비·현장 리스크 관점"},
        {"role": "구조기술사", "lens": "구조형식·물량 합리성(콘크리트·철근) 관점"},
        {"role": "디벨로퍼", "lens": "총공사비 적정성·예비비·물가변동 관점"},
    ],
    "tax": [
        {"role": "세무사", "lens": "취득·보유·양도세율 적용·중과·감면 정확성 관점"},
        {"role": "회계사", "lens": "과세표준·세후 현금흐름·법인/개인 구조 관점"},
        {"role": "부동산 법률가", "lens": "세법 개정·해석·불복 리스크 관점"},
        {"role": "디벨로퍼", "lens": "세부담이 사업수지에 미치는 영향 관점"},
    ],
    "esg": [
        {"role": "LCA/탄소 전문가", "lens": "전과정평가(EN15978)·내재/운영 탄소 산정 관점"},
        {"role": "녹색건축 인증 심사원", "lens": "G-SEED·에너지효율·인증 기준 관점"},
        {"role": "ESG 금융 전문가", "lens": "K-택소노미·녹색금융·공시 관점"},
        {"role": "건축 설비기술사", "lens": "에너지·설비 성능·저감수단 관점"},
    ],
    "design": [
        {"role": "건축사", "lens": "배치·평면·법규 적합성·설계 품질 관점"},
        {"role": "구조기술사", "lens": "구조 합리성·시공성 관점"},
        {"role": "디벨로퍼", "lens": "분양성·평형구성·수익 최적화 관점"},
        {"role": "도시계획 전문가", "lens": "용도지역 한도·일조·인동간격 관점"},
    ],
}
_DEFAULT_ROSTER = [
    {"role": "디벨로퍼", "lens": "사업성·실현가능성 관점"},
    {"role": "부동산학 교수", "lens": "시장·이론 관점"},
    {"role": "부동산 법률가", "lens": "법적 리스크 관점"},
    {"role": "도시계획 전문가", "lens": "도시계획·규제 관점"},
]

_SUBJECTS = {
    "permit": "이 부지의 인허가 가능성·개발방식 분석",
    "regulation": "이 부지에 적용되는 규제 환경 분석",
    "market": "이 지역의 부동산 시장 분석",
    "feasibility": "이 사업의 사업성(수지) 분석",
    "site": "이 부지의 부지분석",
    "cost": "이 사업의 공사비·적산 분석",
    "tax": "이 사업의 부동산 조세 분석",
    "esg": "이 건축물의 ESG·탄소(전과정평가) 분석",
    "design": "이 부지의 건축 설계(배치·평형·법규) 분석",
}

_PANEL_SYSTEM = """\
당신은 부동산개발 전문가 패널의 진행자입니다. 주어진 분석 자료를 바탕으로 각 전문가가
자신의 전문 관점에서 독립적으로 검토하고, 핵심 쟁점을 토론한 뒤, 다관점을 통합한 최종
의견과 검증(반론·리스크·신뢰도)을 제시합니다.
원칙: 제공 데이터에 근거하고 과장·허위 금지. 전문가마다 관점 차이를 분명히 드러낼 것.
반드시 JSON만 출력."""

_PANEL_TMPL = """\
## 분석 주제
{subject} — {address}

## 분석 자료(요약)
{context}

## 참여 전문가
{roster}

## 출력 JSON 스키마
{{
  "experts": [
    {{"role": "전문가명", "opinion": "해당 관점 핵심 의견(2~3문장)",
      "key_points": ["근거·포인트 1~3개"], "concerns": ["우려·이견 1~2개"]}}
  ],
  "debate": [
    {{"issue": "쟁점", "positions": "전문가간 이견 요약", "resolution": "토론 결과·절충"}}
  ],
  "consensus": "다관점 통합 최종 의견(3~5문장, 가장 합리적인 결론)",
  "recommended_actions": ["실행 권고 2~4개"],
  "verification": {{
    "confidence": 0-100 정수(분석 신뢰도),
    "risks": ["검증상 핵심 리스크 1~3개"],
    "counterpoints": ["주의해야 할 반론·맹점 1~3개"],
    "data_gaps": ["추가 확인 필요 데이터 0~3개"]
  }}
}}
전문가는 위 명단 그대로 분석하세요.
"""

_EXPERT_SYSTEM = """\
당신은 한국 부동산개발 분야의 해당 전문가입니다. 제시된 분석 자료를 당신의 전문 관점에서만
검토해 의견을 제시합니다. 데이터 근거·과장 금지. JSON만 출력."""

_EXPERT_TMPL = """\
## 당신의 역할: {role} ({lens})
## 분석 주제: {subject} — {address}
## 분석 자료(요약)
{context}

## 출력 JSON
{{"role": "{role}", "opinion": "당신 관점의 핵심 의견(2~3문장)",
  "key_points": ["근거 1~3개"], "concerns": ["우려·이견 1~2개"]}}
"""

_SYNTH_SYSTEM = """\
당신은 전문가 패널 진행자입니다. 각 전문가 의견을 종합해 쟁점을 정리하고, 다관점을
통합한 최종 결론과 검증(반론·리스크·신뢰도)을 제시합니다. 과장 금지. JSON만 출력."""

_SYNTH_TMPL = """\
## 분석 주제: {subject} — {address}
## 전문가 의견
{opinions}

## 출력 JSON 스키마
{{
  "debate": [{{"issue":"쟁점","positions":"이견 요약","resolution":"토론 결과"}}],
  "consensus": "다관점 통합 최종 의견(3~5문장)",
  "recommended_actions": ["실행 권고 2~4개"],
  "verification": {{"confidence": 0-100 정수, "risks":["1~3개"],
    "counterpoints":["1~3개"], "data_gaps":["0~3개"]}}
}}
"""


def _strip_json(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        raw = raw[4:] if raw.lower().startswith("json") else raw
    return raw.strip()


class ExpertPanelService:
    async def analyze(
        self,
        analysis_type: str,
        context: dict[str, Any] | str,
        address: str = "",
        mode: str = "single",
    ) -> dict[str, Any]:
        roster = ROSTERS.get(analysis_type, _DEFAULT_ROSTER)
        subject = _SUBJECTS.get(analysis_type, "부동산개발 분석")
        ctx_str = context if isinstance(context, str) else json.dumps(context, ensure_ascii=False)
        ctx_str = ctx_str[:4000]

        if mode in ("deep", "graph"):
            # LangGraph 일원화: 전문가(다각도) → 검증(원데이터 대조·할루시네이션 게이트) → 통합.
            try:
                from app.services.expert_panel.expert_panel_graph import run_panel_graph
                result = await run_panel_graph(subject, address, ctx_str, roster)
                if not (result and result.get("consensus")):
                    raise ValueError("graph 결과 없음")
            except Exception as e:  # noqa: BLE001
                logger.warning("전문가 패널(graph) 실패, deep 폴백: %s", str(e)[:100])
                result = await self._deep(subject, address, ctx_str, roster)
        else:
            result = await self._single(subject, address, ctx_str, roster)
        result["analysis_type"] = analysis_type
        result["mode"] = mode
        result["roster"] = [r["role"] for r in roster]
        return result

    async def _single(self, subject, address, ctx, roster) -> dict[str, Any]:
        try:
            from app.services.ai.llm_provider import get_llm
            from app.services.ai.base_interpreter import GROUNDING_RULE
            from langchain_core.messages import HumanMessage, SystemMessage

            roster_str = "\n".join(f"- {r['role']} ({r['lens']})" for r in roster)
            user = _PANEL_TMPL.format(subject=subject, address=address or "대상지",
                                      context=ctx, roster=roster_str)
            llm = get_llm(timeout=75, max_tokens=3500)
            resp = await llm.ainvoke(
                [SystemMessage(content=_PANEL_SYSTEM + GROUNDING_RULE), HumanMessage(content=user)]
            )
            # 계측: BaseInterpreter 밖 직접 호출도 동일하게 토큰·과금 기록(best-effort)
            from app.services.ai.base_interpreter import record_llm_response_billing
            await record_llm_response_billing(llm, resp, service="expert_panel")
            data = json.loads(_strip_json(resp.content if hasattr(resp, "content") else str(resp)))
            if not isinstance(data.get("experts"), list):
                raise ValueError("experts 누락")
            data["generated"] = True
            return data
        except Exception as e:  # noqa: BLE001
            logger.warning("전문가 패널(single) 실패, 폴백", err=str(e)[:100])
            return self._fallback(roster)

    async def _deep(self, subject, address, ctx, roster) -> dict[str, Any]:
        try:
            from app.services.ai.llm_provider import get_llm
            from app.services.ai.base_interpreter import GROUNDING_RULE
            from langchain_core.messages import HumanMessage, SystemMessage

            async def one_expert(r: dict) -> dict[str, Any]:
                user = _EXPERT_TMPL.format(role=r["role"], lens=r["lens"],
                                           subject=subject, address=address or "대상지", context=ctx)
                llm = get_llm(timeout=60, max_tokens=900)
                resp = await llm.ainvoke(
                    [SystemMessage(content=_EXPERT_SYSTEM + GROUNDING_RULE), HumanMessage(content=user)]
                )
                from app.services.ai.base_interpreter import record_llm_response_billing
                await record_llm_response_billing(llm, resp, service="expert_panel")
                try:
                    d = json.loads(_strip_json(resp.content if hasattr(resp, "content") else str(resp)))
                    d.setdefault("role", r["role"])
                    return d
                except Exception:  # noqa: BLE001
                    return {"role": r["role"], "opinion": "", "key_points": [], "concerns": []}

            experts = await asyncio.gather(*[one_expert(r) for r in roster])
            experts = [e for e in experts if e.get("opinion")]
            if not experts:
                raise ValueError("전문가 의견 없음")

            # 통합·검증
            opinions = "\n".join(
                f"[{e['role']}] {e.get('opinion','')} (포인트: {', '.join(e.get('key_points') or [])}; "
                f"우려: {', '.join(e.get('concerns') or [])})" for e in experts
            )
            synth_user = _SYNTH_TMPL.format(subject=subject, address=address or "대상지", opinions=opinions)
            llm = get_llm(timeout=70, max_tokens=2000)
            resp = await llm.ainvoke(
                [SystemMessage(content=_SYNTH_SYSTEM + GROUNDING_RULE), HumanMessage(content=synth_user)]
            )
            from app.services.ai.base_interpreter import record_llm_response_billing
            await record_llm_response_billing(llm, resp, service="expert_panel")
            synth = json.loads(_strip_json(resp.content if hasattr(resp, "content") else str(resp)))
            return {
                "generated": True,
                "experts": experts,
                "debate": synth.get("debate", []),
                "consensus": synth.get("consensus", ""),
                "recommended_actions": synth.get("recommended_actions", []),
                "verification": synth.get("verification", {}),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("전문가 패널(deep) 실패, single 폴백", err=str(e)[:100])
            return await self._single(subject, address, ctx, roster)

    @staticmethod
    def _fallback(roster) -> dict[str, Any]:
        return {
            "generated": False,
            "experts": [
                {"role": r["role"], "opinion": "AI 패널 연결 후 상세 의견이 제공됩니다.",
                 "key_points": [], "concerns": []}
                for r in roster
            ],
            "debate": [],
            "consensus": "전문가 패널 분석은 일시적으로 제공되지 않습니다. 잠시 후 다시 시도하세요.",
            "recommended_actions": [],
            "verification": {"confidence": None, "risks": [], "counterpoints": [], "data_gaps": []},
        }
