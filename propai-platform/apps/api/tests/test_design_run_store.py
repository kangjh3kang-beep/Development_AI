"""design_run_store(WP-E · P10) 단위·계약 테스트 — 앵커 통일·결정성·테넌트스코프·승인차원.

핵심 게이트(계획서 §4 WP-E 명기):
- ①동일 seed+input_hash→동일 geometry_hash 재현(결정성).
- ③타임아웃/부분해는 DRAFT만(APPROVED 전이는 명시 approve 액션만).
- ④테넌트 스코프(run_id 해시 tenant 편입 + 쿼리 tenant_id IS NOT DISTINCT FROM).
- provenance 앵커 통일: 표면 A(bare 스탬프)/B(enriched 매스)/C(resolved 계약)가 같은 bare 기하면
  동일 input_hash(발산 봉합). 표면별 해시는 surface_hashes에 별도 보존.

라이브 DB 없이도 결정적으로 검증하기 위해 (1) 순수 헬퍼는 직접 호출, (2) 영속 로직은 store가
작성한 SQL을 충실히 모사하는 인메모리 fake DB로 구동, (3) DB 전용 계약(CREATE TABLE IF NOT
EXISTS·원장 무접촉 등)은 소스 텍스트 정적 검사로 확인한다(site_basis 선례 동형·정직 기재).
"""
from __future__ import annotations

import inspect
import json

import pytest

from app.services.cad import design_run_store as store

# ══════════════════════════════════════════════════════════════════════════
# 1) 순수 헬퍼 — 앵커 통일·결정성·run_id 스코프·상태전이(DB 불요)
# ══════════════════════════════════════════════════════════════════════════

def test_canonical_anchor_contains_only_bare_geometry():
    """앵커는 폭·깊이·층수·층고 4개 기하 키만 담는다(부착물·비-기하 입력 배제)."""
    anchor = store.canonical_design_anchor(
        building_width_m=30, building_depth_m=12, num_floors=8, floor_height_m=3.2
    )
    assert set(anchor.keys()) == {
        "building_width_m", "building_depth_m", "num_floors", "floor_height_m"
    }
    assert anchor["num_floors"] == 8  # 층수는 정수 정체
    assert anchor["building_width_m"] == 30.0  # float 통일


def test_anchor_unifies_surfaces_A_B_C():
    """★앵커 통일(PR#290 MEDIUM 봉합) — bare/enriched/resolved 세 표면이 같은 input_hash."""
    # A) save_drawing 스탬프: bare 4스칼라(num_floors 키).
    surface_a = {"building_width_m": 30.0, "building_depth_m": 12.0,
                 "num_floors": 8, "floor_height_m": 3.2}
    # B) glb/generate: enriched 매스(부착물·전이 부기 섞임 — compliance·special_parcel·_cache_hit).
    surface_b = {"building_width_m": 30.0, "building_depth_m": 12.0,
                 "num_floors": 8, "floor_height_m": 3.2,
                 "compliance": {"far_pct": 250}, "special_parcel": {"warnings": []},
                 "_cache_hit": True, "core_positions": [[1, 2]], "total_units": 40}
    # C) generate 계약: resolved req(floor_count 키 + zone/use 등 비-기하 입력 섞임).
    surface_c = {"building_width_m": 30.0, "building_depth_m": 12.0,
                 "floor_count": 8, "floor_height_m": 3.2,
                 "zone_code": "3R", "building_use": "공동주택", "land_area_sqm": 900.0}

    ha = store.compute_anchor_input_hash(store.anchor_from_mass(surface_a))
    hb = store.compute_anchor_input_hash(store.anchor_from_mass(surface_b))
    hc = store.compute_anchor_input_hash(store.anchor_from_mass(surface_c))
    assert ha == hb == hc  # 같은 bare 기하 → 표면 무관 동일 input_hash


