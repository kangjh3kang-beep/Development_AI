"""WP-L 게이트 — job 상태머신(QUEUED/RUNNING/SUCCEEDED/CANCELLED/FAILED)·취소·차원 독립성.

핵심 게이트(계획서 §4 WP-L):
- 취소 상태머신 전이: 불법 전이 409·터미널 재취소 409.
- job상태(실행차원) ↔ 승인상태(승인차원)의 완전 독립(별도 컬럼·서로 무접촉).

라이브 DB 없이, design_run_store/design_run_job이 작성한 design_runs SQL을 충실히 모사하는
인메모리 fake로 구동한다(WP-E 테스트 동형). persist로 run을 씨앗한 뒤 두 축을 각각 전이시켜
'혼용 금지'가 모듈 경계로 지켜지는지 확인한다.
"""
from __future__ import annotations

import inspect
import json

import pytest

from app.services.cad import design_run_job as job
from app.services.cad import design_run_store as store


# ══════════════════════════════════════════════════════════════════════════
# 1) 순수 규칙 — 정규화·터미널·전이·취소(DB 불요)
# ══════════════════════════════════════════════════════════════════════════
def test_is_terminal():
    assert job.is_terminal("SUCCEEDED") is True
    assert job.is_terminal("CANCELLED") is True
    assert job.is_terminal("FAILED") is True
    assert job.is_terminal("QUEUED") is False
    assert job.is_terminal("RUNNING") is False
    assert job.is_terminal(None) is False


def test_can_transition_legal_paths():
    assert job.can_transition(None, "QUEUED")[0] is True
    assert job.can_transition(None, "RUNNING")[0] is True
    assert job.can_transition("QUEUED", "RUNNING")[0] is True
    assert job.can_transition("RUNNING", "SUCCEEDED")[0] is True
    assert job.can_transition("RUNNING", "FAILED")[0] is True
    assert job.can_transition("QUEUED", "CANCELLED")[0] is True


def test_can_transition_illegal_paths():
    # 규모 건너뛰기(QUEUED→SUCCEEDED) 금지.
    assert job.can_transition("QUEUED", "SUCCEEDED")[0] is False
    # 터미널에서의 전이 금지.
    assert job.can_transition("SUCCEEDED", "RUNNING")[0] is False
    assert job.can_transition("CANCELLED", "QUEUED")[0] is False
    assert job.can_transition("FAILED", "RUNNING")[0] is False
    # 유효하지 않은 목표.
    assert job.can_transition("QUEUED", "BOGUS")[0] is False


def test_can_cancel_matrix():
    assert job.can_cancel(None)[0] is True
    assert job.can_cancel("QUEUED")[0] is True
    assert job.can_cancel("RUNNING")[0] is True
    assert job.can_cancel("SUCCEEDED")[0] is False   # 터미널 → 409
    assert job.can_cancel("CANCELLED")[0] is False   # 재취소 → 409
    assert job.can_cancel("FAILED")[0] is False


def test_normalize_job_status():
    assert job.normalize_job_status(None) is None
    assert job.normalize_job_status("") is None
    assert job.normalize_job_status(" running ") == "RUNNING"


# ══════════════════════════════════════════════════════════════════════════
# 2) 인메모리 fake DB — persist 씨앗 + 두 축 전이(차원 독립성)
# ══════════════════════════════════════════════════════════════════════════
def _tenant_match(row_tenant, query_tenant) -> bool:
    return row_tenant == query_tenant


class _Res:
    def __init__(self, row=None, rowcount=0):
        self._row = row
        self.rowcount = rowcount

    def first(self):
        return self._row


