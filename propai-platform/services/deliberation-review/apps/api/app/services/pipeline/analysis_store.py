"""P2 — 분석 실행 영속화/조회. AnalysisResult ↔ analysis_run(JSONB). run_id = 조회 키."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.analysis import AnalysisResult
from app.db.models.analysis_models import AnalysisRunModel


async def save_analysis(session: AsyncSession, result: AnalysisResult,
                        input_payload: dict | None = None) -> AnalysisResult:
    """결과 저장 → run_id 부여한 결과 반환(저장본도 run_id 포함).

    input_payload(원시 입력)는 INC-14 reconcile 불일치 시 동일입력 재실행(결정론)에 사용 — 미전달 시 None
    (재실행 불가로 표면화). 결과 JSON엔 원시 입력이 없어 별도 컬럼에 보존.
    """
    run_id = uuid.uuid4()
    stored = result.model_copy(update={"run_id": str(run_id)})
    row = AnalysisRunModel(
        id=run_id,
        snapshot_id=result.snapshot_id,
        input_hash=result.input_hash,
        status="DONE",
        result=stored.model_dump(mode="json"),
        input_payload=input_payload,
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
