"""F-Parcel 배치 Celery 태스크.

run_batch(job_id): 동기 래퍼로 asyncio.run(BatchService(DbJobStore...).run(job_id)).
celery 미설치/미가동 시에도 import 가 깨지지 않도록 안전 폴백(try/except).
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def _get_celery_app():
    """Celery 앱을 지연 임포트한다(없으면 None)."""
    try:
        from app.tasks.celery_app import app

        return app
    except (ImportError, RuntimeError):
        return None


def run_batch(job_id: str) -> dict:
    """배치 잡을 동기 컨텍스트에서 실행한다(Celery 워커 진입점).

    내부적으로 async BatchService.run 을 asyncio.run 으로 구동한다.
    """
    from app.foundation.parcel.batch.batch_service import BatchService
    from app.foundation.parcel.batch.job_store import DbJobStore

    logger.info("배치 잡 실행 시작: %s", job_id)

    async def _go() -> dict:
        service = BatchService(store=DbJobStore())
        record = await service.run(job_id)
        return {
            "job_id": job_id,
            "state": record.job.state.value,
            "completeness": record.job.completeness.value,
            "counts": record.job.counts.model_dump(),
        }

    result = asyncio.run(_go())
    logger.info("배치 잡 실행 완료: %s (%s)", job_id, result.get("state"))
    return result


# ── Celery 데코레이터 적용(설치/가동된 경우에만) ──
_celery_app = _get_celery_app()
if _celery_app is not None:
    run_batch = _celery_app.task(
        name="app.tasks.parcel_batch_task.run_batch",
        queue="parcel_batch",
        bind=False,
        max_retries=2,
        default_retry_delay=30,
    )(run_batch)
