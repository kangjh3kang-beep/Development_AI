"""C2R(Coordinate-to-Render) 라우터 — 부지 좌표 기반 렌더 브리프·이미지 렌더.

엔드포인트:
 - POST /api/v1/c2r/brief   : 주소/PNU → 부지 해석·인벨로프·렌더 브리프·Think-Before(렌더 미수행).
 - POST /api/v1/c2r/render  : 브리프 → 이미지 렌더(provider). 키 없으면 200+provider_unconfigured.

게이트: brief 는 인증(get_current_user). render 는 인증+LLM 쿼터(enforce_llm_quota) — 비용 발생
경로라 한도초과 시 402. 단, 키 미설정은 에러가 아니라 정직 상태(provider_unconfigured) 200.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.billing_deps import enforce_llm_quota
from app.services.auth.auth_service import get_current_user

router = APIRouter(prefix="/c2r", tags=["C2R 렌더"])


class BriefRequest(BaseModel):
    pnu: str | None = Field(None, description="필지 PNU(주소 대신).")
    address: str | None = Field(None, description="분석 대상 주소(PNU 미지정 시).")
    options: dict[str, Any] | None = Field(
        None, description="프로그램 옵션 {building_use, scale, style, materials, ...}."
    )
    use_llm: bool = Field(False, description="브리프 자연어 보강(설계 인터프리터) 포함 여부.")


@router.post("/brief")
async def create_render_brief(req: BriefRequest, current_user=Depends(get_current_user)):
    """부지 좌표 → 구조화 렌더 브리프 + Think-Before 게이팅(이미지 렌더는 미수행).

    렌더는 기본 호출하지 않는다(render.status='pending_provider'). 실제 이미지는 /render 별도.
    """
    from app.services.c2r.c2r_service import build_foundation

    key = (req.pnu or req.address or "").strip()
    if not key:
        return {"error": "pnu 또는 address 가 필요합니다."}
    return await build_foundation(key, req.options, use_llm=req.use_llm)


class RenderRequest(BaseModel):
    brief: dict[str, Any] = Field(..., description="synthesize_brief 산출 구조화 렌더 브리프.")
    provider: str = Field("openai", description="이미지 provider: openai | gemini.")
    settings: dict[str, Any] | None = Field(None, description="provider 옵션(향후 확장).")


@router.post("/render")
async def render_from_brief(
    req: RenderRequest,
    current_user=Depends(get_current_user),
    _quota: None = Depends(enforce_llm_quota),
):
    """렌더 브리프 → 이미지 렌더(provider). 키 미설정은 200+provider_unconfigured(정직).

    ★가짜 이미지 위조 없음: 키 없으면 provider_unconfigured, 호출 실패면 render_error.
    """
    from app.services.c2r.image_provider import render_image

    return await render_image(req.brief, provider=req.provider, settings=req.settings)
