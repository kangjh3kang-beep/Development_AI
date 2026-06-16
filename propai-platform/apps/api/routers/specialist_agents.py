"""Phase 3.2 — 계층3 SpecialistAgent HTTP 노출(W4를 HTTP로).

POST /api/v1/agents/specialist/dispatch — 도메인 SpecialistAgent를 디스패치한다
(prior read + 계층1 결정론 도구 + citation_gate grounded + Phase2 원장 cite).

보안: 인증 필수(get_current_user, HTTPBearer). tenant_id는 **인증 사용자에 고정**(클라이언트
입력 무시 — 교차테넌트 차단). 결정론 코어/수치 불변(라우터는 디스패치 위임만).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from apps.api.auth.jwt_handler import CurrentUser, get_current_user

router = APIRouter()


class SpecialistDispatchRequest(BaseModel):
    domain: str
    data: dict[str, Any] = Field(default_factory=dict)
    project_id: str | None = None
    pnu: str | None = None
    address: str | None = None


@router.post("/dispatch")
async def dispatch_specialist(
    body: SpecialistDispatchRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """도메인 SpecialistAgent 디스패치. 미등록 도메인은 400(정직)."""
    from apps.api.core.coordinator import AgentCoordinator

    tenant_id = getattr(current_user, "tenant_id", None)
    result = await AgentCoordinator().dispatch(
        body.domain, body.data,
        tenant_id=str(tenant_id) if tenant_id is not None else None,
        project_id=body.project_id, pnu=body.pnu, address=body.address,
    )
    if not isinstance(result, dict) or not result.get("ok"):
        detail = (result or {}).get("message", "dispatch failed") if isinstance(result, dict) else "dispatch failed"
        raise HTTPException(status_code=400, detail=detail)
    return result
