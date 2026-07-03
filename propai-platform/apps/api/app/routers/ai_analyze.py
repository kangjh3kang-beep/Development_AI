"""범용 AI 호출 프록시 — 서버 공통 LLM 키(.env, key_sanitizer)로 일원화.

프론트가 도메인 프롬프트(system+user)를 구성해 보내면 서버 공통 키로 LLM 호출 후 텍스트 반환.
설계 AI 등 기존 프론트 전용 /api/ai/analyze(localStorage 키)를 대체 → 사용자별 키 등록 불필요.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.auth.auth_service import get_current_user

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


class LLMRequest(BaseModel):
    system: str | None = None
    prompt: str
    max_tokens: int | None = 2000


@router.post("/llm")
async def ai_llm(req: LLMRequest, current_user=Depends(get_current_user)) -> dict:
    """공통 LLM 키로 1회 호출(system+prompt → text)."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.services.ai.llm_provider import get_llm

        llm = get_llm(max_tokens=req.max_tokens or 2000, timeout=60)
        msgs = []
        if req.system:
            msgs.append(SystemMessage(content=req.system))
        msgs.append(HumanMessage(content=req.prompt))
        res = await llm.ainvoke(msgs)
        text = getattr(res, "content", res)
        if isinstance(text, list):  # 일부 프로바이더는 content 블록 리스트 반환
            text = "".join(
                (b.get("text", "") if isinstance(b, dict) else str(b)) for b in text
            )
        return {"text": str(text)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"AI 호출 실패: {str(e)[:200]}")
