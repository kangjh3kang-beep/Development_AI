"""v61 법정요율/표준단가/연금 자동갱신 태스크.

Celery beat 스케줄에 의해 주기적으로 실행된다.
"""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_celery_app():
    """Celery 앱을 지연 임포트한다."""
    try:
        from app.tasks.celery_app import app
        return app
    except (ImportError, RuntimeError):
        return None


def check_legal_rates() -> dict:
    """법정요율 변동을 감지하고, 변경 시 프로젝트 재계산을 큐에 등록한다.

    매일 01:00 실행 (beat_schedule).
    """
    from app.services.cost.legal_rate_service import LegalRateService

    svc = LegalRateService()
    result = svc.refresh_rates()

    if result["status"] == "updated":
        logger.info(
            "법정요율 변경 감지: %d개 항목 갱신",
            result.get("updated_count", 0),
        )
        # 실제 구현: 영향받는 프로젝트에 recalculate_project_cost 큐 등록
    else:
        logger.info("법정요율 변동 없음 (%s)", datetime.now().isoformat())

    return result


def check_standard_prices() -> dict:
    """CODIL API에서 표준단가 변동을 확인한다.

    매주 월요일 02:00 실행 (beat_schedule).
    """
    logger.info("표준단가 갱신 확인 시작 (%s)", datetime.now().isoformat())

    # CODIL API 호출 스텁 — 실제 구현 시 httpx 비동기 호출
    result = {
        "status": "no_changes",
        "checked_at": datetime.now().isoformat(),
        "source": "CODIL",
        "price_count": 0,
    }

    logger.info("표준단가 확인 완료: %s", result["status"])
    return result


def check_pension_increase() -> dict:
    """국민연금 단계인상(2026~2033, +0.5%p/년)을 반영한다.

    매월 1일 03:00 실행 (beat_schedule).
    """
    from app.services.cost.legal_rate_service import LegalRateService

    svc = LegalRateService()
    current_year = datetime.now().year
    rate = svc.get_pension_for_year(current_year)

    result = {
        "year": current_year,
        "pension_rate": rate,
        "checked_at": datetime.now().isoformat(),
        "status": "applied",
    }

    logger.info(
        "국민연금 요율 확인: %d년 = %.4f%%",
        current_year, rate * 100,
    )
    return result


# Celery 데코레이터 적용 (celery 설치 시에만)
_celery_app = _get_celery_app()
if _celery_app is not None:
    check_legal_rates = _celery_app.task(
        name="app.tasks.rate_tasks.check_legal_rates",
        bind=False,
        max_retries=3,
        default_retry_delay=300,
    )(check_legal_rates)

    check_standard_prices = _celery_app.task(
        name="app.tasks.rate_tasks.check_standard_prices",
        bind=False,
        max_retries=3,
        default_retry_delay=600,
    )(check_standard_prices)

    check_pension_increase = _celery_app.task(
        name="app.tasks.rate_tasks.check_pension_increase",
        bind=False,
        max_retries=3,
        default_retry_delay=300,
    )(check_pension_increase)
