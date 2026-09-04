"""성장 뇌(MemoryHub) 비동기 적재 디스패치 — 워커 부재 시 in-process 백그라운드(핫패스 비차단).

★배경(정찰 G1~G3): ingest/specialist Celery 태스크는 prod 단일컨테이너에 워커가 없어 `.delay()` 가
  (a) 도달 불가 브로커에 동기 커넥션을 시도해 핫패스를 지연시키고, (b) 큐에 적재돼도 소비자가 없어
  실행이 0이었다 → 성장 뇌 자동 적재가 死. 워커 미배포가 기본 현실이므로, 기본 경로를 '현재 요청
  이벤트루프에 create_task 로 fire-and-forget' 으로 바꾼다:
  - 같은 루프를 쓰므로 DB 엔진 크로스루프 문제가 없다.
  - 적재 코루틴은 임베딩을 asyncio.to_thread 로 오프로드하므로 루프를 막지 않는다(핫패스 비차단).
  - 워커 없이도 실제 적재가 일어난다(死 경로 해소).
  GROWTH_CELERY_WORKER=1(명시) + celery 가용 시에만 `.delay()` 로 워커에 위임한다(미래 배포 대비).

★fire-and-forget 은 best-effort 다: 실패는 로그로 흡수하고 분석 본체를 절대 막지 않는다.

★**이 모듈은 이벤트루프를 만들지 않는다**(2026-08-08 장애 후속). 여기는 Celery 워커가 아니라
  **API 프로세스**이고, 전역 엔진 풀을 다른 루프에서 건드리면 라이브 요청이 다친다.
  러닝 루프가 없으면 적재를 **건너뛰고 드러낸다** — 사유와 올바른 처방은 `fire_and_forget` 참조.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)

# create_task 결과를 참조 보관(미보관 시 GC 로 백그라운드 태스크가 조기 취소될 수 있음).
_background_tasks: set[asyncio.Task] = set()


def worker_enabled() -> bool:
    """Celery 워커가 실제 배포됐다고 명시됐는가(GROWTH_CELERY_WORKER). 기본 False=인프로세스 적재."""
    return os.getenv("GROWTH_CELERY_WORKER", "").strip().lower() in ("1", "true", "yes")


def fire_and_forget(coro: Coroutine[Any, Any, Any], *, label: str = "") -> None:
    """성장 뇌 적재 코루틴을 핫패스 비차단으로 실행하고 결과는 버린다(best-effort).

    - 실행 중 이벤트루프가 있으면(일반 요청 경로): 그 루프에 create_task(같은 엔진·비차단).
    - 없으면(동기 컨텍스트): **아무 루프도 만들지 않고 시끄럽게 거절한다**(아래 참조).
    coro 는 '이미 생성된 코루틴'이어야 한다(호출부: fire_and_forget(_ingest_async(payload))).
    """
    async def _guard() -> None:
        try:
            await coro
        except Exception as e:  # noqa: BLE001 — 적재 실패는 분석을 막지 않음(정직 degrade)
            logger.warning("성장뇌 적재 백그라운드 실패(%s): %s", label, str(e)[:200])

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # ── 실행 중 루프 없음(동기 컨텍스트) ─────────────────────────────────────
        # ★여기서 **새 루프를 만들지 않는다**. 어떤 형태로 만들어도 결함이 된다:
        #   ① 맨 `asyncio.run` — 루프를 닫으며 **모듈 전역 엔진 풀에 죽은 루프에 묶인
        #      연결**을 남긴다. 다음 실행의 `pool_pre_ping` 이 그 연결로 `BEGIN` 을 보내다
        #      끊겨 서버에 `idle in transaction` 이 고착 = 2026-08-08 프로덕션 장애 그대로.
        #   ② `run_async_batch` — 정리는 하지만, 이 모듈은 Celery 워커가 아니라 **API
        #      프로세스 안**에서 돈다. `_dispose_engines()` 가 **라이브 HTTP 요청을 서빙 중인
        #      전역 엔진**을 다른 스레드·다른 루프에서 파기한다(Celery 용 처방의 오적용).
        #
        # ★일회용 엔진(`deliberation-review` INC-13 방식)은 **이 자리에서 불가능**하다:
        #   `coro` 는 호출부가 **이미 만들어 넘긴 코루틴**이고, 그 본문은 모듈 전역
        #   `async_session_factory`(memory_tasks)·전문가 에이전트 내부 세션을 각각
        #   자기 모듈에서 직접 해석한다. 엔진을 가르려면 그 소비처 전부의 계약을 바꿔야 한다.
        #   실제 동기 호출부가 생기면 그때 할 일은 둘 중 하나다 —
        #   (a) 세션 팩토리를 주입 가능하게 바꾼 뒤 일회용 엔진, 또는
        #   (b) 앱 이벤트루프 핸들을 잡아 `asyncio.run_coroutine_threadsafe` 로 **같은 루프**에 태움.
        #
        # ★현재 호출부 3곳은 전부 async 라 이 분기는 도달하지 않는다(실측:
        #   `specialist_agent.run`·`expert_panel_service.analyze`·
        #   `comprehensive_analysis_service.analyze`). 적재는 계약상 best-effort 이므로,
        #   조용히 새는 것보다 **건너뛰고 드러내는 쪽**이 옳다.
        coro.close()  # 미-await 코루틴 경고를 남기지 않는다(자원도 즉시 반납).
        logger.error(
            # ★변이 도구가 아래 **이어지는 두 줄의 문구 변경**을 생존으로 보고한다
            #   (설명 가능한 생존): 첫 줄은 label 이 들어가 `건너뛴 사실을 드러낸다` 케이스가
            #   잡지만, 뒤 두 줄은 **사람에게 주는 안내문**이라 어떤 동작도 좌우하지 않는다.
            #   여기에 문구 일치를 박으면 상수를 복창하는 동어반복 락이 되므로 두지 않는다.
            "성장뇌 적재를 건너뛴다(%s) — 동기 컨텍스트에서 호출됐다."
            " 이 경로는 새 루프를 만들지 않는다(전역 커넥션 풀 오염 방지)."
            " 호출부를 async 로 두거나, 주입 가능한 세션 팩토리로 일회용 엔진을 쓰라.",
            label or "ingest",
        )
        return

    task = loop.create_task(_guard())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
