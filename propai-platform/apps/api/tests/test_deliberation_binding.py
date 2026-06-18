"""중심엔진 통합 Phase 1 — engine_run_binding(run_id↔테넌트·멱등) 통합테스트.

실 Postgres(없으면 skip — 거짓통과 금지). 멱등키=(tenant, content_input_hash, snapshot_id):
동일 입력 재호출 시 기존 run_id 재사용(엔진 재호출 차단), 테넌트 격리(교차 read None).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.services.deliberation import binding_service as b


@pytest.fixture
async def binding_db():
    from app.core.database import async_session_factory, engine

    await engine.dispose()
    try:
        async with async_session_factory() as probe:
            await probe.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"DB 미가용 — binding 통합테스트 skip: {str(e)[:80]}")
    async with async_session_factory() as db:
        yield db


@pytest.fixture
async def tnt(binding_db):
    t = f"test-{uuid.uuid4().hex[:12]}"
    yield t
    await binding_db.execute(text("DELETE FROM engine_run_binding WHERE tenant_id = :t"), {"t": t})
    await binding_db.commit()


async def test_insert_then_lookup(tnt):
    cih, sid = "cih-aaa", "snap-1"
    assert await b.insert(run_id="run-1", tenant_id=tnt, content_input_hash=cih,
                          snapshot_id=sid, input_hash="ih-1", source="sync") is True
    row = await b.lookup(tenant_id=tnt, content_input_hash=cih, snapshot_id=sid)
    assert row is not None and row["run_id"] == "run-1" and row["source"] == "sync"


async def test_idempotent_conflict_reuses_existing(tnt):
    cih, sid = "cih-bbb", "snap-1"
    assert await b.insert(run_id="run-1", tenant_id=tnt, content_input_hash=cih,
                          snapshot_id=sid, input_hash="ih-1", source="sync") is True
    # 동일 멱등키 재삽입(재시도/동시성) → False, 기존 run_id 보존.
    assert await b.insert(run_id="run-2", tenant_id=tnt, content_input_hash=cih,
                          snapshot_id=sid, input_hash="ih-1", source="sync") is False
    row = await b.lookup(tenant_id=tnt, content_input_hash=cih, snapshot_id=sid)
    assert row["run_id"] == "run-1"


async def test_different_snapshot_is_separate_binding(tnt):
    cih = "cih-ccc"
    assert await b.insert(run_id="run-s1", tenant_id=tnt, content_input_hash=cih,
                          snapshot_id="snap-1", input_hash="ih-1", source="sync") is True
    # reconcile가 snapshot 갱신 → 같은 content_input_hash라도 다른 snapshot은 별 결속(별 run).
    assert await b.lookup(tenant_id=tnt, content_input_hash=cih, snapshot_id="snap-2") is None
    assert await b.insert(run_id="run-s2", tenant_id=tnt, content_input_hash=cih,
                          snapshot_id="snap-2", input_hash="ih-2", source="sync") is True


async def test_tenant_isolation_lookup(tnt):
    cih, sid = "cih-ddd", "snap-1"
    await b.insert(run_id="run-x", tenant_id=tnt, content_input_hash=cih,
                   snapshot_id=sid, input_hash="ih", source="sync")
    # 다른 테넌트는 같은 멱등키로도 조회 불가(격리).
    assert await b.lookup(tenant_id="other-tenant", content_input_hash=cih, snapshot_id=sid) is None
    # run_id 소유 검증: 소유 테넌트만, 타테넌트는 None(→404).
    assert (await b.lookup_by_run(tenant_id=tnt, run_id="run-x"))["run_id"] == "run-x"
    assert await b.lookup_by_run(tenant_id="other-tenant", run_id="run-x") is None


async def test_nondeterministic_runs_bypass_idempotent_dedup(tnt):
    # ★핵심 안전속성: 부분 유니크 'WHERE deterministic' — 비결정(VLLM/라이브) run은 동일 멱등키라도
    # 매 호출 별 행(둘 다 True). 'WHERE deterministic'가 빠지면 두 번째가 False가 되어 RED.
    cih, sid = "cih-nondet", "snap-1"
    assert await b.insert(run_id="nd-1", tenant_id=tnt, content_input_hash=cih, snapshot_id=sid,
                          input_hash="ih-1", source="sync", deterministic=False) is True
    assert await b.insert(run_id="nd-2", tenant_id=tnt, content_input_hash=cih, snapshot_id=sid,
                          input_hash="ih-2", source="sync", deterministic=False) is True
    # 두 비결정 run 모두 결속 조회 가능(run_id PK 유일).
    assert (await b.lookup_by_run(tenant_id=tnt, run_id="nd-1"))["run_id"] == "nd-1"
    assert (await b.lookup_by_run(tenant_id=tnt, run_id="nd-2"))["run_id"] == "nd-2"


async def test_result_jsonb_roundtrip(tnt):
    # 재사용/GET이 권위본으로 반환하는 result(jsonb) 라운드트립 — 중첩/한글 보존 + status.
    cih, sid = "cih-json", "snap-1"
    payload = {"input_hash": "ih-1", "report": {"items": [1, 2], "note": "한글 근거"}, "skipped": []}
    assert await b.insert(run_id="run-j", tenant_id=tnt, content_input_hash=cih, snapshot_id=sid,
                          input_hash="ih-1", source="async", status="DONE", result=payload) is True
    row = await b.lookup_by_run(tenant_id=tnt, run_id="run-j")
    assert row["result"] == payload and row["status"] == "DONE"
