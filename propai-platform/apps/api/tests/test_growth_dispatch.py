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


def test_market_specialist_has_interpreter_wired():
    """★G6: market 도메인 SpecialistAgent 에 LLM 인터프리터 주입(과거 interpreter=None dead-path 해소).

    결정론 도메인(zoning/far)은 rule-only(interpreter=None)를 의도적으로 유지한다.
    """
    from app.services.agents.registry import get_specialist

    assert get_specialist("market")._interpreter is not None
    assert get_specialist("zoning")._interpreter is None


async def test_specialist_agent_default_ingester_uses_dispatch_memory_ingest_not_delay(monkeypatch):
    """★C5: 기본 ingester가 `.delay`(워커 부재 시 no-op)가 아니라 dispatch_memory_ingest(PR#173
    패턴 — 워커 없으면 in-process 실제 적재)를 쓰는지 확인한다."""
    from app.services.agents.specialist_agent import SpecialistAgent
    from app.tasks import memory_tasks

    seen: dict = {}
    done = asyncio.Event()

    async def _fake_ingest(payload: dict) -> bool:
        seen.update(payload)
        done.set()
        return True

    monkeypatch.setattr(memory_tasks, "_ingest_async", _fake_ingest)
    monkeypatch.setattr(memory_tasks, "_celery", None)  # 워커 부재

    def _tool(data):
        return {"findings": [{"check_id": "X", "status": "pass"}], "summary": {}}

    async def _rec(*, analysis_type, payload, **kw):
        return {"ok": True, "version": 1, "content_hash": "h",
                "contradictions": {"has_contradiction": False}}

    async def _prior(**kw):
        return None

    agent = SpecialistAgent(domain="far", task_type="effective_far", tool=_tool,
                            interpreter=None, recorder=_rec, prior_loader=_prior)
    await agent.run({"ok": True}, tenant_id="t", pnu="P1", project_id="proj1")
    # ★워커 없이도 in-process로 실제 적재가 발화돼야 한다(.delay였다면 no-op이라 아래가 timeout).
    await asyncio.wait_for(done.wait(), timeout=1.0)
    assert seen.get("domain") == "far"


# ── 동기 컨텍스트: 루프를 만들지 않는다 ────────────────────────────────────
# ★배경(2026-08-08 장애 후속): 이 모듈은 Celery 워커가 아니라 **API 프로세스 안**에서 돈다.
#   여기서 새 루프를 만들면 두 갈래 모두 결함이다 —
#     ① 맨 `asyncio.run` → 전역 엔진 풀에 죽은 루프에 묶인 연결을 남긴다(장애 기전 그대로)
#     ② `run_async_batch` → 정리는 하지만 **라이브 요청을 서빙 중인 전역 엔진**을 파기한다
#   그래서 러닝 루프가 없으면 **적재를 건너뛰고 드러낸다**. 아래 두 케이스가 그 계약을 잠근다.


def test_동기_컨텍스트에서는_적재를_실행하지_않고_드러낸다(caplog) -> None:
    """★러닝 루프가 없을 때 코루틴이 **실행되면 안 된다**.

    ★"코루틴이 닫혔는가"만 보면 부족하다 — 정상 완료된 코루틴도 프레임이 비어 실행 여부를
      구분하지 못한다. 그래서 **실행되면 켜지는 플래그**를 두고, 넉넉히 기다린 뒤에도
      꺼져 있음을 단언한다(종전 데몬 스레드 구현이라면 수 ms 안에 켜졌다).
    """
    import time

    ran: list[str] = []

    async def _work() -> None:
        ran.append("실행됨")

    with caplog.at_level("ERROR", logger=growth_dispatch.__name__):
        growth_dispatch.fire_and_forget(_work(), label="동기호출")

    time.sleep(0.3)  # 스레드/루프로 우회했다면 이 사이에 실행된다
    assert ran == [], "동기 컨텍스트에서 새 루프를 만들어 적재를 실행했다 — 전역 풀이 오염된다"

    messages = [r.getMessage() for r in caplog.records]
    assert any("동기호출" in m for m in messages), (
        f"건너뛴 사실을 조용히 묻었다 — best-effort 라도 드러나야 한다: {messages}"
    )


def test_동기_컨텍스트가_전역_엔진을_파기하지_않는다(monkeypatch) -> None:
    """★이 경로가 `run_async_batch` 로 되돌아가면 **라이브 HTTP 요청을 서빙 중인 전역 엔진**을
    다른 스레드에서 파기한다. 정리 함수가 **불렸는지**를 직접 잠근다(우회 형태 무관)."""
    import time

    from app.tasks import _async_batch

    disposed: list[int] = []

    async def _spy_dispose() -> int:
        disposed.append(1)
        return 0

    monkeypatch.setattr(_async_batch, "_dispose_engines", _spy_dispose)

    async def _work() -> None:
        return None

    growth_dispatch.fire_and_forget(_work(), label="동기호출2")
    time.sleep(0.3)  # 스레드로 우회했다면 이 사이에 정리가 돈다

    assert disposed == [], (
        "인프로세스 경로가 전역 엔진 정리를 호출했다 — Celery 용 처방을 API 프로세스에 오적용했다"
    )
