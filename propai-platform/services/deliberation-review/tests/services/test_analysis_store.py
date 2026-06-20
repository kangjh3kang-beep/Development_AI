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


async def test_tenant_isolation_save_and_get(db):
    # #8a 심층방어 — tenant_id 적재(organization_id) + get 소유 필터(교차테넌트 차단·레거시 허용).
    from sqlalchemy import delete

    from app.db.models.analysis_models import AnalysisRunModel
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    result = run_analysis(AnalysisInput(pnu="1111010100100000004", application_date=date(2026, 1, 1)))
    stored = await save_analysis(db, result, tenant_id=t1)
    row = await db.get(AnalysisRunModel, uuid.UUID(stored.run_id))
    assert row.organization_id == t1                                  # organization_id 적재
    assert await get_analysis(db, stored.run_id, tenant_id=t1) is not None   # 소유 테넌트 조회 가능
    assert await get_analysis(db, stored.run_id, tenant_id=t2) is None       # 교차테넌트 차단
    assert await get_analysis(db, stored.run_id) is not None                 # tenant 미지정(레거시 경로) 허용
    await db.execute(delete(AnalysisRunModel).where(AnalysisRunModel.id == uuid.UUID(stored.run_id)))
    await db.commit()


async def test_legacy_null_org_allows_tenant_get(db):
    # 레거시(organization_id NULL) 행은 tenant_id 제공돼도 허용(후방호환 — BFF binding이 1차 게이트).
    from sqlalchemy import delete

    from app.db.models.analysis_models import AnalysisRunModel
    result = run_analysis(AnalysisInput(pnu="1111010100100000005", application_date=date(2026, 1, 1)))
    stored = await save_analysis(db, result)  # tenant_id 미전달 → organization_id NULL
    assert await get_analysis(db, stored.run_id, tenant_id=uuid.uuid4()) is not None
    await db.execute(delete(AnalysisRunModel).where(AnalysisRunModel.id == uuid.UUID(stored.run_id)))
    await db.commit()


async def test_save_analysis_fans_out_per_field_rows(db):
    # ★per-field 저장 — legal_quantities/findings가 discrete 행으로 영속(analysis_id=run_id), blob과 정합.
    from sqlalchemy import delete, select

    from app.db.models.analysis_models import AnalysisRunModel
    from app.db.models.r1_5_models import LegalQuantityModel
    from app.db.models.r3_models import FindingModel
    inp = AnalysisInput(
        pnu="1111010100100000006", application_date=date(2026, 1, 1),
        rules=[{"rule": {"rule_id": "far_limit", "target_variable": "far_floor_area",
                         "basis_article": "국토계획법 시행령"}, "measured": 250.0, "limit": 200.0}],
        calc_targets=[{"target": "building_area", "payload": {"outer_area": 500.0},
                       "elements": [{"semantic_type": "EXT_WALL", "confidence": 0.9}]}],
    )
    result = run_analysis(inp)
    assert result.findings, "rules → findings 산출 전제"  # fan-out 검증 의미 확보
    tid = uuid.uuid4()
    stored = await save_analysis(db, result, tenant_id=tid)
    rid = uuid.UUID(stored.run_id)
    lq = (await db.execute(select(LegalQuantityModel).where(LegalQuantityModel.analysis_id == rid))).scalars().all()
    fnd = (await db.execute(select(FindingModel).where(FindingModel.analysis_id == rid))).scalars().all()
    # 행 수·식별자 집합이 blob과 일치(순서 무관).
    assert {r.rule_id for r in fnd} == {f.rule_id for f in result.findings}
    assert {r.variable_id for r in lq} == {q.variable_id for q in result.legal_quantities}
    # verdict 등 필드별 값 정합 + analysis_id 귀속 + 테넌트 격리키(blob과 동일) 적재.
    assert {r.rule_id: r.verdict for r in fnd} == {f.rule_id: f.verdict.value for f in result.findings}
    assert all(r.analysis_id == rid and r.organization_id == tid for r in (*lq, *fnd))
    # unit이 enum 문자열값(value)으로 저장(정규화) + calc_trace provenance(INV-10) 보존.
    assert {r.variable_id: r.unit for r in lq} == {q.variable_id: q.unit.value for q in result.legal_quantities}
    assert all(r.calc_trace is not None for r in lq
               if next(q for q in result.legal_quantities if q.variable_id == r.variable_id).calc_trace is not None)
    for tbl in (FindingModel, LegalQuantityModel):
        await db.execute(delete(tbl).where(tbl.analysis_id == rid))
    await db.execute(delete(AnalysisRunModel).where(AnalysisRunModel.id == rid))
    await db.commit()


async def test_save_analysis_attributes_project_id(db):
    # ★project_id 귀속 — run(blob) + per-field 행 모두에 project_id 동일 적재(프로젝트 단위 데이터베이스).
    from sqlalchemy import delete, select

    from app.db.models.analysis_models import AnalysisRunModel
    from app.db.models.r1_5_models import LegalQuantityModel
    from app.db.models.r3_models import FindingModel
    inp = AnalysisInput(
        pnu="1111010100100000007", application_date=date(2026, 1, 1),
        rules=[{"rule": {"rule_id": "far_limit", "target_variable": "far_floor_area",
                         "basis_article": "국토계획법 시행령"}, "measured": 250.0, "limit": 200.0}],
        calc_targets=[{"target": "building_area", "payload": {"outer_area": 500.0},
                       "elements": [{"semantic_type": "EXT_WALL", "confidence": 0.9}]}],
    )
    result = run_analysis(inp)
    tid, pid = uuid.uuid4(), uuid.uuid4()
    stored = await save_analysis(db, result, tenant_id=tid, project_id=pid)
    rid = uuid.UUID(stored.run_id)
    run = await db.get(AnalysisRunModel, rid)
    assert run.project_id == pid and run.organization_id == tid  # blob 행 귀속
    lq = (await db.execute(select(LegalQuantityModel).where(LegalQuantityModel.analysis_id == rid))).scalars().all()
    fnd = (await db.execute(select(FindingModel).where(FindingModel.analysis_id == rid))).scalars().all()
    assert lq and fnd, "fan-out 전제(per-field 행 존재)"
    # per-field 행도 동일 project_id로 귀속(필드별 행을 프로젝트로 집계 가능) + 테넌트 격리키 일관.
    assert all(r.project_id == pid and r.organization_id == tid for r in (*lq, *fnd))
    for tbl in (FindingModel, LegalQuantityModel):
        await db.execute(delete(tbl).where(tbl.analysis_id == rid))
    await db.execute(delete(AnalysisRunModel).where(AnalysisRunModel.id == rid))
    await db.commit()


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
