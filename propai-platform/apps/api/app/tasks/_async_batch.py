"""Celery 동기 태스크에서 async 코드를 돌릴 때 **커넥션을 남기지 않고** 끝내는 공용 진입점.

## 왜 이게 필요한가 — 2026-08-08 프로덕션 장애의 근본

Celery 태스크는 동기 함수라 `asyncio.run(...)` 으로 async 배치를 돌린다. 그런데
`asyncio.run` 은 **끝나면 이벤트 루프를 닫는다**. 반면 SQLAlchemy 비동기 엔진과 그
**커넥션 풀은 모듈 전역**이다(`app/core/database.py`·`database/session.py`).

그래서 배치가 끝나면 풀에는 **이미 닫힌 루프에 묶인 연결**이 남는다. 그 연결은
서버(Postgres) 쪽에서 살아 있는데, 트랜잭션을 되돌릴 주체(루프)가 사라졌다.
SQLAlchemy 는 첫 쿼리 직전 `BEGIN` 을 보내므로, 서버에는 **`BEGIN;` 만 도달하고
ROLLBACK 은 영영 오지 않는** 연결이 남는다 = `idle in transaction`.

**실제 피해**: 매일 1건씩 쌓여 **16~17일 만에 Supabase 트랜잭션 풀러(6543) 슬롯을 고갈**시켰고,
DB 를 쓰는 모든 요청이 60초 타임아웃으로 죽었다(로그인 불가). 세션 포트(5432)는 멀쩡했고
`pg_stat_activity` 의 고착 16건은 **전부 마지막 쿼리가 `BEGIN;`** 이었다.

★이 저장소는 이 현상을 **이미 알고 있었다** — `tests/integration/test_growth_loop_e2e.py` 가
`engine.dispose()` 를 부르며 "교차-이벤트루프 풀 바인딩 초기화"라고 적어 뒀다.
테스트에서만 처리하고 **배치 경로엔 적용하지 않은 것**이 이 사고다.

## 처방

루프가 닫히기 **전에**, 그 루프 안에서 엔진을 `dispose()` 한다. dispose 는 풀의 연결을
정상 종료(=ROLLBACK 후 close)하므로 서버에 `idle in transaction` 이 남지 않는다.

★태스크마다 손으로 `dispose` 를 넣지 않는다 — 6개 파일이 같은 결함을 공유했으므로
**한 곳을 고치면 전역이 따라오도록** 이 진입점으로 모은다.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


# 이 저장소가 만드는 비동기 엔진 전부(모듈, 속성명).
# ★새 엔진을 만들면 여기 추가한다 — 빠지면 그 엔진의 연결만 조용히 새어 나간다.
_ENGINES: tuple[tuple[str, str], ...] = (
    ("app.core.database", "engine"),
    ("apps.api.database.session", "engine"),
    ("apps.api.database.session", "timescale_engine"),
)


async def _dispose_engines() -> int:
    """현재 루프에 묶인 커넥션 풀을 정리하고, 정리한 엔진 수를 돌려준다."""
    disposed = 0
    for module_name, attr in _ENGINES:
        try:
            module = importlib.import_module(module_name)
        except Exception:  # noqa: BLE001 — 해당 엔진이 없는 배포 형태도 있다
            continue
        engine = getattr(module, attr, None)
        if engine is None:
            continue
        try:
            await engine.dispose()
            disposed += 1
        except Exception:  # noqa: BLE001 — 정리 실패가 배치 결과를 덮지 않게 한다
            logger.warning("engine dispose 실패: %s.%s", module_name, attr, exc_info=True)
    return disposed


def run_async_batch[T](factory: Callable[[], Awaitable[T]]) -> T:
    """async 배치를 돌리고, **루프를 닫기 전에** 커넥션 풀을 정리한다.

    `factory` 는 코루틴을 만드는 함수다(코루틴 객체가 아니라). 재시도 경로에서 코루틴을
    두 번 await 하는 사고를 막기 위해 매번 새로 만들게 한다.
    """

    async def _runner() -> T:
        try:
            return await factory()
        finally:
            # ★배치가 실패해도 정리는 반드시 한다 — 예외 경로가 오히려 더 잘 샌다.
            await _dispose_engines()

    try:
        return asyncio.run(_runner())
    except RuntimeError:
        # 이미 루프가 도는 환경(일부 워커·테스트) — 격리된 새 루프로 실행한다.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_runner())
        finally:
            loop.close()
