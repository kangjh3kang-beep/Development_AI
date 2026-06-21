"""프로젝트 단위 데이터 조회 API — 분석 결과를 프로젝트로 집계해 필드별 값 제공(읽기 측).

GET /api/v1/projects/{project_id}/fields: 프로젝트에 귀속된 분석들의 per-field 값(법정산정/판정) 집계.
쓰기 측(analyze가 X-Project-Id를 project_id로 적재)의 대응 조회 — '각 데이터값을 필드별로 제공하는
프로젝트 단위 데이터베이스'의 읽기 경로. 테넌트 격리(#8a)는 store가 보장. 인증: require_token.
project_id는 경로 UUID(형식오류 자동 422). X-Tenant-Id 제공 시 소유 행만(교차테넌트 차단).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, get_tenant_id, require_token
from app.contracts.project_data import ProjectFieldData
from app.services.pipeline.analysis_store import get_project_field_data

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.get("/{project_id}/fields", response_model=ProjectFieldData, dependencies=[Depends(require_token)])
async def get_project_fields(project_id: uuid.UUID, session: AsyncSession = Depends(get_session),
                             tenant_id: uuid.UUID | None = Depends(get_tenant_id)) -> ProjectFieldData:
    # 프로젝트 귀속 per-field 값 집계. 테넌트 격리(#8a): X-Tenant-Id 제공 시 소유 행만(교차테넌트 차단).
    return await get_project_field_data(session, project_id, tenant_id=tenant_id)
