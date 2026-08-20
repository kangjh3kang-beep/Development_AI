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


async def _닫힘락_전용_코루틴() -> None:
    """★이 락 **전용** 코루틴. 이름을 고유하게 둔 이유는 아래 락이 경고를
    **자기 것인지 이름으로 가려내기** 때문이다. 이 파일의 다른 테스트가 쓰는
    `_work` 를 재사용하면 남의 것과 이름이 겹쳐 다시 못 가린다."""
    return None


def _닫힘락_내_경고만(caught: list) -> list:
    """`caught` 에서 **이 락이 만든 코루틴**의 미-await 경고만 골라낸다."""
    return [
        w
        for w in caught
        if "never awaited" in str(w.message) and "_닫힘락_전용_코루틴" in str(w.message)
    ]


def test_건너뛴_코루틴을_닫아_미await_경고를_남기지_않는다() -> None:
    """★적재를 건너뛰기만 하고 코루틴을 **버리면** 파이썬이 GC 시점에
    `coroutine ... was never awaited` 를 찍고 그 코루틴의 자원도 늦게 반납된다.

    ★이 락은 **도구가 만들지 못한 변이**를 막는다: `scripts/mutate_changed.py` 는 이 파일에서
      로그 문자열 3건만 변이했고 `coro.close()` 는 건드리지 않았다. 직접 주입해 보니
      **SURVIVED**(경고만 4→6으로 늘고 아무 케이스도 실패하지 않았다) — 그래서 여기 잠근다.

    ★★2026-08-20 — **이 락이 CI 에서 무작위로 빨개졌다**(#714·#712 가 이걸로 막혔다).
      원인은 이 락이 잠그려는 결함이 아니라 **락 자신**이었다: `gc.collect()` 는 이 테스트가
      만든 코루틴만 수거하지 않는다. **다른 테스트가 남긴 쓰레기까지 같이 수거**하고,
      그때 나온 경고가 이 창(`catch_warnings`)에 함께 잡혔다. CI 가 실제로 잡은 것은
      `AsyncMockMixin._execute_mock_call` — 이 테스트는 `AsyncMock` 을 **쓰지도 않는다**.
      병렬 실행(`-n auto`)에서 이웃이 누가 되느냐에 따라 발화 여부가 갈렸다.
      → 처방은 두 겹이다. ①창에 들어가기 **전에** 한 번 수거해 남의 쓰레기를 창 밖에서
      털어내고, ②남은 경고도 **이름으로 자기 것만** 고른다.
    """
    import gc
    import warnings

    # ① 남의 쓰레기를 **창 밖에서** 턴다. 이걸 안 하면 아래 `gc.collect()` 가
    #    이웃 테스트의 미수거 코루틴을 주워 이 락이 남의 일로 실패한다.
    #    ★변이 실측(2026-08-20): 이 줄을 지워도 **세 케이스 모두 통과한다(SURVIVED)**.
    #      ②의 이름 필터가 이미 남의 것을 걸러내기 때문이다 — 즉 **의도된 이중 가드**이지
    #      무잠금이 아니다. 필터 쪽이 무너졌을 때를 대비한 두 번째 겹으로 남긴다.
    gc.collect()

    coro = _닫힘락_전용_코루틴()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        growth_dispatch.fire_and_forget(coro, label="동기호출3")
        del coro
        gc.collect()  # 참조가 끊긴 코루틴을 즉시 수거해 경고를 결정론적으로 만든다

    never_awaited = _닫힘락_내_경고만(caught)
    assert not never_awaited, (
        "건너뛴 코루틴을 닫지 않았다 — 미-await 경고가 남고 자원 반납이 늦어진다: "
        f"{[str(w.message) for w in never_awaited]}"
    )


def test_닫힘락의_경고필터가_살아있다_양성대조군() -> None:
    """★위 락은 경고를 **이름으로 좁혀** 본다. 좁히다 보면 *아무것도 못 잡는 필터*가
    되기 쉽고, 그러면 `coro.close()` 를 지워도 초록인 **공허한 락**이 된다.

    그래서 여기서 **일부러 닫지 않은 코루틴**을 버려 필터가 그것을 잡는지 확인한다.
    이 케이스가 깨지면 위 락은 무효다 — 위 락의 초록을 믿기 전에 이걸 본다.
    """
    import gc
    import warnings

    gc.collect()  # 위와 같은 이유로 남의 쓰레기를 먼저 턴다

    with warnings.catch_warnings(record=True) as control:
        warnings.simplefilter("always")
        버려진_코루틴 = _닫힘락_전용_코루틴()  # ★close() 하지 않고 버린다
        del 버려진_코루틴
        gc.collect()

    assert _닫힘락_내_경고만(control), (
        "양성 대조군이 비었다 — 필터가 **자기 코루틴조차** 못 잡는다. "
        "즉 위 닫힘 락은 무엇을 지워도 초록인 공허한 락이다"
    )


def test_이웃이_남긴_쓰레기로는_닫힘락이_깨지지_않는다() -> None:
    """★이 락이 CI 에서 **무작위로 빨개진 그 상황**을 재현해서 잠근다(#714·#712 가 막혔다).

    재현의 핵심은 *어떻게 남의 쓰레기를 GC 시점까지 살려 두느냐* 다.
    `AsyncMock()` 을 그냥 버리면 **참조계수로 즉시** 수거되어 경고가 남의 테스트 안에서
    터지고 끝난다(1차 재현이 이래서 실패했다 — 원본 단언조차 통과했다).
    **순환 참조에 가두면** 참조계수로 죽지 않아 **GC 사이클까지 살아남고**, 그 뒤
    `gc.collect()` 를 부르는 쪽이 남의 쓰레기를 뒤집어쓴다. 그게 CI 에서 벌어진 일이다.

    ★대조 실증(2026-08-20): 이 순서에서 **필터 없는 원본 단언은 FAILED**
      (`coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` — CI 와 같은 메시지),
      **이름으로 좁힌 지금 필터는 PASSED**.
    """
    import gc
    import warnings
    from unittest.mock import AsyncMock

    # ── 이웃이 남기는 쓰레기를 만든다(순환에 가둬 GC 사이클까지 살린다) ──
    mock = AsyncMock()
    남의_코루틴 = mock()  # ★await 하지 않는다
    순환: dict = {}
    순환["self"] = 순환
    순환["coro"] = 남의_코루틴
    del mock, 남의_코루틴, 순환  # 바깥 참조만 끊는다 — 수거는 GC 로 미뤄진다

    # ── 닫힘락과 **같은 절차**를 밟는다 ──
    coro = _닫힘락_전용_코루틴()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        growth_dispatch.fire_and_forget(coro, label="이웃쓰레기재현")
        del coro
        gc.collect()  # ★여기서 남의 쓰레기도 함께 수거된다

    남의_것 = [w for w in caught if "AsyncMock" in str(w.message)]
    내_것 = _닫힘락_내_경고만(caught)

    # 전제 확인 — 남의 쓰레기가 실제로 이 창에 잡혔어야 재현이 성립한다.
    # (안 잡혔다면 이 케이스는 아무것도 검증하지 않는 **공허한 초록**이다)
    assert 남의_것, (
        "재현 실패 — 남의 쓰레기가 이 창에 잡히지 않았다. 순환 참조가 깨졌거나 "
        "GC 동작이 바뀌었다. 이 상태의 초록은 아무것도 보증하지 않는다"
    )
    assert not 내_것, (
        "남의 쓰레기를 자기 것으로 주웠다 — 필터가 이름을 확인하지 않는다: "
        f"{[str(w.message) for w in 내_것]}"
    )
