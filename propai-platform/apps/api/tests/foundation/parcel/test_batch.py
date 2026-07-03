"""F-Parcel 배치 인수 테스트(AT-M1 ~ AT-M11).

라이브콜 0: InMemoryJobStore + FakeVWorld 만 사용(DB·네트워크 없음).
pytest-asyncio 미설치 환경에서도 동작하도록 asyncio.run 으로 동기 래핑한다.
"""

from __future__ import annotations

import asyncio

import pytest
from _fakes import FakeVWorld  # 같은 디렉터리 _fakes 모듈(conftest 가 path 추가)

from app.foundation.parcel.batch.aggregator import Aggregator
from app.foundation.parcel.batch.batch_service import BatchService
from app.foundation.parcel.batch.job_runner import JobRunner
from app.foundation.parcel.batch.job_store import InMemoryJobStore
from app.foundation.parcel.contracts.batch import (
    BatchInput,
    Completeness,
    ItemStatus,
    JobState,
)


def _service(fake: FakeVWorld) -> BatchService:
    """FakeVWorld 를 주입한 인메모리 BatchService 를 만든다."""
    store = InMemoryJobStore()
    runner = JobRunner(vworld=fake)
    aggregator = Aggregator(vworld=fake)
    return BatchService(store=store, runner=runner, aggregator=aggregator, vworld=fake)


def _run(coro):
    return asyncio.run(coro)


# ── AT-M1: 폴리곤/bbox 배치 → 전 필지 해석(total == region_parcel_count) ──

def test_AT_M1_bbox_all_parcels_resolved():
    fake = FakeVWorld(
        confirmed_pnus=["1111010100100010000", "1111010100100020000"],
        ambiguous_pnus=[],
        bbox_pnus=["1111010100100010000", "1111010100100020000"],
    )
    svc = _service(fake)

    async def go():
        job = await svc.submit(BatchInput(bbox=(126.9, 37.5, 127.0, 37.6)))
        res = await svc.result(job.id, wait=True)
        return res

    res = _run(go())
    # bbox 가 돌려준 필지 수만큼 모두 해석됨.
    assert res.counts.total == 2
    assert res.counts.confirmed == 2


# ── AT-M2: 일부 실패 → 부분 비전체화 ──

def test_AT_M2_partial_not_whole_failure():
    fake = FakeVWorld(
        confirmed_pnus=["1111010100100010000", "1111010100100020000"],
        ambiguous_pnus=[],
        bbox_pnus=["1111010100100010000", "1111010100100020000", "9999999999999999999"],
    )
    svc = _service(fake)

    async def go():
        job = await svc.submit(BatchInput(bbox=(126.9, 37.5, 127.0, 37.6)))
        return await svc.result(job.id, wait=True)

    res = _run(go())
    # 미존재 필지(9999...)는 NOT_FOUND, 나머지는 확정 — 전체 실패 아님.
    assert res.counts.not_found > 0
    assert res.counts.confirmed > 0
    assert res.completeness in (Completeness.PARTIAL, Completeness.COMPLETE)
    assert res.state != JobState.FAILED


# ── AT-M3: 단일 SLA — 단일 해석이 배치 store/락에 막히지 않음(구조적 독립) ──

def test_AT_M3_single_path_independent():
    fake = FakeVWorld()
    runner = JobRunner(vworld=fake)

    async def go():
        # 단일 필지 해석은 BatchService/store 없이 직접 호출 가능해야 한다.
        item = await runner.resolve_one("1111010100100010000")
        return item

    item = _run(go())
    # 단일 경로가 배치 인프라와 독립적으로 즉시 확정됨.
    assert item.status == ItemStatus.CONFIRMED
    assert item.pnu == "1111010100100010000"


# ── AT-M4: 진행 중 마스터 갱신 → snapshot_id 불변 ──

def test_AT_M4_snapshot_immutable():
    fake = FakeVWorld()
    svc = _service(fake)

    async def go():
        job = await svc.submit(
            BatchInput(pnu_list=["1111010100100010000"]), snapshot_id="SNAP_FIXED"
        )
        before = job.snapshot_id
        # 실행(마스터가 바뀌었다고 가정해도 잡의 snapshot 은 고정).
        rec = await svc.run(job.id)
        return before, rec.job.snapshot_id

    before, after = _run(go())
    assert before == "SNAP_FIXED"
    assert after == "SNAP_FIXED"


# ── AT-M5: 부분결과 → completeness == PARTIAL and pending ──

def test_AT_M5_partial_completeness_and_pending():
    fake = FakeVWorld(
        confirmed_pnus=["1111010100100010000"],
        ambiguous_pnus=["1111010100100040000"],
    )
    svc = _service(fake)

    async def go():
        job = await svc.submit(
            BatchInput(pnu_list=["1111010100100010000", "1111010100100040000"])
        )
        return await svc.result(job.id, wait=True)

    res = _run(go())
    # 애매(AMBIGUOUS) 필지가 있어 미완결.
    assert res.completeness == Completeness.PARTIAL
    assert len(res.pending) >= 1
    assert "1111010100100040000" in res.pending


# ── AT-M6: 집계 완결성 — PARTIAL이면 held, COMPLETE면 union 있음 ──

