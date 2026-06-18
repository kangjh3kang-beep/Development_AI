"""P2 — 분석 실행 영속화/조회. AnalysisResult ↔ analysis_run(JSONB). run_id = 조회 키."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.analysis import AnalysisResult
from app.db.models.analysis_models import AnalysisRunModel


async def save_analysis(session: AsyncSession, result: AnalysisResult,
                        input_payload: dict | None = None,
                        *, tenant_id: uuid.UUID | None = None) -> AnalysisResult:
    """결과 저장 → run_id 부여한 결과 반환(저장본도 run_id 포함).

    input_payload(원시 입력)는 INC-14 reconcile 불일치 시 동일입력 재실행(결정론)에 사용 — 미전달 시 None
    (재실행 불가로 표면화). 결과 JSON엔 원시 입력이 없어 별도 컬럼에 보존.
    tenant_id(#8a): BFF가 X-Tenant-Id로 전달 시 organization_id로 적재 → get_analysis 소유 필터의 격리 키.
    """
    run_id = uuid.uuid4()
    stored = result.model_copy(update={"run_id": str(run_id)})
    row = AnalysisRunModel(
        id=run_id,
        organization_id=tenant_id,
        snapshot_id=result.snapshot_id,
        input_hash=result.input_hash,
        status="DONE",
        result=stored.model_dump(mode="json"),
        input_payload=input_payload,
    )
    session.add(row)
    await session.commit()
    return stored


async def get_analysis(session: AsyncSession, run_id: str,
                       *, tenant_id: uuid.UUID | None = None) -> AnalysisResult | None:
    """run_id로 조회. tenant_id 제공 시 소유 필터(#8a 심층방어) — 행이 organization_id를 가졌고 불일치면 None
    (교차테넌트 차단). 레거시(organization_id NULL) 행은 후방호환 허용(BFF binding이 1차 소유 게이트)."""
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        return None
    row = await session.get(AnalysisRunModel, uid)
    if row is None or row.result is None:
        return None
    if tenant_id is not None and row.organization_id is not None and row.organization_id != tenant_id:
        return None  # 교차테넌트 조회 차단(엔진측 2차 방어선)
    return AnalysisResult.model_validate(row.result)
