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
    - 없으면(동기 컨텍스트): 데몬 스레드에서 새 루프로 실행(엔진 크로스루프 실패는 graceful 흡수).
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
        # 실행 중 루프 없음(드문 동기 컨텍스트) — 데몬 스레드에서 실행.
        import threading

        def _run() -> None:
            try:
                asyncio.run(_guard())
            except Exception as e:  # noqa: BLE001
                logger.warning("성장뇌 적재 스레드 실패(%s): %s", label, str(e)[:200])

        threading.Thread(target=_run, name=f"growth-{label or 'ingest'}", daemon=True).start()
        return

    task = loop.create_task(_guard())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
