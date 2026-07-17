"""save_drawing → design_run 표면화(후속④) — /drawings/save 응답이 persist_design_run의
실키(run_id)·승인차원 status를 additive로 동봉하는지 검증한다.

배경(직전 조사 확정 차단): design-runs 승인 API(POST /api/v1/design-runs/{run_id}/approve)는
완결됐지만, 프론트가 'dr_' run_id를 얻을 경로가 없어 승인 흐름을 표면화할 수 없었다. 해제 레시피는
persist_design_run 반환 dict(design_run_store.py:318-324 — run_id·status)의 실키를 저장 응답에
additive 1필드(design_run={run_id, status})로 동봉하는 것. 이 테스트가 그 계약을 고정한다.

무회귀 계약: 기존 응답 필드(project_id·status·layer_count 등)는 무변경. design_run은 신규 optional
필드라 매스치수 부재(미영속) 시 None(정직). DrawingSaveResponse 모델이 이 값을 그대로 통과시킨다.

라이브 DB 없이 라우터 async 함수를 직접 호출하고 필요한 SQL만 모사하는 fake DB로 구동한다
(test_design_v61_save_optimistic_lock.py 선례 동형 — '결정적 픽스처만' 원칙).
"""
from __future__ import annotations

import uuid

import pytest

from app.routers.design_v61 import CADSaveRequest, DrawingSaveResponse, save_drawing

TENANT_A = str(uuid.uuid4())
PROJECT_ID = str(uuid.uuid4())


class _User:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


class _Res:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _SaveFakeDb:
    """save_drawing + persist_design_run이 실행하는 SQL을 내용으로 라우팅하는 fake.

    - projects 소유권 조회 → owner_tenant
    - MAX(version_number) → max_version
    - design_runs status 재조회(persist 내부) → None(신규 행 → 반환 status는 DRAFT 기본)
    - 그 외(advisory lock·INSERT·DDL·commit) → no-op
    """

    def __init__(self, owner_tenant, max_version=0):
        self.owner_tenant = owner_tenant
        self.max_version = max_version
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(getattr(statement, "text", statement))
        if "FROM projects WHERE id" in sql:
            return _Res((self.owner_tenant,))
        if "MAX(version_number)" in sql:
            return _Res((self.max_version,))
        # design_runs status 재조회 등은 행 없음 → persist 반환 status는 DRAFT 기본 유지.
        return _Res(None)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _mass_req() -> CADSaveRequest:
    """완전한 매스치수(폭·깊이·층수)를 실은 저장 요청 — persist_design_run 트리거 조건 충족."""
    return CADSaveRequest(
        building_width_m=12.0,
        building_depth_m=9.0,
        floor_count=5,
        building_height_m=15.0,
        floor_height_m=3.0,
    )


@pytest.mark.asyncio
async def test_save_surfaces_design_run_real_run_id_and_status():
    """★핵심: 완전한 매스치수가 있으면 응답 design_run에 실키(run_id='dr_…')·status(DRAFT)가 실린다."""
    db = _SaveFakeDb(owner_tenant=TENANT_A, max_version=0)
    res = await save_drawing(PROJECT_ID, _mass_req(), db=db, user=_User(TENANT_A))

    assert res["status"] == "saved(v1)"  # 기존 필드 무변경(하위호환)
    dr = res["design_run"]
    assert isinstance(dr, dict)
    assert isinstance(dr["run_id"], str) and dr["run_id"].startswith("dr_")  # 실키(스코프된 run_id)
    assert dr["status"] == "DRAFT"  # persist는 항상 DRAFT로 시작(자동경로는 APPROVED를 만들지 않음)


@pytest.mark.asyncio
async def test_save_without_mass_dims_returns_null_design_run():
    """매스치수 부재(미영속) 시 design_run은 None(정직) — stale 승인 UI 노출 방지."""
    db = _SaveFakeDb(owner_tenant=TENANT_A, max_version=0)
    req = CADSaveRequest()  # 기하 필드 전부 None → persist 건너뜀
    res = await save_drawing(PROJECT_ID, req, db=db, user=_User(TENANT_A))
    assert res["status"] == "saved(v1)"
    assert res["design_run"] is None


@pytest.mark.asyncio
async def test_response_validates_against_drawing_save_response_model():
    """★additive 안전: 저장 응답 dict가 DrawingSaveResponse(신규 optional design_run)로 통과한다.

    response_model이 undeclared 키를 버리지 않고 design_run을 그대로 노출하는지 고정한다.
    """
    db = _SaveFakeDb(owner_tenant=TENANT_A, max_version=0)
    res = await save_drawing(PROJECT_ID, _mass_req(), db=db, user=_User(TENANT_A))
    model = DrawingSaveResponse(**res)  # 검증 실패 없이 통과해야 한다
    assert model.design_run is not None
    assert model.design_run["run_id"].startswith("dr_")


def test_drawing_save_response_declares_optional_design_run():
    """DrawingSaveResponse.design_run 기본값은 None(하위호환 — echo/미영속 응답도 유효)."""
    m = DrawingSaveResponse(
        project_id=PROJECT_ID, drawing_code="CAD-EDIT", drawing_type="평면도",
        svg_length=0, layer_count=0, status="echo",
    )
    assert m.design_run is None
