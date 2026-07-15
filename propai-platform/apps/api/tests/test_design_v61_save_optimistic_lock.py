"""save_drawing 무낙관잠금 봉합(WP-E R1) — expected_version If-Match 의미론·advisory lock.

배경(design_v61.py:509 실존 레이스): 저장 버전을 MAX(version_number)+1로 계산해, 두 요청이
같은 MAX를 읽으면 같은 버전을 이중 발번하는 lost-update가 났다. 수선:
  ①트랜잭션 advisory lock으로 같은 프로젝트 동시 저장을 직렬화(MAX+1 레이스 원천 차단).
  ②expected_version(If-Match) 제공 시 현재 최신과 불일치하면 409로 거부(무음 덮어쓰기 금지).
  ③미제공(None)이면 기존 동작(MAX+1) 유지 — 점진 도입·하위호환.
  ④(WP-E 세션2 분리 리뷰 MEDIUM) 락 키를 32bit(hashtext)→64bit(hashtextextended)로 상향하되,
    배포 전환창(블루그린 신·구 파드 혼재)의 상호배제 붕괴를 막기 위해 과도기엔 구키를 먼저,
    신키를 다음으로 고정 순서 이중 획득한다(차기 릴리스에서 구키 제거 예정).

라이브 DB 없이 라우터 async 함수를 직접 호출하고, 필요한 SQL만 모사하는 fake DB로 구동한다
(test_design_v61_glb_ownership.py 선례 동형 — '결정적 픽스처만' 원칙).
"""
from __future__ import annotations

import inspect
import uuid

import pytest
from fastapi import HTTPException

from app.routers.design_v61 import CADSaveRequest, save_drawing

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
    """save_drawing이 실행하는 SQL을 내용으로 라우팅하는 fake — 실행 순서를 기록한다."""

    def __init__(self, owner_tenant, max_version):
        self.owner_tenant = owner_tenant
        self.max_version = max_version
        self.executed: list[str] = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(getattr(statement, "text", statement))
        self.executed.append(sql)
        if "FROM projects WHERE id" in sql:
            return _Res((self.owner_tenant,))
        if "MAX(version_number)" in sql:
            return _Res((self.max_version,))
        return _Res(None)  # advisory lock·INSERT 등

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_expected_version_mismatch_returns_409():
    """★If-Match — expected_version이 현재 최신과 다르면 409(무음 덮어쓰기 금지)."""
    db = _SaveFakeDb(owner_tenant=TENANT_A, max_version=5)
    req = CADSaveRequest(expected_version=2)  # 사용자는 v2를 봤는데 서버 최신은 v5
    with pytest.raises(HTTPException) as exc:
        await save_drawing(PROJECT_ID, req, db=db, user=_User(TENANT_A))
    assert exc.value.status_code == 409  # ★500이 아니라 409로 정직 거부
    assert db.commits == 0  # 저장 커밋 0(덮어쓰기 없음)


@pytest.mark.asyncio
async def test_expected_version_match_proceeds_to_save():
    """expected_version이 현재 최신과 같으면 저장을 진행한다(next_ver=MAX+1)."""
    db = _SaveFakeDb(owner_tenant=TENANT_A, max_version=5)
    # 기하 필드는 None으로 두어 bimir 스탬프·design_run 영속을 건너뛴다(버전 로직에만 집중).
    req = CADSaveRequest(expected_version=5)
    res = await save_drawing(PROJECT_ID, req, db=db, user=_User(TENANT_A))
    assert res["status"] == "saved(v6)"  # 5 + 1
    assert db.commits == 1


@pytest.mark.asyncio
async def test_no_expected_version_is_backward_compatible():
    """expected_version 미제공(None)이면 409 없이 기존 MAX+1 동작 유지(하위호환)."""
    db = _SaveFakeDb(owner_tenant=TENANT_A, max_version=5)
    req = CADSaveRequest()  # expected_version 기본 None
    res = await save_drawing(PROJECT_ID, req, db=db, user=_User(TENANT_A))
    assert res["status"] == "saved(v6)"
    assert db.commits == 1


def test_expected_version_field_defaults_to_none():
    """CADSaveRequest.expected_version 기본값은 None(하위호환 — 명시 제공 시에만 If-Match)."""
    assert CADSaveRequest().expected_version is None
    assert CADSaveRequest(expected_version=3).expected_version == 3


@pytest.mark.asyncio
async def test_advisory_lock_precedes_max_version_read():
    """★advisory lock이 MAX(version) 읽기보다 먼저 실행돼 동시 저장을 직렬화한다."""
    db = _SaveFakeDb(owner_tenant=TENANT_A, max_version=0)
    req = CADSaveRequest()
    await save_drawing(PROJECT_ID, req, db=db, user=_User(TENANT_A))
    lock_idx = next(i for i, s in enumerate(db.executed) if "pg_advisory_xact_lock" in s)
    max_idx = next(i for i, s in enumerate(db.executed) if "MAX(version_number)" in s)
    assert lock_idx < max_idx


@pytest.mark.asyncio
async def test_dual_advisory_lock_old_key_before_new_key_both_before_max_version():
    """★분리 리뷰 MEDIUM(전환기 레이스 봉합) — 배포 전환창 동안 신·구 파드가 혼재해도 상호배제가
    깨지지 않도록, 구키(hashtext 32bit)와 신키(hashtextextended 64bit)를 **고정 순서(구키 먼저)**
    로 둘 다 획득한다. 둘 다 MAX(version) 읽기보다 먼저 실행돼야 레이스가 봉합된다."""
    db = _SaveFakeDb(owner_tenant=TENANT_A, max_version=0)
    req = CADSaveRequest()
    await save_drawing(PROJECT_ID, req, db=db, user=_User(TENANT_A))
    lock_stmts = [s for s in db.executed if "pg_advisory_xact_lock" in s]
    assert len(lock_stmts) == 2  # 구키+신키 둘 다 획득(전환기 이중 잠금)
    assert "hashtext(:lk)::bigint" in lock_stmts[0]  # 구키가 먼저(데드락 방지 — 순서 고정)
    assert "hashtextextended(:lk, 0)" in lock_stmts[1]  # 신키가 다음
    old_idx = next(i for i, s in enumerate(db.executed) if "hashtext(:lk)::bigint" in s)
    new_idx = next(i for i, s in enumerate(db.executed) if "hashtextextended(:lk, 0)" in s)
    max_idx = next(i for i, s in enumerate(db.executed) if "MAX(version_number)" in s)
    assert old_idx < new_idx < max_idx  # 구키→신키→MAX 조회 순서 고정


def test_httpexception_handler_precedes_generic_in_source():
    """★409가 generic except로 500 변환되지 않도록 except HTTPException이 먼저 온다(순서 계약)."""
    src = inspect.getsource(save_drawing)
    h_idx = src.index("except HTTPException:")
    g_idx = src.index("except Exception as e:")
    assert h_idx < g_idx  # HTTPException 핸들러가 generic보다 앞