def test_AT_M6_aggregate_held_when_partial():
    fake = FakeVWorld(
        confirmed_pnus=["1111010100100010000"],
        ambiguous_pnus=["1111010100100040000"],
    )
    svc = _service(fake)

    async def go():
        job = await svc.submit(
            BatchInput(pnu_list=["1111010100100010000", "1111010100100040000"])
        )
        return await svc.result(job.id, wait=True)

    res = _run(go())
    assert res.completeness == Completeness.PARTIAL
    assert res.aggregate.held is True
    assert res.aggregate.union_boundary is None


def test_AT_M6_aggregate_union_when_complete():
    fake = FakeVWorld(
        confirmed_pnus=["1111010100100010000", "1111010100100020000"],
        ambiguous_pnus=[],
    )
    svc = _service(fake)

    async def go():
        job = await svc.submit(
            BatchInput(pnu_list=["1111010100100010000", "1111010100100020000"])
        )
        return await svc.result(job.id, wait=True)

    res = _run(go())
    assert res.completeness == Completeness.COMPLETE
    assert res.aggregate.held is False
    assert res.aggregate.union_boundary is not None
    assert res.aggregate.total_area_sqm == 1500.0


# ── AT-M7: 멱등 — 동일 region+snapshot 재제출 → 동일 job_id ──

def test_AT_M7_idempotent_submit():
    fake = FakeVWorld()
    svc = _service(fake)

    async def go():
        inp = BatchInput(pnu_list=["1111010100100010000", "1111010100100020000"])
        j1 = await svc.submit(inp, snapshot_id="SNAP1")
        # 순서를 바꿔도 정규화로 동일 키 → 동일 job.
        inp2 = BatchInput(pnu_list=["1111010100100020000", "1111010100100010000"])
        j2 = await svc.submit(inp2, snapshot_id="SNAP1")
        return j1.id, j2.id

    id1, id2 = _run(go())
    assert id1 == id2


# ── AT-M8: 상태기계 — submit → cancel → CANCELLED ──

def test_AT_M8_cancel_state():
    fake = FakeVWorld()
    svc = _service(fake)

    async def go():
        job = await svc.submit(BatchInput(pnu_list=["1111010100100010000"]))
        cancelled = await svc.cancel(job.id)
        return cancelled.state

    state = _run(go())
    assert state == JobState.CANCELLED


# ── AT-M9: 미적재 구역 → degrade + live_calls == 0 ──

def test_AT_M9_degrade_no_live_calls():
    # admin_code 경로는 직접 API 없음 → degrade, 외부 호출 0.
    fake = FakeVWorld()
    svc = _service(fake)

    async def go():
        job = await svc.submit(BatchInput(admin_code="1111010100"))
        res = await svc.result(job.id, wait=True)
        rec = await svc.store.get(job.id)
        return res, rec

    res, rec = _run(go())
    assert rec.degrade_reason is not None        # 정직 degrade 플래그
    assert rec.target_pnus == []                 # 가짜 생성 없음
    assert fake.live_calls == 0                  # 라이브콜 0
    assert res.aggregate.held is True


def test_AT_M9_empty_bbox_degrade():
    # bbox 가 비어있으면(미적재) degrade. bbox 1콜 외 추가 라이브콜 없음.
    fake = FakeVWorld(bbox_pnus=[])
    svc = _service(fake)

    async def go():
        job = await svc.submit(BatchInput(bbox=(126.9, 37.5, 127.0, 37.6)))
        rec = await svc.store.get(job.id)
        await svc.result(job.id, wait=True)
        return rec

    rec = _run(go())
    assert rec.degrade_reason is not None
    assert rec.target_pnus == []


# ── AT-M10: 폴리곤 intersect 필터 — 폴리곤 밖 필지 제외 ──
# ※공간색인 EXPLAIN 대신 필터 정확성으로 대체 검증.

def test_AT_M10_polygon_intersect_filter():
    # 후보 2개: 하나는 폴리곤 안, 하나는 밖.
    inside = {
        "pnu": "1111010100100010000",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0.1, 0.1], [0.1, 0.4], [0.4, 0.4], [0.4, 0.1], [0.1, 0.1]]],
        },
    }
    outside = {
        "pnu": "1111010100100099999",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[5, 5], [5, 6], [6, 6], [6, 5], [5, 5]]],
        },
    }
    fake = FakeVWorld(
        confirmed_pnus=["1111010100100010000"],
        ambiguous_pnus=[],
        bbox_features=[inside, outside],
    )
    svc = _service(fake)

    # 단위 정사각형 폴리곤(0,0)-(1,1): inside 만 교차.
    polygon = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
    }

    async def go():
        job = await svc.submit(BatchInput(polygon=polygon))
        rec = await svc.store.get(job.id)
        res = await svc.result(job.id, wait=True)
        return rec, res

    rec, res = _run(go())
    assert rec.target_pnus == ["1111010100100010000"]   # 밖 필지 제외
    assert res.counts.total == 1


# ── AT-M11: 페이지네이션 — items <= size and has_next ──

def test_AT_M11_pagination():
    pnus = [
        "1111010100100010000",
        "1111010100100020000",
        "1111010100100030000",
    ]
    fake = FakeVWorld(confirmed_pnus=pnus, ambiguous_pnus=[])
    svc = _service(fake)

    async def go():
        job = await svc.submit(BatchInput(pnu_list=pnus))
        await svc.run(job.id)
        page1 = await svc.result(job.id, page=1, size=2)
        page2 = await svc.result(job.id, page=2, size=2)
        return page1, page2

    p1, p2 = _run(go())
    assert len(p1.items) <= 2
    assert p1.has_next is True
    assert len(p2.items) <= 2
    assert p2.has_next is False


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
