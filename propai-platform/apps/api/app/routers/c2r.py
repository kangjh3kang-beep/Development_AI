"""C2R(Coordinate-to-Render) 라우터 — 부지 좌표 기반 렌더 브리프·이미지 렌더.

엔드포인트:
 - POST /api/v1/c2r/brief   : 주소/PNU → 부지 해석·인벨로프·렌더 브리프·Think-Before(렌더 미수행).
 - POST /api/v1/c2r/render  : 브리프 → 이미지 렌더(provider). 키 없으면 200+provider_unconfigured.

게이트: brief 는 인증(get_current_user). render 는 인증+LLM 쿼터(enforce_llm_quota) — 비용 발생
경로라 한도초과 시 402. 단, 키 미설정은 에러가 아니라 정직 상태(provider_unconfigured) 200.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends
from packages.schemas.run_state import RunStateEnum
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.billing_deps import enforce_llm_quota
from app.core.config import settings
from app.core.database import get_db
from app.services.auth.auth_service import get_current_user

logger = structlog.get_logger(__name__)

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
    ★렌더 가드: 검증 안 된 브리프(geometry_hash 없음/불일치)는 ENFORCE 시 렌더 차단,
      기본 shadow(False)면 경고 로그만 남기고 종전대로 렌더(노출빈도 측정 단계·무회귀).
    """
    from app.services.c2r.image_provider import render_image
    from app.services.c2r.render_guard import check_render_allowed

    guard = check_render_allowed(req.brief)
    if not guard["allowed"]:
        if settings.C2R_RENDER_GUARD_ENFORCE:
            # enforce 모드 — render_image 호출하지 않고 정직 차단(200·가짜 이미지 없음).
            #   provider_unconfigured 와 동형(상태·사유만 반환, 이미지 위조 없음).
            return {
                "status": guard["status"],
                "reason": guard["reason"],
                "render_guard": "enforced",
            }
        # shadow 모드(기본) — 차단 사유를 경고로 남기고 종전대로 렌더한다(거동 불변).
        logger.warning(
            "c2r 렌더 가드 shadow 경고(차단하지 않음)",
            guard_status=guard["status"],
            guard_reason=guard["reason"],
        )
        result = await render_image(req.brief, provider=req.provider, settings=req.settings)
        # 응답에 경고 메타만 additive로 덧붙인다(렌더 결과 자체는 무변경).
        if isinstance(result, dict):
            result["render_guard_warning"] = {
                "status": guard["status"],
                "reason": guard["reason"],
            }
        return result

    return await render_image(req.brief, provider=req.provider, settings=req.settings)


@router.post("/ping")
async def c2r_ping(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """C2R 추적 인프라 라이브 헬스 — run_execution 왕복(생성→조회)으로 배선 동작을 증명.

    인증 필요(DB write). 진단용 run(track='__ping__')을 1건 생성·재조회해 추적 3종
    (RunStateEnum · run_execution 테이블 · 멱등키 저장소)이 실제로 동작함을 확인한다.
    무목업: 실 DB 왕복만 한다(가짜 응답 없음). alembic 부팅 미강제 대비 ensure_schema 선행.
    """
    from app.services.c2r.run_store import create_run, ensure_schema, get_run

    await ensure_schema(db)
    # 고정 멱등키 — ping 이 run_execution 을 무한 누적하지 않고 단일 진단 row 를 재사용한다
    # (멱등 경로까지 함께 라이브검증). 최초 1건 생성 후 이후 요청은 같은 row 를 반환.
    run = await create_run(
        db,
        track="__ping__",
        s_phase="S0",
        state=RunStateEnum.DRAFT.value,
        idempotency_key="__c2r_ping__",
    )
    fetched = await get_run(db, run.run_id)
    return {
        "status": "ok",
        "run_id": run.run_id,
        "state": (fetched.state if fetched else None),
        "roundtrip": fetched is not None,
        "tracking": "run_execution",
    }