def test_anchor_from_mass_aliases_num_floors_and_floor_count():
    """num_floors(매스)와 floor_count(요청)는 같은 값을 부른다 — 둘 다 같은 앵커."""
    a = store.anchor_from_mass({"building_width_m": 10, "building_depth_m": 10,
                                "num_floors": 5, "floor_height_m": 3.0})
    b = store.anchor_from_mass({"building_width_m": 10, "building_depth_m": 10,
                               "floor_count": 5, "floor_height_m": 3.0})
    assert a == b


def test_input_hash_deterministic_int_float_insensitive():
    """같은 기하는 int/float 표기가 달라도 같은 input_hash(멱등 강건성)."""
    h1 = store.compute_anchor_input_hash(store.canonical_design_anchor(
        building_width_m=30, building_depth_m=12, num_floors=8, floor_height_m=3))
    h2 = store.compute_anchor_input_hash(store.canonical_design_anchor(
        building_width_m=30.0, building_depth_m=12.0, num_floors=8, floor_height_m=3.0))
    assert h1 == h2


def test_geometry_hash_deterministic_and_derived():
    """geometry_hash는 같은 앵커에 결정적이며 파생 기하(높이·바닥면적)를 반영한다."""
    anchor = store.canonical_design_anchor(
        building_width_m=30, building_depth_m=12, num_floors=8, floor_height_m=3.0)
    g1 = store.compute_anchor_geometry_hash(anchor)
    g2 = store.compute_anchor_geometry_hash(dict(anchor))
    assert g1 == g2
    # 층수가 바뀌면(=높이 변화) geometry_hash도 바뀐다.
    anchor2 = dict(anchor, num_floors=9)
    assert store.compute_anchor_geometry_hash(anchor2) != g1


def test_reproducibility_same_seed_input_hash_same_geometry_hash():
    """★게이트① — 동일 seed+input_hash면 동일 geometry_hash(재현). 앵커에서 결정적 파생이라 성립."""
    anchor = store.anchor_from_mass(
        {"building_width_m": 24.0, "building_depth_m": 14.0, "num_floors": 12, "floor_height_m": 3.1})
    ih_a = store.compute_anchor_input_hash(anchor)
    gh_a = store.compute_anchor_geometry_hash(anchor)
    # 완전히 독립적으로 재구성한 동일 기하.
    anchor_again = store.anchor_from_mass(
        {"floor_count": 12, "building_width_m": 24, "building_depth_m": 14, "floor_height_m": 3.1})
    assert store.compute_anchor_input_hash(anchor_again) == ih_a
    assert store.compute_anchor_geometry_hash(anchor_again) == gh_a


def test_run_id_is_tenant_scoped():
    """★게이트④ — 같은 앵커라도 테넌트가 다르면 run_id가 다르다(IDOR 교차충돌 차단)."""
    ih = store.compute_anchor_input_hash(store.canonical_design_anchor(
        building_width_m=20, building_depth_m=10, num_floors=5, floor_height_m=3.0))
    rid_a = store.make_design_run_id(tenant_id="tenant-a", project_id="p1", seed="default", input_hash=ih)
    rid_b = store.make_design_run_id(tenant_id="tenant-b", project_id="p1", seed="default", input_hash=ih)
    assert rid_a != rid_b
    assert rid_a.startswith("dr_") and rid_b.startswith("dr_")


def test_run_id_is_project_and_seed_scoped():
    """같은 테넌트라도 프로젝트·seed가 다르면 run_id가 다르다(독립 실행 식별)."""
    ih = store.compute_anchor_input_hash(store.canonical_design_anchor(
        building_width_m=20, building_depth_m=10, num_floors=5, floor_height_m=3.0))
    base = store.make_design_run_id(tenant_id="t", project_id="p1", seed="s1", input_hash=ih)
    assert store.make_design_run_id(tenant_id="t", project_id="p2", seed="s1", input_hash=ih) != base
    assert store.make_design_run_id(tenant_id="t", project_id="p1", seed="s2", input_hash=ih) != base


