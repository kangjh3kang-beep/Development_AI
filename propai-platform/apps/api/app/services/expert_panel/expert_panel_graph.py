"""전문가 패널 — LangGraph 일원화(다각도·다층 분석 + 원데이터 검증/할루시네이션 게이트).

그래프 흐름:
  experts(병렬 다각도 분석) → verify(원데이터 대조·할루시네이션 적발) → synthesize(검증통과만 통합)

기존 _deep(병렬+통합) 대비 추가:
  ① 전문가 프롬프트를 심층·다층(법규/시장/재무)·다각도(기회 vs 리스크)로 강화.
  ② verify 노드: 각 전문가 주장이 '원본 자료'에 실제 근거가 있는지 LLM이 대조 →
     자료에 없는 수치·사실은 hallucination으로 표시하고 통합에서 배제(근거기반만 채택).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


class PanelState(TypedDict, total=False):
    subject: str
    address: str
    ctx: str
    roster: list
    experts: list            # 전문가 원의견
    verification_report: dict  # 주장별 근거검증 결과
    result: dict


_EXPERT_DEEP_TMPL = """\
## 당신의 역할: {role} ({lens})
## 분석 주제: {subject} — {address}
## 분석 자료(원본)
{context}

## 지시 — 심층·다층·다각도로 분석
- 심층: 표면이 아닌 근본 원인/구조까지 짚는다.
- 다층: 법규·시장·재무·입지 등 관련 층위를 구분해 본다.
- 다각도: 기회 요인과 리스크 요인을 모두 제시한다.
- ★모든 주장에는 위 '원본 자료'의 근거 수치를 함께 적는다. \
자료에 없으면 "근거 없음"으로 명시하고 추정치를 사실처럼 단정하지 않는다.

## 출력 JSON
{{"role": "{role}", "opinion": "핵심 의견(2~3문장)",
  "key_points": ["근거 포함 포인트 1~4개"], "concerns": ["우려·리스크 1~3개"]}}
"""

_EXPERT_SYSTEM = ("당신은 한국 부동산개발 분야의 해당 전문가입니다. 제시된 원본 자료에 근거해서만 "
                  "분석하고, 자료에 없는 수치를 지어내지 않습니다. JSON만 출력.")

_VERIFY_SYSTEM = ("당신은 분석 검증관입니다. 전문가 주장이 제공된 '원본 자료'에 실제 근거가 있는지만 "
                  "냉정하게 대조합니다. 자료에 없는 수치·사실은 hallucination으로 표시. JSON만 출력.")

_VERIFY_TMPL = """\
## 원본 자료
{context}

## 검증 대상(전문가 주장들)
{claims}

## 지시
각 주장이 원본 자료에 근거가 있는지 대조하라. 자료에 없는 수치·단정은 flagged(할루시네이션)로 분류.
## 출력 JSON
{{"verified": [{{"role":"역할","grounded":["원본 근거 있는 주장"],"flagged":["근거 없는(할루시네이션) 주장"]}}],
  "overall_confidence": 0-100 정수(근거기반 비율), "notes": "검증 총평 1~2문장"}}
"""

_SYNTH_SYSTEM = ("당신은 전문가 패널 진행자입니다. ★검증을 통과한(grounded) 의견만 근거로 종합합니다. "
                 "flagged(할루시네이션) 주장은 결론에 쓰지 않습니다. 과장 금지. JSON만 출력.")

_SYNTH_TMPL = """\
## 분석 주제: {subject} — {address}
## 전문가 의견(검증 결과 포함)
{opinions}
## 검증 총평
{verify_notes} (근거기반 신뢰도 {confidence})

## 출력 JSON
{{"debate": [{{"issue":"쟁점","positions":"이견 요약","resolution":"토론 결과"}}],
  "consensus": "검증통과 근거만으로 통합한 최종 결론(3~5문장)",
  "recommended_actions": ["실행 권고 2~4개"],
  "verification": {{"confidence": 0-100 정수, "risks":["1~3개"],
    "counterpoints":["1~3개"], "data_gaps":["0~3개"]}}}}
"""


def _strip_json(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        raw = raw[4:] if raw.lower().startswith("json") else raw
    return raw.strip()


async def _experts_node(state: PanelState) -> dict[str, Any]:
    """병렬 다각도 전문가 분석."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.services.ai.base_interpreter import GROUNDING_RULE
    from app.services.ai.llm_provider import get_llm

    async def one(r: dict) -> dict[str, Any]:
        user = _EXPERT_DEEP_TMPL.format(role=r["role"], lens=r["lens"],
                                        subject=state["subject"], address=state.get("address") or "대상지",
                                        context=state["ctx"])
        llm = get_llm(timeout=60, max_tokens=1000)
        resp = await llm.ainvoke([SystemMessage(content=_EXPERT_SYSTEM + GROUNDING_RULE), HumanMessage(content=user)])
        # 계측: BaseInterpreter 밖 직접 호출도 동일하게 토큰·과금 기록(best-effort)
        from app.services.ai.base_interpreter import record_llm_response_billing
        await record_llm_response_billing(llm, resp, service="expert_panel")
        try:
            d = json.loads(_strip_json(resp.content if hasattr(resp, "content") else str(resp)))
            d.setdefault("role", r["role"])
            return d
        except Exception:  # noqa: BLE001
            return {"role": r["role"], "opinion": "", "key_points": [], "concerns": []}

    experts = await asyncio.gather(*[one(r) for r in state["roster"]])
    return {"experts": [e for e in experts if e.get("opinion")]}


