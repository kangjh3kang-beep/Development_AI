"""INC-PD3 — 프로세스 결과 영속/조회(permit·design 공용 process 저장). blob(재현) + 프로젝트 DB 결속(project_id·org).

테넌트 격리(#8a) + ★프로세스 분리(spec_id): 조회 시 spec_id 지정하면 해당 프로세스(permit-default/design-default)만
반환 — 공용 테이블에서 시스템1/시스템2 산출 교차누출을 store 계층에서 SSOT로 차단(라우트별 필터 누락 위험 제거).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.permit_result import PermitProcessResult
from app.db.models.permit_models import PermitProcessRunModel

_MAX_PROJECT_ROWS = 1000   # 운영 상수(거대 응답 방어) — 법정 파라미터 아님(INV-3 무관)


async def save_permit_process(session: AsyncSession, out: PermitProcessResult, *,
                              tenant_id: uuid.UUID | None = None,
                              project_id: uuid.UUID | None = None) -> PermitProcessResult:
    """결과 저장 → run_id 부여 반환. organization_id/project_id 결속(프로젝트 DB·격리)."""
    run_id = uuid.uuid4()
    stored = out.model_copy(update={"run_id": str(run_id)})
    session.add(PermitProcessRunModel(
        id=run_id, organization_id=tenant_id, project_id=project_id,
        spec_id=out.spec_id, spec_version=out.spec_version, analysis_run_id=out.run_id,
        overall_conformance=out.overall_conformance, overall_verification=out.overall_verification,
        result=stored.model_dump(mode="json"),
    ))
    await session.commit()
    return stored


async def get_project_permit(session: AsyncSession, project_id: uuid.UUID, *,
                             tenant_id: uuid.UUID | None = None, spec_id: str | None = None,
                             max_rows: int = _MAX_PROJECT_ROWS) -> list[PermitProcessResult]:
    """프로젝트 귀속 프로세스 결과 목록(테넌트 격리 + spec_id 프로세스 분리). 결정론 정렬(created_at,id)."""
    stmt = select(PermitProcessRunModel).where(PermitProcessRunModel.project_id == project_id)
    if tenant_id is not None:
        stmt = stmt.where(PermitProcessRunModel.organization_id == tenant_id)
    if spec_id is not None:
        stmt = stmt.where(PermitProcessRunModel.spec_id == spec_id)   # 프로세스 분리(교차누출 차단)
    stmt = stmt.order_by(PermitProcessRunModel.created_at, PermitProcessRunModel.id).limit(max_rows)
    rows = (await session.execute(stmt)).scalars().all()
    return [PermitProcessResult.model_validate(r.result) for r in rows]


async def get_permit_process(session: AsyncSession, run_id: str, *,
                             tenant_id: uuid.UUID | None = None,
                             spec_id: str | None = None) -> PermitProcessResult | None:
    """run_id 조회 + 테넌트 격리(교차테넌트 차단·레거시 NULL 허용) + spec_id 프로세스 분리(불일치 시 None)."""
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        return None
    row = await session.get(PermitProcessRunModel, uid)
    if row is None:
        return None
    if tenant_id is not None and row.organization_id is not None and row.organization_id != tenant_id:
        return None
    if spec_id is not None and row.spec_id != spec_id:
        return None   # 교차 프로세스 누출 차단(예: permit 엔드포인트로 design run 조회→None)
    return PermitProcessResult.model_validate(row.result)
