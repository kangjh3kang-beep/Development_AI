"""F-Parcel 대량 다필지 배치 라우터.

엔드포인트:
- POST ""             : 배치 제출(멱등) → {job_id, state, snapshot_id}
- GET  "/{job_id}"    : 폴링(페이지네이션 BatchResult)
- POST "/{job_id}/cancel" : 취소

실행 경로(둘 다 지원, 가용한 것 사용):
- Celery 워커가 떠 있으면 parcel_batch 큐로 enqueue.
- 워커 미가동 환경에서도 동작하도록 FastAPI BackgroundTasks 로 인프로세스 실행을 함께 시도.

main.py 배선은 통합자가 한다(여기서는 router 만 export).
"""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.foundation.parcel.batch.batch_service import BatchService
from app.foundation.parcel.batch.job_store import DbJobStore
from app.foundation.parcel.contracts.batch import BatchInput, BatchResult
from app.services.auth.auth_service import get_current_user

router = APIRouter(
    prefix="/api/v1/parcels/batch",
    dependencies=[Depends(get_current_user)],
    tags=["대량 다필지 배치"],
)


def _service() -> BatchService:
    """DB 기반 BatchService 를 생성한다(라우터용)."""
    return BatchService(store=DbJobStore())


async def _run_inprocess(job_id: str) -> None:
    """인프로세스 백그라운드 실행(워커 미가동 폴백)."""
    try:
        await _service().run(job_id)
    except Exception:  # noqa: BLE001 - 백그라운드 실패는 폴링 상태로 노출됨
        pass


def _enqueue_celery(job_id: str) -> bool:
    """Celery 큐(parcel_batch)로 작업을 보낸다. 워커 미가동이면 False."""
    try:
        from app.tasks.parcel_batch_task import run_batch

        # Celery 데코레이터가 적용된 경우에만 delay 가 존재한다.
        if hasattr(run_batch, "delay"):
            run_batch.delay(job_id)
            return True
    except Exception:  # noqa: BLE001 - celery 미설치/미가동
        return False
    return False


@router.post("")
async def submit_batch(
    inp: BatchInput,
    background: BackgroundTasks,
    snapshot_id: Optional[str] = None,
) -> dict:
    """배치 제출(멱등). 제출 후 Celery enqueue + 인프로세스 백그라운드 실행을 함께 시도."""
    service = _service()
    job = await service.submit(inp, snapshot_id=snapshot_id)

    # 가용한 실행 경로를 모두 시도(둘 다 멱등이라 중복 처리해도 결과는 동일).
    enqueued = _enqueue_celery(job.id)
    if not enqueued:
        background.add_task(_run_inprocess, job.id)

    return {
        "job_id": job.id,
        "state": job.state.value,
        "snapshot_id": job.snapshot_id,
    }


@router.get("/{job_id}")
async def poll_batch(job_id: str, page: int = 1, size: int = 500) -> BatchResult:
    """배치 결과 폴링(페이지네이션)."""
    service = _service()
    try:
        return await service.result(job_id, page=page, size=size)
    except KeyError:
        raise HTTPException(status_code=404, detail="배치 잡을 찾을 수 없습니다.")


@router.post("/{job_id}/cancel")
async def cancel_batch(job_id: str) -> dict:
    """배치 취소."""
    service = _service()
    try:
        job = await service.cancel(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="배치 잡을 찾을 수 없습니다.")
    return {"job_id": job.id, "state": job.state.value}