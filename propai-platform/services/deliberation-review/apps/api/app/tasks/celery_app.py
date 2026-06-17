"""Phase 0 — Celery 앱(redis 브로커). 공급측 비동기 페이즈(R2/L4/L5 잡)에서 사용."""
from __future__ import annotations

from celery import Celery

from app.settings import settings

celery_app = Celery(
    "propai_review", broker=settings.redis_url, backend=settings.redis_url,
    # worker가 태스크를 등록하도록 명시 include(autodiscover 미사용).
    include=[
        "app.tasks.analysis_tasks", "app.tasks.supply_tasks",
        "app.tasks.verify_tasks", "app.tasks.reconcile_tasks",
    ],
)
celery_app.conf.update(
    task_track_started=True, task_serializer="json", result_serializer="json",
    # dev(브로커 없음)는 eager 동기 폴백. 운영은 CELERY_TASK_ALWAYS_EAGER=false + worker.
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=True,
)
