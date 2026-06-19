"""AI 비서 에이전트 — 도구 호출(tool-use) 루프.

기존 ai_assistant 라우터의 '단발 채팅'을 보강한다. 사용자가 주소/부지 정보를 물으면
비서가 직접 읽기 도구(부지분석·사전진단·토지가)를 호출해 실데이터를 가져와 답한다.

설계(자세히는 docs/AI_ASSISTANT_AGENT_DESIGN.md):
- langgraph 미사용. langchain-anthropic `bind_tools` + 수동 ReAct 루프(버전스큐·의존성 회피).
- 읽기 도구만(무료·비가역 아님) → 자동 실행. 쓰기/과금 도구는 후속(Phase B, 확인게이트).
- 이벤트(delta/tool_start/tool_end)를 yield → 라우터가 기존 SSE {"delta": ...}로 합성(프론트 무변경).
- 도구 결과만 근거로 답하고, 실패 시 정직 고지(무목업 원칙). 모델ID는 get_llm() 한 곳만.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# 도구 호출 최대 라운드 — 분석 비서는 2~3회면 충분. 초과 시 도구 없이 최종 답변 강제.
# 요청당 LLM 호출은 최대 (_MAX_TOOL_ROUNDS + 1)회로 상한(비용·지연 폭주 방지).
_MAX_TOOL_ROUNDS = 3


class AgentUnavailableError(RuntimeError):
    """bind_tools 미지원 등 — 호출부가 단발 채팅으로 폴백하도록 신호."""


# ── 시스템 프롬프트 보강(도구 인지 + 그라운딩) ──
_AGENT_ADDENDUM = (
    "\n\n[도구 사용 지침]\n"
    "- 사용자가 주소·지번을 주거나 부지/용도지역/공시지가/대지면적/사업성/토지가를 물으면, "
    "되묻지 말고 먼저 도구를 호출해 실데이터를 가져와라.\n"
    "- 사실(용적률·건폐율·면적·공시지가·시세·개발방식)은 반드시 도구 결과만 근거로 답하라. "
    "도구로 확인되지 않은 수치는 추정하지 말고 '확인 불가'로 정직히 고지하라.\n"
    "- 용적률은 실효(조례) 기준과 특이부지 판정을 우선 안내하고, 법정상한은 별도로 구분해 제시하라.\n"
    "- 단순 일반 질문(개념 설명 등)은 도구 없이 바로 답하라. 필요한 도구만 호출하라."
)


def _chunk_text(chunk: object) -> str:
    """스트림 청크의 텍스트 추출 — content가 str 또는 블록 list(Anthropic) 양쪽 대응.

    tool_use 블록은 텍스트가 아니므로 자동 제외(도구 JSON이 화면에 새지 않게).
    """
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict) and isinstance(p.get("text"), str):
                parts.append(p["text"])
        return "".join(parts)
    return ""


# ─────────────────────────── 읽기 도구(무료·in-process) ───────────────────────────

@tool
async def analyze_site(address: str) -> str:
    """주소(또는 지번)의 용도지역·대지면적·공시지가·지목·특이부지 등 부지 기본정보를 조회한다. 읽기 전용."""
    from app.services.zoning.auto_zoning_service import AutoZoningService

    try:
        r = await AutoZoningService().analyze_by_address(address)
    except Exception as e:  # noqa: BLE001
        return f"부지 조회 실패: {str(e)[:120]}. 이 정보 없이 정직하게 '확인 불가'로 답하라."
    if not isinstance(r, dict):
        return "부지 조회 결과가 없습니다(데이터 없음)."

    # zone_source가 주소 키워드 추론이면 실조회값이 아님 → 머리에 명시 경고(할루시네이션 가드).
    inferred = r.get("zone_source") == "keyword_inference"
    lines: list[str] = []
    if inferred:
        lines.append("[주의] 아래 용도지역은 주소 키워드 추론값이며 실조회(공부 확인)가 아닙니다. "
                     "권위있는 사실로 단정하지 말고 사용자에게 실데이터 확인을 안내하라.")
    lines.append(f"주소: {r.get('address') or address}")
    if r.get("pnu"):
        lines.append(f"PNU: {r['pnu']}")
    if r.get("zone_type"):
        tag = "추론값·미확인" if inferred else (r.get("zone_source") or "미상")
        lines.append(f"용도지역: {r['zone_type']} (출처: {tag})")
    if r.get("zone_limits"):
        lines.append(f"법정 한도(참고): {r['zone_limits']}")
    if r.get("land_area_sqm") is not None:
        lines.append(f"대지면적: {r['land_area_sqm']}㎡")
    if r.get("land_category"):
        lines.append(f"지목: {r['land_category']}")
    if r.get("official_price_per_sqm") is not None:
        try:
            lines.append(f"공시지가: {int(r['official_price_per_sqm']):,}원/㎡")
        except (TypeError, ValueError):
            lines.append(f"공시지가: {r['official_price_per_sqm']}원/㎡")
    if r.get("special_districts"):
        lines.append(f"특이/지구: {', '.join(str(x) for x in r['special_districts'])}")
    if r.get("warnings"):
        lines.append(f"주의: {'; '.join(str(x) for x in r['warnings'])}")

    # 실데이터 유무 판정 — 경고/주소 라인만 있고 실제 부지 정보가 없으면 '데이터 없음'.
    has_data = any([
        r.get("zone_type"), r.get("zone_limits"), r.get("land_area_sqm") is not None,
        r.get("land_category"), r.get("official_price_per_sqm") is not None,
        r.get("special_districts"),
    ])
    if not has_data:
        return f"'{address}'의 부지 정보를 확인하지 못했습니다(데이터 없음). 정직하게 고지하라."
    lines.append("[안내] 용적률은 조례 실효기준+특이부지 판정을 우선하고, 법정상한은 별도로 구분해 설명하라.")
    return "\n".join(lines)


@tool
async def feasibility_precheck(address: str, area_sqm: float | None = None) -> str:
    """주소 기반 90초 사업성·개발방식 사전진단(읽기 전용). 개발 가능성·추천 방식을 물으면 호출한다."""
    from app.services.precheck.precheck_service import run_instant_precheck

    try:
        r = await run_instant_precheck(address, area_sqm=area_sqm, use_llm=False)
    except Exception as e:  # noqa: BLE001
        return f"사전진단 실패: {str(e)[:120]}. 데이터 없이 정직히 고지하라."
    if not isinstance(r, dict):
        return "사전진단 결과가 없습니다(데이터 없음)."
    if not r.get("ok"):
        return f"사전진단 불가: {r.get('message') or '필지를 확인하지 못했습니다.'}"

    lines: list[str] = []
    if r.get("zone_type"):
        lines.append(f"용도지역: {r['zone_type']}")
    if r.get("area_sqm") is not None:
        lines.append(f"대지면적: {r['area_sqm']}㎡")
    if r.get("legal_limits"):
        lines.append(f"법정 한도: {r['legal_limits']}")
    summary = r.get("summary") or {}
    if summary.get("best"):
        lines.append(f"추천 개발방식: {summary['best']}")
    if summary.get("developability"):
        lines.append(f"개발가능성: {summary['developability']}")
    if summary.get("special_parcel_warning"):
        lines.append(f"특이부지 고지: {summary['special_parcel_warning']}")
    methods = r.get("methods") or []
    if isinstance(methods, list) and methods:
        sig = ", ".join(
            f"{m.get('name') or m.get('code')}={m.get('signal')}"
            for m in methods[:6]
            if isinstance(m, dict)
        )
        if sig:
            lines.append(f"방식별 신호: {sig}")
    return "\n".join(lines) if lines else "사전진단 결과가 비어 있습니다(데이터 없음)."


@tool
async def estimate_land_price(address: str, area_sqm: float | None = None) -> str:
    """주소의 적정 토지 매입가/시세를 추정한다(읽기 전용). 토지가격·매입가·시세를 물으면 호출한다."""
    from app.services.land_intelligence.land_price_estimator import (
        estimate_land_price as _estimate,
    )

    try:
        r = await _estimate(address=address, area_sqm=area_sqm)
    except Exception as e:  # noqa: BLE001
        return f"토지가 추정 실패: {str(e)[:120]}. 데이터 없이 정직히 고지하라."
    if not isinstance(r, dict):
        return "토지가 추정 결과가 없습니다(데이터 없음)."
    if not r.get("ok"):
        return f"토지가 추정 불가: {r.get('message') or '공시지가를 확인하지 못했습니다.'}"

    lines: list[str] = []
    if r.get("official_price_per_sqm") is not None:
        lines.append(f"개별공시지가: {int(r['official_price_per_sqm']):,}원/㎡")
    if r.get("estimated_price_per_sqm") is not None:
        lines.append(f"추정 단가: {int(r['estimated_price_per_sqm']):,}원/㎡")
    if r.get("estimated_total_won") is not None:
        lines.append(f"추정 매입가(총액): {int(r['estimated_total_won']):,}원")
    if r.get("rationale"):
        lines.append(f"근거: {r['rationale']}")
    trust = r.get("trust") or {}
    if trust.get("note"):
        lines.append(f"신뢰 한계: {trust['note']}")
    return "\n".join(lines) if lines else "토지가 추정 결과가 비어 있습니다(데이터 없음)."


# 질의당 노출 도구는 소수로 유지(과다 도구는 오선택·토큰폭증 유발).
_READ_TOOLS = [analyze_site, feasibility_precheck, estimate_land_price]
_TOOLS_BY_NAME = {t.name: t for t in _READ_TOOLS}
_TOOL_LABELS = {
    "analyze_site": "부지 분석",
    "feasibility_precheck": "사업성 사전진단",
    "estimate_land_price": "토지가 추정",
}


def _augment_system(msgs: list) -> list:
    """첫 SystemMessage에 도구 사용 지침을 덧붙인다(원본 불변 — 새 메시지로 교체)."""
    out = list(msgs)
    for i, m in enumerate(out):
        if isinstance(m, SystemMessage):
            base = m.content if isinstance(m.content, str) else str(m.content)
            out[i] = SystemMessage(content=base + _AGENT_ADDENDUM)
            return out
    out.insert(0, SystemMessage(content=_AGENT_ADDENDUM.strip()))
    return out


async def _meter(base_llm: object, response: object, service: str) -> None:
    """LLM 라운드 토큰 계측(단일경유, best-effort). 실패는 무시(본기능 무회귀)."""
    try:
        from app.services.ai.base_interpreter import record_llm_response_billing

        await record_llm_response_billing(base_llm, response, service=service)
    except Exception:  # noqa: BLE001
        pass


async def _run_tool(tool_call: dict) -> str:
    """도구 1건 실행 — 실패해도 모델이 읽을 안내문 반환(자가복구·정직)."""
    name = tool_call.get("name", "")
    args = tool_call.get("args") or {}
    # 일부 모델/버전이 args를 JSON 문자열로 줄 수 있음 — dict로 정규화(정상 호출 격하 방지).
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (ValueError, TypeError):
            args = {}
    t = _TOOLS_BY_NAME.get(name)
    if t is None:
        return f"알 수 없는 도구: {name}. 도구 없이 답하라."
    try:
        result = await t.ainvoke(args)
        return result if isinstance(result, str) else str(result)
    except Exception as e:  # noqa: BLE001
        logger.warning("AI 비서 도구 실행 오류 (%s): %s", name, str(e)[:160])
        return f"도구({name}) 실행 오류: {str(e)[:120]}. 이 데이터 없이 정직히 고지하라."


async def run_agent_events(msgs: list, *, service: str = "ai_assistant") -> AsyncIterator[dict]:
    """도구 호출 ReAct 루프. 이벤트 dict를 yield.

    이벤트: {"type": "delta", "text": str} | {"type": "tool_start"/"tool_end", "label": str}
    bind_tools 미지원이면 AgentUnavailableError 발생(호출부가 단발 채팅으로 폴백).

    각 라운드는 ainvoke로 수행한다(astream 아님): ① 토큰 usage_metadata가 모든
    langchain-anthropic 버전에서 확실히 채워져 계측이 누락되지 않고(stream_usage 의존 제거),
    ② 도구 호출(tool_calls)이 버전 무관하게 파싱돼 prod에서 조용히 무효화되지 않는다.
    대신 최종 답변은 토큰 단위 스트리밍이 아니라 완성 후 1회 델타로 송출된다(도구 진행은 실시간).
    """
    from app.services.ai.llm_provider import get_llm

    base_llm = get_llm(timeout=60.0, max_tokens=1024)
    if not hasattr(base_llm, "bind_tools"):
        raise AgentUnavailableError("LLM이 bind_tools를 지원하지 않습니다.")

    convo = _augment_system(msgs)
    llm_with_tools = base_llm.bind_tools(_READ_TOOLS)

    for _round in range(_MAX_TOOL_ROUNDS):
        resp = await llm_with_tools.ainvoke(convo)
        await _meter(base_llm, resp, service)

        tool_calls = list(getattr(resp, "tool_calls", None) or [])
        if not tool_calls:
            text = _chunk_text(resp)
            if text:
                yield {"type": "delta", "text": text}
            return  # 도구 호출 없음 = 최종 답변 완료

        convo.append(resp)
        for tc in tool_calls:
            label = _TOOL_LABELS.get(tc.get("name", ""), tc.get("name", "도구"))
            yield {"type": "tool_start", "label": label}
            result = await _run_tool(tc)
            convo.append(ToolMessage(content=result, tool_call_id=tc.get("id", "")))
            yield {"type": "tool_end", "label": label}

    # 라운드 상한 도달 — 도구 없이 1회 최종 답변 강제(무한 도구호출·비용 폭주 방지)
    resp = await base_llm.ainvoke(convo)
    await _meter(base_llm, resp, service)
    text = _chunk_text(resp)
    if text:
        yield {"type": "delta", "text": text}


async def run_agent_collect(msgs: list, *, service: str = "ai_assistant") -> str:
    """비스트리밍(/chat)용 — 에이전트를 끝까지 돌려 최종 텍스트만 모아 반환.

    에이전트 미가용(AgentUnavailableError)은 그대로 전파해 호출부가 단발로 폴백한다.
    그 외 예외는 누적 텍스트가 있으면 부분 결과를 반환(도구 라운드 토큰 이중과금 방지),
    한 글자도 못 냈으면 전파해 단발 폴백을 허용한다.
    """
    parts: list[str] = []
    try:
        async for ev in run_agent_events(msgs, service=service):
            if ev.get("type") == "delta":
                parts.append(ev["text"])
    except AgentUnavailableError:
        raise
    except Exception:  # noqa: BLE001
        if not parts:
            raise
        logger.warning("AI 비서 에이전트 부분 완료(예외 후 누적분 반환)")
    return "".join(parts).strip()