def test_run_id_stable_for_same_scope():
    """같은 (tenant·project·seed·input_hash)는 항상 같은 run_id(멱등)."""
    ih = "abc123"
    r1 = store.make_design_run_id(tenant_id="t", project_id="p", seed="default", input_hash=ih)
    r2 = store.make_design_run_id(tenant_id="t", project_id="p", seed="default", input_hash=ih)
    assert r1 == r2


def test_zero_dimension_preserved_not_dropped():
    """0-falsy 금지 — 폭 0.0도 앵커에 보존된다(누락 시 다른 기하가 같은 해시로 오염)."""
    anchor = store.canonical_design_anchor(
        building_width_m=0.0, building_depth_m=12, num_floors=8, floor_height_m=3.0)
    assert anchor["building_width_m"] == 0.0  # None이 아니라 0.0로 보존


def test_none_dimension_stays_none():
    """미제공 기하는 None으로 남는다(무날조 — 가짜 기본값 주입 안 함)."""
    anchor = store.canonical_design_anchor(
        building_width_m=None, building_depth_m=12, num_floors=None, floor_height_m=None)
    assert anchor["building_width_m"] is None
    assert anchor["num_floors"] is None
    assert anchor["floor_height_m"] is None


def test_can_approve_requires_nonempty_approver():
    """★게이트③ — 승인자 없으면 APPROVED 전이 거부(무인 승인 0)."""
    ok, _ = store.can_approve_design_run(store.STATUS_DRAFT, None)
    assert ok is False
    ok, _ = store.can_approve_design_run(store.STATUS_DRAFT, "   ")
    assert ok is False


def test_can_approve_only_from_draft():
    """★게이트③ — DRAFT에서만 승인 가능. APPROVED 재승인·기타 상태는 거부."""
    ok, _ = store.can_approve_design_run(store.STATUS_DRAFT, "admin@x")
    assert ok is True
    ok, _ = store.can_approve_design_run(store.STATUS_APPROVED, "admin@x")
    assert ok is False
    ok, _ = store.can_approve_design_run("QUEUED", "admin@x")  # 실행상태 혼입 방어
    assert ok is False


# ══════════════════════════════════════════════════════════════════════════
# 2) 정적 계약 — DDL·원장무접촉·테넌트스코프·승인보존(소스 텍스트 검사)
# ══════════════════════════════════════════════════════════════════════════

def test_ddl_uses_create_table_if_not_exists_no_alembic():
    """★신규 alembic 헤드 0 — schema_guard(CREATE TABLE IF NOT EXISTS)로만 생성."""
    assert "CREATE TABLE IF NOT EXISTS design_runs" in store._DESIGN_RUNS_DDL
    for ix in store._INDEXES:
        assert "CREATE INDEX IF NOT EXISTS" in ix


def test_status_column_is_approval_dimension_only():
    """승인차원(DRAFT/APPROVED)만 status가 소유 — 실행상태(job)는 혼용 금지."""
    assert store.STATUS_DRAFT == "DRAFT"
    assert store.STATUS_APPROVED == "APPROVED"
    src = inspect.getsource(store)
    # 승인차원 status 컬럼에 실행상태 리터럴을 절대 넣지 않는다.
    for job_literal in ("status = 'QUEUED'", "status = 'RUNNING'", "status = 'CANCELLED'",
                        "status = 'FAILED'", "'DRAFT' | 'QUEUED'"):
        assert job_literal not in src


def test_job_status_column_reserved_but_untouched():
    """job_status는 WP-L 예약 컬럼 — DDL에 존재하되 이 WP는 읽지도 쓰지도 않는다."""
    assert "job_status text" in store._DESIGN_RUNS_DDL
    src = inspect.getsource(store)
    assert "SET job_status" not in src  # 갱신 0
    assert "job_status =" not in src    # 조건·대입 0
    assert "job_status," not in src.replace("job_status text,", "")  # SELECT/INSERT 컬럼목록 0


