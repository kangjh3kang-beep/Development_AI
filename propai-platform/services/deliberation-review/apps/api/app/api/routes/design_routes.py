"""건축설계 라이프사이클 프로세스 API(시스템2) — 설계 단계 전과정 계측·검증 산출/조회.

POST /api/v1/design/process: 본문 (a) AnalysisInput(+provided 산출물 표시) → 분석 후 설계 프로세스, 또는 (b) {run_id}
재사용(재계산 0) → run_design_process → 영속(process 공용 store, spec_id=design-default) → ProcessResult.
GET /api/v1/design/process/{run_id}, GET /api/v1/projects/{project_id}/design. 인증 require_token, #8a 격리.
"""
from __future__ import annotations

import uuid

import anyio
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_project_id, get_session, get_tenant_id, require_token
from app.contracts.analysis import AnalysisInput
from app.contracts.permit_result import ProcessResult
from app.core.errors import DomainError
from app.services.design.design_executor import run_design_process
from app.services.permit.permit_store import (
    get_permit_process,
    get_project_permit,
    save_permit_process,
)
from app.services.pipeline.analysis_pipeline import run_analysis
from app.services.pipeline.analysis_store import get_analysis

router = APIRouter(prefix="/api/v1", tags=["design"])

_DESIGN_SPEC = "design-default"   # 프로세스 분리 키(store spec_id 필터로 SSOT 적용)


@router.post("/design/process", response_model=ProcessResult, dependencies=[Depends(require_token)])
async def design_process(payload: dict = Body(...), session: AsyncSession = Depends(get_session),
                         tenant_id: uuid.UUID | None = Depends(get_tenant_id),
                         project_id: uuid.UUID | None = Depends(get_project_id)) -> ProcessResult:
    # 본문: (a) {run_id} 재사용 또는 (b) AnalysisInput 신규 실행. provided=설계 산출물 존재(완결성). use_zone/dev_type 컨텍스트.
    use_zone = payload.get("use_zone")
    dev_type = payload.get("dev_type")
    provided = payload.get("provided") if isinstance(payload.get("provided"), dict) else None
    run_id = payload.get("run_id")
    if run_id:
        result = await get_analysis(session, str(run_id), tenant_id=tenant_id)
        if result is None:
            raise HTTPException(status_code=404, detail="analysis run not found")
    else:
        try:
            inp = AnalysisInput(**{k: v for k, v in payload.items()
                                   if k not in ("use_zone", "dev_type", "run_id", "provided")})
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="invalid_input") from exc
        try:
            result = await anyio.to_thread.run_sync(run_analysis, inp)
        except DomainError as exc:
            raise HTTPException(status_code=422, detail=f"domain_error:{type(exc).__name__}") from exc
    out = run_design_process(result, use_zone=use_zone, dev_type=dev_type, provided=provided)
    return await save_permit_process(session, out, tenant_id=tenant_id, project_id=project_id)


@router.get("/design/process/{run_id}", response_model=ProcessResult, dependencies=[Depends(require_token)])
async def get_design_run(run_id: str, session: AsyncSession = Depends(get_session),
                         tenant_id: uuid.UUID | None = Depends(get_tenant_id)) -> ProcessResult:
    out = await get_permit_process(session, run_id, tenant_id=tenant_id, spec_id=_DESIGN_SPEC)
    if out is None:   # 미존재/타테넌트/타프로세스(permit 등) 동일 404(프로세스 분리·존재은닉)
        raise HTTPException(status_code=404, detail="design process run not found")
    return out


@router.get("/projects/{project_id}/design", response_model=list[ProcessResult],
            dependencies=[Depends(require_token)])
async def list_project_design(project_id: uuid.UUID, session: AsyncSession = Depends(get_session),
                              tenant_id: uuid.UUID | None = Depends(get_tenant_id)) -> list[ProcessResult]:
    # 프로젝트의 design 프로세스만 — store spec_id 필터로 SSOT 분리(공용 테이블, 교차 프로세스 누출 차단)
    return await get_project_permit(session, project_id, tenant_id=tenant_id, spec_id=_DESIGN_SPEC)
