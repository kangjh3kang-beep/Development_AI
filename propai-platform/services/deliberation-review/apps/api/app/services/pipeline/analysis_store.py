"""P2 — 분석 실행 영속화/조회. AnalysisResult ↔ analysis_run(JSONB). run_id = 조회 키."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.analysis import AnalysisResult
from app.db.models.analysis_models import AnalysisRunModel


async def save_analysis(session: AsyncSession, result: AnalysisResult) -> AnalysisResult:
    """결과 저장 → run_id 부여한 결과 반환(저장본도 run_id 포함)."""
    run_id = uuid.uuid4()
    stored = result.model_copy(update={"run_id": str(run_id)})
    row = AnalysisRunModel(
        id=run_id,
        snapshot_id=result.snapshot_id,
        input_hash=result.input_hash,
        status="DONE",
        result=stored.model_dump(mode="json"),
    )
    session.add(row)
    await session.commit()
    return stored


async def get_analysis(session: AsyncSession, run_id: str) -> AnalysisResult | None:
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        return None
    row = await session.get(AnalysisRunModel, uid)
    if row is None or row.result is None:
        return None
    return AnalysisResult.model_validate(row.result)