async def _verify_node(state: PanelState) -> dict[str, Any]:
    """원데이터 대조 — 각 주장의 근거 유무 검증(할루시네이션 게이트)."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.services.ai.llm_provider import get_llm

    experts = state.get("experts") or []
    if not experts:
        return {"verification_report": {"verified": [], "overall_confidence": None, "notes": ""}}
    claims = "\n".join(
        f"[{e['role']}] 의견: {e.get('opinion','')} / 포인트: {', '.join(e.get('key_points') or [])}"
        for e in experts
    )
    user = _VERIFY_TMPL.format(context=state["ctx"], claims=claims)
    llm = get_llm(timeout=60, max_tokens=1200)
    try:
        resp = await llm.ainvoke([SystemMessage(content=_VERIFY_SYSTEM), HumanMessage(content=user)])
        from app.services.ai.base_interpreter import record_llm_response_billing
        await record_llm_response_billing(llm, resp, service="expert_panel")
        report = json.loads(_strip_json(resp.content if hasattr(resp, "content") else str(resp)))
    except Exception:  # noqa: BLE001
        report = {"verified": [], "overall_confidence": None, "notes": "검증 일시 불가"}
    return {"verification_report": report}


async def _synth_node(state: PanelState) -> dict[str, Any]:
    """검증통과(grounded) 의견만으로 통합."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.services.ai.base_interpreter import GROUNDING_RULE
    from app.services.ai.llm_provider import get_llm

    experts = state.get("experts") or []
    report = state.get("verification_report") or {}
    vmap = {v.get("role"): v for v in (report.get("verified") or [])}
    # 검증결과를 의견에 주석으로 결합(grounded 우선, flagged 표시).
    lines = []
    for e in experts:
        v = vmap.get(e["role"], {})
        grounded = v.get("grounded") or e.get("key_points") or []
        flagged = v.get("flagged") or []
        lines.append(f"[{e['role']}] {e.get('opinion','')} (검증된 근거: {', '.join(grounded[:3])}"
                     + (f"; ⚠️근거없음: {', '.join(flagged[:2])}" if flagged else "") + ")")
    opinions = "\n".join(lines)
    user = _SYNTH_TMPL.format(subject=state["subject"], address=state.get("address") or "대상지",
                             opinions=opinions, verify_notes=report.get("notes", ""),
                             confidence=report.get("overall_confidence"))
    llm = get_llm(timeout=70, max_tokens=2000)
    synth: dict[str, Any] = {}
    try:
        resp = await llm.ainvoke([SystemMessage(content=_SYNTH_SYSTEM + GROUNDING_RULE), HumanMessage(content=user)])
        from app.services.ai.base_interpreter import record_llm_response_billing
        await record_llm_response_billing(llm, resp, service="expert_panel")
        synth = json.loads(_strip_json(resp.content if hasattr(resp, "content") else str(resp)))
    except Exception:  # noqa: BLE001
        synth = {}
    verification = synth.get("verification", {}) or {}
    if report.get("overall_confidence") is not None:
        verification.setdefault("confidence", report.get("overall_confidence"))
    return {"result": {
        "generated": True,
        "engine": "langgraph",
        "experts": experts,
        "verification_report": report,  # 주장별 근거검증(할루시네이션 적발)
        "debate": synth.get("debate", []),
        "consensus": synth.get("consensus", ""),
        "recommended_actions": synth.get("recommended_actions", []),
        "verification": verification,
    }}


_GRAPH = None


def _build():
    from langgraph.graph import END, StateGraph
    g = StateGraph(PanelState)
    g.add_node("experts", _experts_node)
    g.add_node("verify", _verify_node)
    g.add_node("synthesize", _synth_node)
    g.set_entry_point("experts")
    g.add_edge("experts", "verify")
    g.add_edge("verify", "synthesize")
    g.add_edge("synthesize", END)
    return g.compile()


async def run_panel_graph(subject: str, address: str, ctx: str, roster: list) -> dict[str, Any]:
    """LangGraph 전문가 패널 실행. 실패 시 예외 → 호출처가 폴백."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build()
    final = await _GRAPH.ainvoke({"subject": subject, "address": address, "ctx": ctx, "roster": roster})
    return final.get("result") or {}
