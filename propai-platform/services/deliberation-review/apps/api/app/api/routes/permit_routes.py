"""인·허가/심의 프로세스 API — 분석 결과를 프로세스 스펙으로 계측·검증해 산출/조회.

POST /api/v1/permit/process: 본문 (a) AnalysisInput → 11페이즈 실행 후 프로세스, 또는 (b) {run_id} → 기존 분석
재사용(재계산 0) → run_permit_process → 영속 → PermitProcessResult.
GET /api/v1/permit/process/{run_id}, GET /api/v1/projects/{project_id}/permit. 인증 require_token, #8a 격리.
"""
from __future__ import annotations

import uuid

import anyio
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_project_id, get_session, get_tenant_id, require_token
from app.contracts.analysis import AnalysisInput
from app.contracts.permit_result import PermitProcessResult
from app.core.errors import DomainError
from app.services.permit.executor import run_permit_process
from app.services.permit.permit_store import (
    get_permit_process,
    get_project_permit,
    save_permit_process,
)
from app.services.permit.spec_loader import load_default_spec
from app.services.pipeline.analysis_pipeline import run_analysis
from app.services.pipeline.analysis_store import get_analysis

router = APIRouter(prefix="/api/v1", tags=["permit"])


@router.post("/permit/process", response_model=PermitProcessResult,
             dependencies=[Depends(require_token)])
async def permit_process(payload: dict = Body(...), session: AsyncSession = Depends(get_session),
                         tenant_id: uuid.UUID | None = Depends(get_tenant_id),
                         project_id: uuid.UUID | None = Depends(get_project_id)) -> PermitProcessResult:
    # 본문: (a) {run_id} 재사용 또는 (b) AnalysisInput 신규 실행. use_zone/dev_type는 프로세스 컨텍스트.
    use_zone = payload.get("use_zone")
    dev_type = payload.get("dev_type")
    run_id = payload.get("run_id")
    if run_id:
        result = await get_analysis(session, str(run_id), tenant_id=tenant_id)
        if result is None:
            raise HTTPException(status_code=404, detail="analysis run not found")
    else:
        try:
            inp = AnalysisInput(**{k: v for k, v in payload.items()
                                   if k not in ("use_zone", "dev_type", "run_id")})
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="invalid_input") from exc
        try:
            result = await anyio.to_thread.run_sync(run_analysis, inp)
        except DomainError as exc:
            raise HTTPException(status_code=422, detail=f"domain_error:{type(exc).__name__}") from exc
    out = run_permit_process(result, load_default_spec(), dev_type=dev_type, use_zone=use_zone)
    return await save_permit_process(session, out, tenant_id=tenant_id, project_id=project_id)


@router.get("/permit/process/{run_id}", response_model=PermitProcessResult,
            dependencies=[Depends(require_token)])
async def get_permit_run(run_id: str, session: AsyncSession = Depends(get_session),
                         tenant_id: uuid.UUID | None = Depends(get_tenant_id)) -> PermitProcessResult:
    out = await get_permit_process(session, run_id, tenant_id=tenant_id)
    if out is None:
        raise HTTPException(status_code=404, detail="permit process run not found")
    return out


@router.get("/projects/{project_id}/permit", response_model=list[PermitProcessResult],
            dependencies=[Depends(require_token)])
async def list_project_permit(project_id: uuid.UUID, session: AsyncSession = Depends(get_session),
                              tenant_id: uuid.UUID | None = Depends(get_tenant_id)
                              ) -> list[PermitProcessResult]:
    return await get_project_permit(session, project_id, tenant_id=tenant_id)
