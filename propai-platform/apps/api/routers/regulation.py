"""법규 검토 라우터."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from packages.schemas.models import RegulationCheckResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.rate_limit import ai_limiter, limiter
from apps.api.services.regulation_service import RegulationService

router = APIRouter()


class RegulationCheckRequest(BaseModel):
    project_id: UUID
    regulation_type: str
    project_info: dict


class RegulationAnalyzeRequest(BaseModel):
    """규제 종합 분석(계층) 요청 — 인증 불필요(부지 공개데이터 기반)."""

    address: str
    pnu: str | None = None
    bcode: str | None = None
    jibun_address: str | None = None
    use_llm: bool = True


@router.post("/analyze", summary="부지 규제 종합 분석(계층 대시보드)")
async def analyze_regulation(body: RegulationAnalyzeRequest) -> dict:
    """부지에 적용되는 상위법령·도시계획·조례·개별규제를 계층으로 정리하고
    정량 한도(건폐/용적/높이/주차)와 AI 통합 해석을 반환한다."""
    import re as _re

    from app.services.regulation.regulation_analysis_service import (
        RegulationAnalysisService,
    )

    pnu = body.pnu
    if not pnu and body.bcode and body.jibun_address:
        m = _re.search(r"(산)?(\d+)(?:-(\d+))?", body.jibun_address or "")
        if m and len(body.bcode) >= 10:
            pnu = (f"{body.bcode}{'2' if m.group(1) else '1'}"
                   f"{m.group(2).zfill(4)}{(m.group(3) or '0').zfill(4)}")
    if not body.address or not body.address.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="주소가 필요합니다.")
    return await RegulationAnalysisService().analyze(
        body.address.strip(), pnu=pnu, use_llm=body.use_llm
    )


@router.post("/check", response_model=RegulationCheckResponse)
@limiter.limit(ai_limiter)
async def check_regulation(
    request: Request,
    body: RegulationCheckRequest,
    current_user: CurrentUser = Depends(RequirePermission("regulation", "write")),
    db: AsyncSession = Depends(get_db),
) -> RegulationCheckResponse:
    """법규 적합성을 검토한다."""
    svc = RegulationService(db)
    return await svc.check_regulation(
        project_id=body.project_id,
        tenant_id=current_user.tenant_id,
        regulation_type=body.regulation_type,
        project_info=body.project_info,
    )
