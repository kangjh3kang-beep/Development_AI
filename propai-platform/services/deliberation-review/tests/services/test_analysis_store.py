"""P2 — 분석 영속화/조회 라운드트립(실 DB). save → get 재현, 결손 None."""
import uuid
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.services.pipeline.analysis_pipeline import run_analysis
from app.services.pipeline.analysis_store import get_analysis, save_analysis

_IN = AnalysisInput(pnu="1111010100100000002", application_date=date(2026, 1, 1), drawing={"scale_text": "1:100"})


async def test_save_and_get_round_trip(db):
    result = run_analysis(_IN)
    stored = await save_analysis(db, result)
    assert stored.run_id
    fetched = await get_analysis(db, stored.run_id)
    assert fetched is not None
    assert fetched.run_id == stored.run_id
    assert fetched.input_hash == result.input_hash
    assert fetched.snapshot_id == result.snapshot_id


async def test_get_missing_returns_none(db):
    assert await get_analysis(db, str(uuid.uuid4())) is None
    assert await get_analysis(db, "not-a-uuid") is None


async def test_save_analysis_persists_input_payload(db):
    # INC-14: 원시 입력 보존 — reconcile 불일치 시 동일입력 재실행(결정론)을 위해 analysis_run에 저장.
    from sqlalchemy import delete

    from app.db.models.analysis_models import AnalysisRunModel
    pnu = "1111010100100000003"
    inp = AnalysisInput(pnu=pnu, application_date=date(2026, 1, 1))
    result = run_analysis(inp)
    stored = await save_analysis(db, result, input_payload=inp.model_dump(mode="json"))
    row = await db.get(AnalysisRunModel, uuid.UUID(stored.run_id))
    assert row is not None and row.input_payload is not None
    assert row.input_payload["pnu"] == pnu
    await db.execute(delete(AnalysisRunModel).where(AnalysisRunModel.id == uuid.UUID(stored.run_id)))
    await db.commit()
