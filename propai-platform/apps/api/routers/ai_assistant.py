"""AI 비서(어시스턴트) — 서버(관리자 설정) LLM 키로 대화하는 백엔드 엔드포인트.

프론트의 Next.js `/api/ai/*` 라우트는 A1 nginx가 /api/ 전체를 백엔드로 프록시해 닿지 못한다(404).
그래서 비서는 이 백엔드 엔드포인트(api.4t8t.net/api/v1/ai/*)를 apiClient로 직접 호출한다.
서버 env의 ANTHROPIC/OPENAI 키를 사용하므로 사용자가 별도 키를 넣지 않아도 동작한다.
"""

import json
import logging
import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.rate_limit import ai_limiter, limiter

router = APIRouter()
logger = logging.getLogger(__name__)

# SSOT 컨텍스트 절단 한도(2KB) — 프롬프트 토큰 폭주 방지(클라이언트와 이중 적용).
_CONTEXT_MAX_CHARS = 2048


# ── 도메인별 간단 시스템 프롬프트(화면 컨텍스트 인지) ──
_BASE_PROMPT = (
    "당신은 '사통팔땅' 부동산개발 AI 비서입니다. 한국 부동산개발(부지분석·용도지역·법규·"
    "건축설계·공사비·수지분석·인허가·ESG·분양)에 정통합니다. 데이터에 없는 수치는 지어내지 말고, "
    "모르면 모른다고 답하세요. 답변은 간결한 한국어로, 핵심부터 제시합니다."
)
_DOMAIN_HINTS = {
    "site-analysis": "현재 화면: 부지분석. 용도지역·용적률 상향·법규 리스크 위주로 보조하세요.",
    "feasibility": "현재 화면: 수지분석. 토지비·공사비·분양가·ROI·민감도 위주로 보조하세요.",
    "design": "현재 화면: 건축설계/BIM. 매스·세대믹스·일조·법규 한도 위주로 보조하세요.",
    "auction": "현재 화면: 경공매. 권리분석·예상낙찰가 위주로 보조하세요.",
    "market": "현재 화면: 시장·시세. 실거래·분양가·지역시세 위주로 보조하세요.",
    "regulation": "현재 화면: 규제/인허가. 상위법령·조례·개발방식 위주로 보조하세요.",
}


def _domain(pathname: str) -> str:
    p = pathname or ""
    if "/site-analysis" in p:
        return "site-analysis"
    if "/feasibility" in p or "/investment" in p or "/cost" in p:
        return "feasibility"
    if "/design" in p or "/bim" in p:
        return "design"
    if "/auction" in p:
        return "auction"
    if "/market" in p:
        return "market"
    if "/regulation" in p or "/permits" in p:
        return "regulation"
    return "general"


class ChatMessage(BaseModel):
    role: str
    content: str


class AssistantChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    pathname: str = ""
    # 옵셔널 SSOT 요약(프론트 useProjectContextStore 직렬화) — 미전달 시 기존 동작 불변.
    context: str = ""


def _build_messages(req: AssistantChatRequest) -> tuple[list, bool]:
    """시스템 프롬프트(+도메인 힌트 +SSOT 컨텍스트) + 최근 대화로 LLM 메시지 구성.

    /chat·/chat/stream 공용 — 컨텍스트는 2KB 절단, 미전달 시 프롬프트 불변.
    Returns: (msgs, has_user_message)
    """
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    sys_text = _BASE_PROMPT
    hint = _DOMAIN_HINTS.get(_domain(req.pathname))
    if hint:
        sys_text += "\n" + hint
    ctx = (req.context or "").strip()
    if ctx:
        sys_text += (
            "\n\n[현재 프로젝트 SSOT 요약 — 플랫폼이 보유한 실제 분석값. "
            "아래에 없는 수치는 지어내지 말고 '데이터 없음'으로 답하라]\n"
            + ctx[:_CONTEXT_MAX_CHARS]
        )

    msgs: list = [SystemMessage(content=sys_text)]
    for m in (req.messages or [])[-12:]:  # 최근 12개만(토큰 절약)
        if m.role == "user":
            msgs.append(HumanMessage(content=m.content[:4000]))
        elif m.role == "assistant":
            msgs.append(AIMessage(content=m.content[:4000]))
    has_user = any(isinstance(x, HumanMessage) for x in msgs)
    return msgs, has_user


