"""INC-PD3 — 프로세스 결과 영속/조회: project DB 결속 + 테넌트 격리."""
import uuid
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.services.permit.executor import run_permit_process
from app.services.permit.permit_store import get_permit_process, get_project_permit, save_permit_process
from app.services.permit.spec_loader import load_default_spec
from app.services.pipeline.analysis_pipeline import run_analysis

_IN = AnalysisInput(
    pnu="1111010100100000021", application_date=date(2026, 1, 1),
    rules=[{"rule": {"rule_id": "far_limit", "target_variable": "far_floor_area",
                     "basis_article": "국토계획법 시행령"}, "measured": 250.0, "limit": 200.0}],
)


async def test_save_and_project_scope_with_tenant_isolation(db):
    from sqlalchemy import delete

    from app.db.models.permit_models import PermitProcessRunModel
    res = run_analysis(_IN)
    out = run_permit_process(res, load_default_spec(), use_zone="제2종일반주거지역")
    pid, tid = uuid.uuid4(), uuid.uuid4()
    stored = await save_permit_process(db, out, tenant_id=tid, project_id=pid)
    assert stored.run_id
    # 프로젝트 스코프 조회(소유 테넌트)
    scoped = await get_project_permit(db, pid, tenant_id=tid)
    assert scoped and scoped[0].spec_id == "permit-default"
    # 교차테넌트 차단
    assert await get_project_permit(db, pid, tenant_id=uuid.uuid4()) == []
    # run_id 조회 + 격리
    assert await get_permit_process(db, stored.run_id, tenant_id=tid) is not None
    assert await get_permit_process(db, stored.run_id, tenant_id=uuid.uuid4()) is None
    rid = uuid.UUID(stored.run_id)
    await db.execute(delete(PermitProcessRunModel).where(PermitProcessRunModel.id == rid))
    await db.commit()