def test_source_never_mutates_analysis_ledger():
    """★원장 무접촉 — analysis_ledger 대상 DDL/DML 구문 0(append-only 보존·site_basis 선례 동형)."""
    src = inspect.getsource(store)
    forbidden = ("INSERT INTO analysis_ledger", "UPDATE analysis_ledger",
                 "ALTER TABLE analysis_ledger", "DELETE FROM analysis_ledger",
                 "DROP TABLE analysis_ledger", "CREATE TABLE IF NOT EXISTS analysis_ledger")
    for stmt in forbidden:
        assert stmt not in src, f"원장 변이 금지 위반 의심 구문: {stmt}"


def test_queries_are_tenant_scoped():
    """★게이트④ — 조회·승인 쿼리가 tenant_id IS NOT DISTINCT FROM으로 스코프된다."""
    src = inspect.getsource(store)
    assert src.count("tenant_id IS NOT DISTINCT FROM :tid") >= 3  # persist 확인·get·approve


def test_on_conflict_preserves_existing_approval():
    """★승인 무음취소 방지(site_basis MEDIUM-2 교훈) — ON CONFLICT가 status/approved_*를 미갱신."""
    src = inspect.getsource(store)
    # ON CONFLICT DO UPDATE 절에는 status·approved_by·approved_at 대입이 없어야 한다.
    conflict_start = src.index("ON CONFLICT (run_id) DO UPDATE SET")
    conflict_block = src[conflict_start:conflict_start + 600]
    assert "status = EXCLUDED" not in conflict_block
    assert "approved_by = EXCLUDED" not in conflict_block
    assert "approved_at = EXCLUDED" not in conflict_block


def test_surface_hashes_merged_not_overwritten():
    """표면별 해시는 덮어쓰지 않고 jsonb concat(||)으로 누적한다."""
    src = inspect.getsource(store)
    assert "surface_hashes = design_runs.surface_hashes || EXCLUDED.surface_hashes" in src


# ══════════════════════════════════════════════════════════════════════════
# 3) 인메모리 fake DB 구동 — persist/get/approve 오케스트레이션(테넌트격리·승인전이)
# ══════════════════════════════════════════════════════════════════════════

def _tenant_match(row_tenant, query_tenant) -> bool:
    """IS NOT DISTINCT FROM 의미론 — 둘 다 None도 일치."""
    return row_tenant == query_tenant


