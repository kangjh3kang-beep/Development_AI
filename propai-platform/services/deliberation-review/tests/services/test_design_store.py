"""INC-DL3 — 프로세스 분리 SSOT(store spec_id): design/permit 공용 테이블에서 양방향 교차누출 차단·테넌트 격리."""
import uuid
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.services.design.design_executor import run_design_process
from app.services.permit.executor import run_process
from app.services.permit.permit_store import get_permit_process, get_project_permit, save_permit_process
from app.services.permit.spec_loader import load_default_spec
from app.services.pipeline.analysis_pipeline import run_analysis

_IN = AnalysisInput(pnu="1111010100100000032", application_date=date(2026, 1, 1))


async def test_process_separation_by_spec_id_both_directions(db):
    from sqlalchemy import delete

    from app.db.models.permit_models import PermitProcessRunModel
    res = run_analysis(_IN)
    pid, tid = uuid.uuid4(), uuid.uuid4()
    permit_out = run_process(res, load_default_spec(), use_zone="제2종일반주거지역")
    design_out = run_design_process(res, use_zone="제2종일반주거지역", provided={"program": True})
    s_p = await save_permit_process(db, permit_out, tenant_id=tid, project_id=pid)
    s_d = await save_permit_process(db, design_out, tenant_id=tid, project_id=pid)

    # 목록: spec_id 필터로 각 프로세스만(공용 테이블 공존하나 분리)
    designs = await get_project_permit(db, pid, tenant_id=tid, spec_id="design-default")
    permits = await get_project_permit(db, pid, tenant_id=tid, spec_id="permit-default")
    assert [r.spec_id for r in designs] == ["design-default"] and designs[0].run_id == s_d.run_id
    assert [r.spec_id for r in permits] == ["permit-default"] and permits[0].run_id == s_p.run_id
    # 필터 없으면 둘 다(공용 테이블)
    assert {r.spec_id for r in await get_project_permit(db, pid, tenant_id=tid)} == {"design-default", "permit-default"}

    # 단일 run: 교차 프로세스 조회는 None(누출 차단·양방향)
    assert await get_permit_process(db, s_d.run_id, tenant_id=tid, spec_id="design-default") is not None
    assert await get_permit_process(db, s_d.run_id, tenant_id=tid, spec_id="permit-default") is None  # design→permit 차단
    assert await get_permit_process(db, s_p.run_id, tenant_id=tid, spec_id="permit-default") is not None
    assert await get_permit_process(db, s_p.run_id, tenant_id=tid, spec_id="design-default") is None  # permit→design 차단
    # 교차테넌트 차단(spec 일치해도)
    assert await get_permit_process(db, s_d.run_id, tenant_id=uuid.uuid4(), spec_id="design-default") is None

    for s in (s_p, s_d):
        await db.execute(delete(PermitProcessRunModel).where(PermitProcessRunModel.id == uuid.UUID(s.run_id)))
    await db.commit()
