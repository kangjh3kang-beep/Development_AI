"""v61 Celery 앱 설정 — 법정요율/표준단가/연금 자동갱신 스케줄.

beat_schedule:
  - daily  01:00  법정요율 변동 감지
  - weekly 월 02:00  표준단가 갱신 확인
  - monthly 1일 03:00  국민연금 단계인상 체크
"""

from __future__ import annotations

import os

try:
    from celery import Celery
    from celery.schedules import crontab
except ImportError:  # pragma: no cover
    Celery = None  # type: ignore[assignment,misc]
    crontab = None  # type: ignore[assignment,misc]

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")


def _create_app() -> "Celery":
    """Celery 앱 인스턴스를 생성한다."""
    if Celery is None:
        raise RuntimeError("celery 패키지가 설치되지 않았습니다.")

    _app = Celery(
        "propai",
        broker=BROKER_URL,
        backend=RESULT_BACKEND,
    )

    _app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Seoul",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
    )

    _app.conf.beat_schedule = {
        "check-legal-rates-daily": {
            "task": "app.tasks.rate_tasks.check_legal_rates",
            "schedule": crontab(hour=1, minute=0),
            "options": {"queue": "rates"},
        },
        "check-standard-prices-weekly": {
            "task": "app.tasks.rate_tasks.check_standard_prices",
            "schedule": crontab(hour=2, minute=0, day_of_week=1),
            "options": {"queue": "rates"},
        },
        "check-pension-increase-monthly": {
            "task": "app.tasks.rate_tasks.check_pension_increase",
            "schedule": crontab(hour=3, minute=0, day_of_month=1),
            "options": {"queue": "rates"},
        },
        "sync-onbid-auctions-daily": {
            "task": "app.tasks.auction_sync_task.sync_onbid_auctions",
            "schedule": crontab(hour=4, minute=0),
            "options": {"queue": "auction"},
        },
        # 자가성장 엔진 — 텔레메트리 큐 → platform_events 배치 적재(5초 주기).
        # ⚠️ Phase 1 정본은 main.py 인프로세스 flush 루프(같은 프로세스 deque 드레인)다.
        #    capture_service 큐는 프로세스-로컬이라 별도 Celery 워커에는 API 가 쌓은
        #    이벤트가 보이지 않아 이 스케줄은 현재 무동작이다. 향후 Redis 공유큐 전환
        #    시 활성화된다(스케줄은 등록만 유지).
        "flush-growth-events": {
            "task": "app.tasks.growth_tasks.flush_growth_events",
            "schedule": 5.0,  # 5초 주기(초 단위 float)
            "options": {"queue": "growth"},
        },
    }

    _app.autodiscover_tasks(["app.tasks"])
    return _app


# 모듈 레벨 앱 (celery가 설치된 경우에만)
app: "Celery | None" = None
if Celery is not None:
    app = _create_app()


# ── 메타 정보 (테스트용) ──

BEAT_SCHEDULE_NAMES = [
    "check-legal-rates-daily",
    "check-standard-prices-weekly",
    "check-pension-increase-monthly",
    "sync-onbid-auctions-daily",
    "flush-growth-events",
]

TASK_NAMES = [
    "app.tasks.rate_tasks.check_legal_rates",
    "app.tasks.rate_tasks.check_standard_prices",
    "app.tasks.rate_tasks.check_pension_increase",
    "app.tasks.cost_tasks.recalculate_project_cost",
    "app.tasks.auction_sync_task.sync_onbid_auctions",
    "app.tasks.growth_tasks.flush_growth_events",
]