class _FakeDesignRunsDb:
    """design_runs SQL(store 승인차원 + job 실행차원)을 모두 모사하는 인메모리 fake."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(getattr(statement, "text", statement))
        s = sql.strip()
        p = params or {}
        if "CREATE TABLE" in sql or "CREATE INDEX" in sql or "ALTER TABLE" in sql:
            return _Res()
        if s.startswith("INSERT INTO design_runs"):
            rid = p["rid"]
            new_surface = json.loads(p["sh"])
            if rid in self.rows:
                r = self.rows[rid]
                r["compiler_version"] = p["cv"]; r["input_hash"] = p["ih"]
                r["geometry_hash"] = p["gh"]; r["metrics"] = json.loads(p["mj"])
                merged = dict(r.get("surface_hashes") or {}); merged.update(new_surface)
                r["surface_hashes"] = merged
            else:
                self.rows[rid] = {
                    "run_id": rid, "tenant_id": p["tid"], "project_id": p["pid"],
                    "seed": p["seed"], "compiler_version": p["cv"], "input_hash": p["ih"],
                    "surface_hashes": new_surface, "geometry_hash": p["gh"],
                    "metrics": json.loads(p["mj"]), "status": "DRAFT", "approved_by": None,
                    "job_status": None,  # 실행차원 초기값(미시작)
                }
            return _Res()
        if s.startswith("SELECT status FROM design_runs"):
            r = self.rows.get(p["rid"])
            if r is None or not _tenant_match(r["tenant_id"], p.get("tid")):
                return _Res(None)
            return _Res((r["status"],))
        if s.startswith("SELECT job_status FROM design_runs"):
            r = self.rows.get(p["rid"])
            if r is None or not _tenant_match(r["tenant_id"], p.get("tid")):
                return _Res(None)
            return _Res((r["job_status"],))
        if "SELECT run_id, tenant_id, project_id" in sql:
            r = self.rows.get(p["rid"])
            if r is None or not _tenant_match(r["tenant_id"], p.get("tid")):
                return _Res(None)
            return _Res((r["run_id"], r["tenant_id"], r["project_id"], r["seed"],
                         r["compiler_version"], r["input_hash"], r["surface_hashes"],
                         r["geometry_hash"], r["metrics"], r["status"], r["approved_by"]))
        if s.startswith("UPDATE design_runs SET status = 'APPROVED'"):
            r = self.rows.get(p["rid"])
            if r is not None:
                r["status"] = "APPROVED"; r["approved_by"] = p["by"]
            return _Res(rowcount=1 if r else 0)
        if s.startswith("UPDATE design_runs SET job_status"):
            r = self.rows.get(p["rid"])
            if r is None or not _tenant_match(r["tenant_id"], p.get("tid")):
                return _Res(rowcount=0)
            target = p.get("cancel") if "cancel" in p else p.get("tgt")
            cur = p.get("cur")
            # 낙관 잠금 가드: 현재값이 :cur와 일치할 때만 갱신.
            if r["job_status"] != cur:
                return _Res(rowcount=0)
            r["job_status"] = target
            return _Res(rowcount=1)
        return _Res()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


async def _seed_run(db, tenant="t-a", project="p1"):
    res = await store.persist_design_run(
        db=db, tenant_id=tenant, project_id=project,
        building_width_m=30, building_depth_m=12, num_floors=8, floor_height_m=3.0)
    return res["run_id"]


@pytest.mark.asyncio
async def test_seeded_run_has_null_job_status():
    db = _FakeDesignRunsDb()
    rid = await _seed_run(db)
    got = await job.get_job(db=db, run_id=rid, tenant_id="t-a")
    assert got is not None and got["job_status"] is None


@pytest.mark.asyncio
async def test_job_lifecycle_queued_running_succeeded():
    db = _FakeDesignRunsDb()
    rid = await _seed_run(db)
    r1 = await job.set_job_status(db=db, run_id=rid, target="QUEUED", tenant_id="t-a")
    assert r1["ok"] and r1["job_status"] == "QUEUED"
    r2 = await job.set_job_status(db=db, run_id=rid, target="RUNNING", tenant_id="t-a")
    assert r2["ok"] and r2["job_status"] == "RUNNING"
    r3 = await job.set_job_status(db=db, run_id=rid, target="SUCCEEDED", tenant_id="t-a")
    assert r3["ok"] and r3["job_status"] == "SUCCEEDED"


@pytest.mark.asyncio
async def test_illegal_transition_is_conflict():
    """★불법 전이(QUEUED→SUCCEEDED) → code=conflict(라우터 409)."""
    db = _FakeDesignRunsDb()
    rid = await _seed_run(db)
    await job.set_job_status(db=db, run_id=rid, target="QUEUED", tenant_id="t-a")
    out = await job.set_job_status(db=db, run_id=rid, target="SUCCEEDED", tenant_id="t-a")
    assert out["ok"] is False and out["code"] == "conflict"


@pytest.mark.asyncio
async def test_cancel_from_running_succeeds():
    db = _FakeDesignRunsDb()
    rid = await _seed_run(db)
    await job.set_job_status(db=db, run_id=rid, target="RUNNING", tenant_id="t-a")
    out = await job.cancel_job(db=db, run_id=rid, tenant_id="t-a")
    assert out["ok"] is True and out["job_status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_cancel_terminal_is_conflict_409():
    """★터미널 재취소 → code=conflict(라우터 409). 상태는 그대로."""
    db = _FakeDesignRunsDb()
    rid = await _seed_run(db)
    await job.set_job_status(db=db, run_id=rid, target="RUNNING", tenant_id="t-a")
    await job.set_job_status(db=db, run_id=rid, target="SUCCEEDED", tenant_id="t-a")
    out = await job.cancel_job(db=db, run_id=rid, tenant_id="t-a")
    assert out["ok"] is False and out["code"] == "conflict"
    got = await job.get_job(db=db, run_id=rid, tenant_id="t-a")
    assert got["job_status"] == "SUCCEEDED"  # 재취소 무효


@pytest.mark.asyncio
async def test_cancel_not_found():
    db = _FakeDesignRunsDb()
    out = await job.cancel_job(db=db, run_id="dr_missing", tenant_id="t-a")
    assert out["ok"] is False and out["code"] == "not_found"


@pytest.mark.asyncio
async def test_set_job_status_not_found():
    db = _FakeDesignRunsDb()
    out = await job.set_job_status(db=db, run_id="dr_missing", target="QUEUED", tenant_id="t-a")
    assert out["ok"] is False and out["code"] == "not_found"


@pytest.mark.asyncio
async def test_require_expected_version_mismatch_is_conflict():
    """If-Match 의미론 — expected_current 불일치 시 conflict(낙관 잠금)."""
    db = _FakeDesignRunsDb()
    rid = await _seed_run(db)
    await job.set_job_status(db=db, run_id=rid, target="QUEUED", tenant_id="t-a")
    out = await job.set_job_status(
        db=db, run_id=rid, target="RUNNING", tenant_id="t-a",
        expected_current="RUNNING", require_expected=True)  # 현재는 QUEUED
    assert out["ok"] is False and out["code"] == "conflict"


@pytest.mark.asyncio
async def test_job_ops_are_tenant_scoped():
    """★테넌트 스코프 — 다른 테넌트로는 run이 안 보인다(not_found)."""
    db = _FakeDesignRunsDb()
    rid = await _seed_run(db, tenant="t-a")
    assert await job.get_job(db=db, run_id=rid, tenant_id="t-b") is None
    out = await job.cancel_job(db=db, run_id=rid, tenant_id="t-b")
    assert out["ok"] is False and out["code"] == "not_found"


# ══════════════════════════════════════════════════════════════════════════
# 3) ★차원 독립성 — job상태 전이가 승인상태를, 승인상태가 job상태를 안 건드린다
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_job_and_approval_are_independent_dimensions():
    """★핵심 게이트 — 승인(APPROVED) 후 실행 취소해도 승인상태는 APPROVED로 유지(별도 축)."""
    db = _FakeDesignRunsDb()
    rid = await _seed_run(db)
    # 실행차원 진행.
    await job.set_job_status(db=db, run_id=rid, target="RUNNING", tenant_id="t-a")
    # 승인차원 승격(job과 무관).
    appr = await store.approve_design_run(db=db, run_id=rid, approved_by="admin@x", tenant_id="t-a")
    assert appr["status"] == "APPROVED"
    # 실행 취소(승인과 무관) — 승인상태는 그대로 APPROVED, 실행상태만 CANCELLED.
    cancel = await job.cancel_job(db=db, run_id=rid, tenant_id="t-a")
    assert cancel["job_status"] == "CANCELLED"
    run = await store.get_design_run(db=db, run_id=rid, tenant_id="t-a")
    assert run["status"] == "APPROVED"  # ★승인상태 무변(job 취소가 승인을 되돌리지 않음)


def test_job_module_never_writes_approval_status():
    """★차원 분리(정적) — design_run_job은 승인차원 status를 절대 쓰지 않는다."""
    src = inspect.getsource(job)
    for forbidden in ("SET status", "status = 'APPROVED'", "status = 'DRAFT'",
                      "status='APPROVED'", "status='DRAFT'"):
        assert forbidden not in src, f"승인상태 변이 금지 위반: {forbidden}"


def test_store_module_never_writes_job_status():
    """★차원 분리(정적·미러) — design_run_store는 실행차원 job_status를 절대 쓰지 않는다(WP-E 불변식)."""
    src = inspect.getsource(store)
    assert "SET job_status" not in src
    assert "job_status =" not in src


def test_job_module_never_mutates_analysis_ledger():
    """★원장 무접촉 — job 모듈에 analysis_ledger 변이 구문 0."""
    src = inspect.getsource(job)
    for stmt in ("INSERT INTO analysis_ledger", "UPDATE analysis_ledger",
                 "ALTER TABLE analysis_ledger", "DELETE FROM analysis_ledger"):
        assert stmt not in src


def test_job_schema_reuses_store_ddl_no_new_alembic():
    """★그린필드 금지 — 기반 테이블 DDL 재작성 없이 store._ensure_schema 재사용 + ADD COLUMN IF NOT EXISTS."""
    src = inspect.getsource(job)
    assert "design_run_store._ensure_schema" in src
    assert "ADD COLUMN IF NOT EXISTS job_status" in src
    # 신규 테이블 DDL(design_runs 재정의) 없음 — 기반 테이블은 store가 소유(그린필드 금지).
    assert "CREATE TABLE IF NOT EXISTS design_runs" not in src
