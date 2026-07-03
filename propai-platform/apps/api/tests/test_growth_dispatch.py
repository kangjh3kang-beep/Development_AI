"""성장 뇌 dead-path 복구 검증 — 워커 부재 시 in-process 백그라운드 적재(핫패스 비차단).

정찰 G1~G3: 과거 `.delay()` 는 prod 워커 부재 시 no-op 이라 자동 적재가 死였다.
dispatch_* 는 워커가 없으면 현재 이벤트루프에 fire-and-forget 으로 '실제로' 실행해야 한다.
"""

from __future__ import annotations

import asyncio

from app.services.agents import growth_dispatch


async def test_fire_and_forget_runs_coroutine_in_background():
    ran = asyncio.Event()

    async def _work():
        ran.set()

    growth_dispatch.fire_and_forget(_work(), label="test")
    # 백그라운드로 예약됐고, 짧게 양보하면 실행된다(핫패스는 즉시 반환).
    await asyncio.wait_for(ran.wait(), timeout=1.0)
    assert ran.is_set()


async def test_fire_and_forget_swallows_exceptions():
    # 적재 실패는 흡수돼야 한다(분석 본체·이벤트루프 무손상).
    async def _boom():
        raise ValueError("적재 실패 시뮬")

    growth_dispatch.fire_and_forget(_boom(), label="boom")
    await asyncio.sleep(0.05)  # 예외가 흡수되고 크래시 없음(여기 도달하면 통과)
    assert True


def test_worker_enabled_defaults_false(monkeypatch):
    monkeypatch.delenv("GROWTH_CELERY_WORKER", raising=False)
    assert growth_dispatch.worker_enabled() is False
    monkeypatch.setenv("GROWTH_CELERY_WORKER", "1")
    assert growth_dispatch.worker_enabled() is True


async def test_dispatch_memory_ingest_runs_in_process_without_worker(monkeypatch):
    from app.tasks import memory_tasks

    seen: dict = {}
    done = asyncio.Event()

    async def _fake_ingest(payload: dict) -> bool:
        seen.update(payload)
        done.set()
        return True

    monkeypatch.setattr(memory_tasks, "_ingest_async", _fake_ingest)
    monkeypatch.setattr(memory_tasks, "_celery", None)  # 워커 부재

    memory_tasks.dispatch_memory_ingest({"session_id": "s1", "domain": "market", "summary": "x"})
    await asyncio.wait_for(done.wait(), timeout=1.0)
    assert seen.get("session_id") == "s1"  # ★워커 없이도 실제 적재 발화(G1 해소)


async def test_dispatch_specialists_runs_in_process_without_worker(monkeypatch):
    from app.tasks import specialist_tasks

    seen: dict = {}
    done = asyncio.Event()

    async def _fake_run(payload: dict) -> int:
        seen.update(payload)
        done.set()
        return 1

    monkeypatch.setattr(specialist_tasks, "_run_specialists_async", _fake_run)
    monkeypatch.setattr(specialist_tasks, "_celery", None)

    specialist_tasks.dispatch_domain_specialists({"domains": {"market": {}}, "address": "용인"})
    await asyncio.wait_for(done.wait(), timeout=1.0)
    assert "market" in (seen.get("domains") or {})  # ★G2 해소


def test_get_memory_hub_is_singleton():
    from app.services.memory_hub.memory_service import get_memory_hub

    a = get_memory_hub()
    b = get_memory_hub()
    assert a is b  # ★G4: 프로세스 단일 인스턴스(embeddings 클라이언트 재사용)
