"""v61 Celery 앱 설정 — 법정요율/표준단가/연금 자동갱신 스케줄.

beat_schedule:
  - daily  01:00  법정요율 변동 감지
  - weekly 월 02:00  표준단가 갱신 확인
  - monthly 1일 03:00  국민연금 단계인상 체크
"""

from __future__ import annotations

from importlib import import_module
import os

try:
    from celery import Celery
    from celery.schedules import crontab
except ImportError:  # pragma: no cover
    Celery = None  # type: ignore[assignment,misc]
    crontab = None  # type: ignore[assignment,misc]

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

OPERATIONAL_QUEUES = [
    "parcel_batch",
    "celery",
    "rates",
    "auction",
    "growth",
]

TASK_MODULES = [
    "app.tasks.rate_tasks",
    "app.tasks.cost_tasks",
    "app.tasks.auction_sync_task",
    "app.tasks.growth_tasks",
    "app.tasks.growth_pr_task",
    "app.tasks.growth_learning_task",
    "app.tasks.parcel_batch_task",
    "app.tasks.memory_tasks",
    "app.tasks.specialist_tasks",
]


def _create_app() -> Celery:
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
        broker_connection_retry_on_startup=True,
        imports=TASK_MODULES,
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
        # 자가성장 엔진 — 분석 배치(Phase 2, §5.1). flush 와 달리 DB(platform_events)
        # 를 읽어 인사이트를 산출하므로 별도 Celery 워커에서도 정상 동작한다
        # (프로세스-로컬 큐 비의존). 인프로세스 폴백이 도는 환경에서는 main.py 의
        # 인프로세스 루프가 동일 함수를 주기 호출하도록 보강할 수 있다.
        # hourly: error_cluster/fallback_rate/quality_drop(직전 1시간 윈도우).
        "analyze-growth-hourly": {
            "task": "app.tasks.growth_tasks.analyze_growth",
            "schedule": crontab(minute=5),  # 매시 5분
            "kwargs": {"window_hours": 1},
            "options": {"queue": "growth"},
        },
        # daily: 일 단위 추세(usage/funnel/latency baseline) 누적 — 24시간 윈도우.
        "analyze-growth-daily": {
            "task": "app.tasks.growth_tasks.analyze_growth",
            "schedule": crontab(hour=2, minute=30),  # 매일 02:30
            "kwargs": {"window_hours": 24},
            "options": {"queue": "growth"},
        },
        # 자가치유 평가(Phase 3, §6.1) — open 인사이트/이벤트 → heal 액션(무인 L0).
        # analyze 와 동일하게 DB 를 읽으므로 별도 Celery 워커에서도 정상 동작.
        # 10분 주기: 가드(시간당 캡·쿨다운)가 빈번 실행을 자체 차단하므로 안전.
        "evaluate-healing": {
            "task": "app.tasks.growth_tasks.evaluate_healing",
            "schedule": crontab(minute="*/10"),  # 10분마다
            "options": {"queue": "growth"},
        },
        # L1 자가수정 평가(Phase 4, §6.2) — open 인사이트/이벤트 → 임계보정·피처
        # 토글·프롬프트 A/B 채택(저위험 무인, 화이트리스트/후보군·±20% 상한·롤백·감사).
        # analyze(매시5분) 직후 효과를 보도록 15분 주기. 가드가 빈번 실행을 자체 차단.
        "evaluate-correction": {
            "task": "app.tasks.growth_tasks.evaluate_correction",
            "schedule": crontab(minute="*/15"),  # 15분마다
            "options": {"queue": "growth"},
        },
        # L2 개선제안 생성 + Draft PR봇(Phase 4, §6.3) — propose_pr critical 인사이트 →
        # 진단+패치 제안 아티팩트(코드 자동변경 없음). GH_TOKEN 있을 때만 Draft PR(없으면
        # 아티팩트만). 일배치(analyze-daily 02:30) 후속 03:00. 절대 자동 머지/배포 금지.
        "evaluate-improvement-daily": {
            "task": "app.tasks.growth_tasks.evaluate_improvement",
            "schedule": crontab(hour=3, minute=0),  # 매일 03:00
            "options": {"queue": "growth"},
        },
        # L3 자가학습 주간 배치(Phase 5, §6.4) — few-shot 큐레이션(candidate 등록)
        # + 파인튜닝셋 생성(생성까지만) + down율 개선대상 프롬프트 후보 A/B 등록.
        # ★파인튜닝 잡 자동실행 금지·few-shot 자동활성 금지·프롬프트 자동채택 금지.
        # 일요일 04:00(개선배치 03:00 후속). 주 1회로 LLM 비용·부하 가드.
        "run-learning-weekly": {
            "task": "app.tasks.growth_learning_task.run_learning",
            "schedule": crontab(hour=4, minute=0, day_of_week=0),  # 일요일 04:00
            "options": {"queue": "growth"},
        },
    }

    return _app


def _import_task_modules() -> None:
    """앱 생성 후 태스크 모듈을 명시 로드해 워커 registry 단절을 막는다."""
    for module_name in TASK_MODULES:
        import_module(module_name)


# 모듈 레벨 앱 (celery가 설치된 경우에만)
app: Celery | None = None
if Celery is not None:
    app = _create_app()
    _import_task_modules()


# ── 메타 정보 (테스트용) ──

BEAT_SCHEDULE_NAMES = [
    "check-legal-rates-daily",
    "check-standard-prices-weekly",
    "check-pension-increase-monthly",
    "sync-onbid-auctions-daily",
    "flush-growth-events",
    "analyze-growth-hourly",
    "analyze-growth-daily",
    "evaluate-healing",
    "evaluate-correction",
    "evaluate-improvement-daily",
    "run-learning-weekly",
]

TASK_NAMES = [
    "app.tasks.rate_tasks.check_legal_rates",
    "app.tasks.rate_tasks.check_standard_prices",
    "app.tasks.rate_tasks.check_pension_increase",
    "app.tasks.cost_tasks.recalculate_project_cost",
    "app.tasks.auction_sync_task.sync_onbid_auctions",
    "app.tasks.growth_tasks.flush_growth_events",
    "app.tasks.growth_tasks.analyze_growth",
    "app.tasks.growth_tasks.evaluate_healing",
    "app.tasks.growth_tasks.evaluate_correction",
    "app.tasks.growth_tasks.evaluate_improvement",
    "app.tasks.growth_pr_task.run_pr_bot",
    "app.tasks.growth_learning_task.run_learning",
    "app.tasks.parcel_batch_task.run_batch",
    "tasks.memory.ingest_experience",
    "tasks.specialists.run_for_analysis",
]