def _chunk_text(chunk: object) -> str:
    """LangChain 스트림 청크의 텍스트 추출 — content가 str 또는 블록 list(Anthropic) 양쪽 대응."""
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


def _sse(payload: dict) -> str:
    """SSE data 프레임 직렬화(UTF-8 한국어 보존)."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/status")
async def assistant_status():
    """서버(관리자 설정) LLM 키 가용 여부 — 비서 '연결됨' 판정용."""
    available = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"))
    return {"available": available}


@router.post("/chat")
@limiter.limit(ai_limiter)
async def assistant_chat(
    request: Request,
    req: AssistantChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """서버 LLM으로 대화 답변 생성. 키 미설정/실패 시 정직 안내(가짜답변 금지).

    서버 공통 LLM 키를 사용하므로 인증 필수 + AI rate limit(20/min) 적용.
    """
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")):
        return {"ok": False, "reply": "", "error": "no_key",
                "message": "서버 LLM 키가 설정되지 않았습니다. 관리자 키 설정 후 이용 가능합니다."}
    try:
        from app.services.ai.llm_provider import get_llm

        msgs, has_user = _build_messages(req)
        if not has_user:
            return {"ok": True, "reply": "무엇을 도와드릴까요?"}

        llm = get_llm(timeout=30.0, max_tokens=1024)
        resp = await llm.ainvoke(msgs)
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        return {"ok": True, "reply": (text or "").strip() or "(빈 응답)"}
    except Exception as e:  # noqa: BLE001
        logger.warning("AI 비서 LLM 호출 실패: %s", str(e)[:160])
        return {"ok": False, "reply": "", "error": "llm_failed",
                "message": "AI 응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요."}


@router.post("/chat/stream")
@limiter.limit(ai_limiter)
async def assistant_chat_stream(
    request: Request,
    req: AssistantChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """SSE 스트리밍 대화 — 기존 /chat 보존, 델타(`data: {"delta": ...}`) 점증 송출.

    EventSource는 POST 본문·Authorization 헤더를 지원하지 않으므로
    프론트는 fetch 기반 readSseStream(lib/realtime.ts)으로 소비한다.
    키 미설정/LLM 실패 시에도 SSE error 이벤트로 정직 안내(가짜답변 금지).
    """

    async def _events():
        if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")):
            yield _sse({"error": "no_key",
                        "message": "서버 LLM 키가 설정되지 않았습니다. 관리자 키 설정 후 이용 가능합니다."})
            yield _sse({"done": True})
            return
        try:
            from app.services.ai.llm_provider import get_llm

            msgs, has_user = _build_messages(req)
            if not has_user:
                yield _sse({"delta": "무엇을 도와드릴까요?"})
                yield _sse({"done": True})
                return

            llm = get_llm(timeout=60.0, max_tokens=1024)
            emitted = False
            async for chunk in llm.astream(msgs):
                text = _chunk_text(chunk)
                if text:
                    emitted = True
                    yield _sse({"delta": text})
            if not emitted:
                yield _sse({"delta": "(빈 응답)"})
            yield _sse({"done": True})
        except Exception as e:  # noqa: BLE001
            logger.warning("AI 비서 SSE 스트림 실패: %s", str(e)[:160])
            yield _sse({"error": "llm_failed",
                        "message": "AI 응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요."})
            yield _sse({"done": True})

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # A1 nginx가 /api/를 프록시하므로 버퍼링을 꺼야 델타가 실시간 도달한다.
            "X-Accel-Buffering": "no",
        },
    )
