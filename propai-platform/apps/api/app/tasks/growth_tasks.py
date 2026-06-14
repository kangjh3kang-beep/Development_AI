"""자가성장 엔진 — 텔레메트리 적재 Celery 태스크(설계서 §4).

⚠️ Phase 1 정본은 main.py 의 인프로세스 flush 루프(_growth_flush_loop)다.
    같은 프로세스의 capture_service in-memory deque 를 드레인해 platform_events
    로 배치 INSERT 한다.

    이 Celery 경로는 별도 Celery 워커 프로세스에서 도는데, capture_service 의
    큐가 프로세스-로컬(모듈 전역 deque)이라 API 프로세스가 쌓은 이벤트가
    워커에는 보이지 않는다 → 현재 Celery 경로는 사실상 무동작이다.
    향후 큐를 Redis 등 공유 큐로 전환하면 이 태스크가 실질 활성화된다.
    (코드는 그대로 두되 오해를 막기 위해 역할을 명시.)

flush_growth_events: in-memory 큐(capture_service)의 이벤트를 platform_events
로 배치 INSERT 한다. Celery Beat 가 5초 주기로 호출(celery_app.py 등록).

Celery 워커는 동기 컨텍스트이므로 asyncio.run 으로 async flush_batch 를 구동한다.
DB 는 새 AsyncSession 1개를 열어 사용(요청 세션과 무관). best-effort: 어떤
예외도 워커를 죽이지 않는다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _get_celery_app():
    """Celery 앱을 지연 임포트한다(rate_tasks 선례)."""
    try:
        from app.tasks.celery_app import app
        return app
    except (ImportError, RuntimeError):
        return None


async def _flush_async(limit: int = 500) -> int:
    """새 AsyncSession 으로 큐를 platform_events 에 배치 INSERT 한다."""
    from apps.api.database.session import AsyncSessionLocal
    from app.services.growth import capture_service

    total = 0
    async with AsyncSessionLocal() as session:
        # 한 사이클에 누적분을 비우되, 단일 트랜잭션 폭주를 막기 위해 청크 반복.
        for _ in range(20):  # 최대 20청크/사이클(= limit*20 건)
            n = await capture_service.flush_batch(session, limit=limit)
            total += n
            if n < limit:
                break
    return total


def flush_growth_events() -> dict:
    """큐 → platform_events 배치 적재. Beat 5초 주기.

    반환: {"flushed": N}. 동기 진입점(Celery 워커)에서 asyncio.run 으로 구동.
    """
    import asyncio

    try:
        flushed = asyncio.run(_flush_async())
    except RuntimeError:
        # 이미 이벤트 루프가 도는 환경(인프로세스 폴백 등) — 새 루프로 격리.
        loop = asyncio.new_event_loop()
        try:
            flushed = loop.run_until_complete(_flush_async())
        finally:
            loop.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("flush_growth_events 실패: %s", str(e)[:160])
        return {"flushed": 0, "error": str(e)[:160]}

    if flushed:
        logger.info("growth 이벤트 적재 %d건", flushed)
    return {"flushed": flushed}


# ── 분석 배치(Phase 2, 설계서 §5.1) ─────────────────────────────────────────
# flush 와 달리 analyze 는 DB(platform_events)를 읽어 인사이트를 산출하므로
# 별도 Celery 워커에서도 정상 동작한다(프로세스-로컬 큐에 의존하지 않음).

async def _analyze_async(window_hours: int = 1) -> int:
    """직전 window_hours 시간을 분석해 platform_insights 를 생성한다."""
    from apps.api.database.session import AsyncSessionLocal
    from app.services.growth import analyzer

    w0, w1 = analyzer.default_window(hours=window_hours)
    async with AsyncSessionLocal() as session:
        insights = await analyzer.analyze_window(session, w0, w1)
    return len(insights)


def analyze_growth(window_hours: int = 1) -> dict:
    """platform_events → platform_insights 분석 배치. Beat hourly/daily 호출.

    반환: {"insights": N}. 동기 진입점(Celery 워커)에서 asyncio.run 으로 구동.
    best-effort: 어떤 예외도 워커를 죽이지 않는다.
    """
    import asyncio

    try:
        n = asyncio.run(_analyze_async(window_hours))
    except RuntimeError:
        # 이미 이벤트 루프가 도는 환경 — 새 루프로 격리(flush 선례 동일).
        loop = asyncio.new_event_loop()
        try:
            n = loop.run_until_complete(_analyze_async(window_hours))
        finally:
            loop.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("analyze_growth 실패: %s", str(e)[:160])
        return {"insights": 0, "error": str(e)[:160]}

    if n:
        logger.info("growth 인사이트 %d건 생성", n)
    return {"insights": n}


# Celery 태스크 등록(앱이 있을 때만; 미설치 환경에서도 함수는 직접 호출 가능).
_celery = _get_celery_app()
if _celery is not None:
    flush_growth_events = _celery.task(
        name="app.tasks.growth_tasks.flush_growth_events"
    )(flush_growth_events)
    analyze_growth = _celery.task(
        name="app.tasks.growth_tasks.analyze_growth"
    )(analyze_growth)