class _Res:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeDesignRunsDb:
    """store가 작성한 design_runs SQL을 충실히 모사하는 인메모리 fake(라이브 DB 불가 대체)."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(getattr(statement, "text", statement))
        p = params or {}
        if "CREATE TABLE" in sql or "CREATE INDEX" in sql:
            return _Res(None)
        if sql.strip().startswith("INSERT INTO design_runs"):
            rid = p["rid"]
            new_surface = json.loads(p["sh"])
            if rid in self.rows:
                r = self.rows[rid]
                r["compiler_version"] = p["cv"]
                r["input_hash"] = p["ih"]
                r["geometry_hash"] = p["gh"]
                r["metrics"] = json.loads(p["mj"])
                merged = dict(r.get("surface_hashes") or {})
                merged.update(new_surface)  # jsonb || 병합 모사
                r["surface_hashes"] = merged
                # ★status/approved_by 미갱신(승인 보존) — store의 ON CONFLICT 계약 모사.
            else:
                self.rows[rid] = {
                    "run_id": rid, "tenant_id": p["tid"], "project_id": p["pid"],
                    "seed": p["seed"], "compiler_version": p["cv"], "input_hash": p["ih"],
                    "surface_hashes": new_surface, "geometry_hash": p["gh"],
                    "metrics": json.loads(p["mj"]), "status": "DRAFT", "approved_by": None,
                }
            return _Res(None)
        if sql.strip().startswith("SELECT status FROM design_runs"):
            r = self.rows.get(p["rid"])
            if r is None or not _tenant_match(r["tenant_id"], p.get("tid")):
                return _Res(None)
            return _Res((r["status"],))
        if "SELECT run_id, tenant_id, project_id" in sql:
            r = self.rows.get(p["rid"])
            if r is None or not _tenant_match(r["tenant_id"], p.get("tid")):
                return _Res(None)
            return _Res((r["run_id"], r["tenant_id"], r["project_id"], r["seed"],
                         r["compiler_version"], r["input_hash"], r["surface_hashes"],
                         r["geometry_hash"], r["metrics"], r["status"], r["approved_by"]))
        if sql.strip().startswith("UPDATE design_runs SET status = 'APPROVED'"):
            r = self.rows.get(p["rid"])
            if r is not None:
                r["status"] = "APPROVED"
                r["approved_by"] = p["by"]
            return _Res(None)
        return _Res(None)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_persist_then_get_returns_draft():
    db = _FakeDesignRunsDb()
    res = await store.persist_design_run(
        db=db, tenant_id="t-a", project_id="p1",
        building_width_m=30, building_depth_m=12, num_floors=8, floor_height_m=3.0,
        surface="save_stamp", surface_hash="deadbeef", metrics={"floor_count": 8})
    assert res["status"] == "DRAFT"
    got = await store.get_design_run(db=db, run_id=res["run_id"], tenant_id="t-a")
    assert got is not None
    assert got["status"] == "DRAFT"
    assert got["input_hash"] == res["input_hash"]
    assert got["surface_hashes"] == {"save_stamp": "deadbeef"}


@pytest.mark.asyncio
async def test_get_is_tenant_isolated():
    """★게이트④ — 다른 테넌트로 조회하면 존재해도 None(교차테넌트 조회 차단)."""
    db = _FakeDesignRunsDb()
    res = await store.persist_design_run(
        db=db, tenant_id="t-a", project_id="p1",
        building_width_m=30, building_depth_m=12, num_floors=8, floor_height_m=3.0)
    assert await store.get_design_run(db=db, run_id=res["run_id"], tenant_id="t-b") is None
    assert await store.get_design_run(db=db, run_id=res["run_id"], tenant_id="t-a") is not None


@pytest.mark.asyncio
async def test_approve_transitions_draft_to_approved():
    """★게이트③ — 명시 approve만 DRAFT→APPROVED로 전이한다."""
    db = _FakeDesignRunsDb()
    res = await store.persist_design_run(
        db=db, tenant_id="t-a", project_id="p1",
        building_width_m=30, building_depth_m=12, num_floors=8, floor_height_m=3.0)
    out = await store.approve_design_run(db=db, run_id=res["run_id"], approved_by="admin@x", tenant_id="t-a")
    assert out["ok"] is True
    assert out["status"] == "APPROVED"
    got = await store.get_design_run(db=db, run_id=res["run_id"], tenant_id="t-a")
    assert got["status"] == "APPROVED" and got["approved_by"] == "admin@x"


# ══════════════════════════════════════════════════════════════════════════
# 4) SoD(직무분리, 백로그③) — design_run은 author 개념 자체가 없어 항상 skip 표식
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_approve_sod_check_is_always_skip_marker_no_author_concept():
    """★design_runs·persist_design_run 어디에도 author(작성자) 컬럼·인자가 없다 — 자기승인
    비교 자체가 성립하지 않으므로 누가 승인하든 sod_check는 항상 "skipped(author 미기록)"이다
    (무언 "passed" 참칭 금지 — W1-B 정직 표기 원칙). 이는 곧 이 경로에서 실제 SoD 차단이
    "발생하지 않는다"는 사실을 기계적으로 고정한다(author 배선 전까지는 정직한 통과일 뿐)."""
    db = _FakeDesignRunsDb()
    res = await store.persist_design_run(
        db=db, tenant_id="t-a", project_id="p1",
        building_width_m=30, building_depth_m=12, num_floors=8, floor_height_m=3.0)
    out = await store.approve_design_run(db=db, run_id=res["run_id"], approved_by="admin@x", tenant_id="t-a")
    assert out["ok"] is True
    assert out["sod_check"] == "skipped(author 미기록)"


@pytest.mark.asyncio
async def test_approve_regression_unaffected_by_sod_wiring():
    """★무회귀 — SoD 배선 이후에도 기존 승인 흐름(성공 status/approved_by)은 그대로 유지."""
    db = _FakeDesignRunsDb()
    res = await store.persist_design_run(
        db=db, tenant_id="t-a", project_id="p1",
        building_width_m=20, building_depth_m=10, num_floors=5, floor_height_m=3.0)
    out = await store.approve_design_run(db=db, run_id=res["run_id"], approved_by="reviewer@x", tenant_id="t-a")
    assert out == {
        "ok": True, "run_id": res["run_id"], "status": "APPROVED",
        "approved_by": "reviewer@x", "sod_check": "skipped(author 미기록)",
    }


@pytest.mark.asyncio
async def test_approve_wrong_tenant_is_not_found():
    """★게이트④ — 다른 테넌트의 run_id 승인 시도는 '없음'으로 거부(IDOR 오라클 방지)."""
    db = _FakeDesignRunsDb()
    res = await store.persist_design_run(
        db=db, tenant_id="t-a", project_id="p1",
        building_width_m=30, building_depth_m=12, num_floors=8, floor_height_m=3.0)
    out = await store.approve_design_run(db=db, run_id=res["run_id"], approved_by="admin@x", tenant_id="t-b")
    assert out["ok"] is False
    # 원본은 여전히 DRAFT(무단 승격 0).
    got = await store.get_design_run(db=db, run_id=res["run_id"], tenant_id="t-a")
    assert got["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_repersist_preserves_existing_approval():
    """★승인 무음취소 방지 — 승인 후 같은 run_id 재저장이 status를 DRAFT로 되돌리지 않는다."""
    db = _FakeDesignRunsDb()
    res = await store.persist_design_run(
        db=db, tenant_id="t-a", project_id="p1",
        building_width_m=30, building_depth_m=12, num_floors=8, floor_height_m=3.0)
    await store.approve_design_run(db=db, run_id=res["run_id"], approved_by="admin@x", tenant_id="t-a")
    # 동일 기하 재저장(예: 재편집 저장) — 반환 status는 보존된 APPROVED여야 한다.
    res2 = await store.persist_design_run(
        db=db, tenant_id="t-a", project_id="p1",
        building_width_m=30, building_depth_m=12, num_floors=8, floor_height_m=3.0,
        surface="glb", surface_hash="cafef00d")
    assert res2["run_id"] == res["run_id"]
    assert res2["status"] == "APPROVED"  # 무음 강등 0


@pytest.mark.asyncio
async def test_persist_merges_multiple_surface_hashes():
    """표면 save_stamp·glb를 각각 저장하면 두 해시가 모두 누적된다(덮어쓰기 0)."""
    db = _FakeDesignRunsDb()
    r1 = await store.persist_design_run(
        db=db, tenant_id="t-a", project_id="p1",
        building_width_m=30, building_depth_m=12, num_floors=8, floor_height_m=3.0,
        surface="save_stamp", surface_hash="aaa")
    await store.persist_design_run(
        db=db, tenant_id="t-a", project_id="p1",
        building_width_m=30, building_depth_m=12, num_floors=8, floor_height_m=3.0,
        surface="glb", surface_hash="bbb")
    got = await store.get_design_run(db=db, run_id=r1["run_id"], tenant_id="t-a")
    assert got["surface_hashes"] == {"save_stamp": "aaa", "glb": "bbb"}
