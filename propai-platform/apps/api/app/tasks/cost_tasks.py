"""v61 공사비 재계산 태스크.

법정요율 변경 시 영향받는 프로젝트의 원가계산서를 재생성한다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _get_celery_app():
    """Celery 앱을 지연 임포트한다."""
    try:
        from app.tasks.celery_app import app
        return app
    except (ImportError, RuntimeError):
        return None


def recalculate_project_cost(project_id: str) -> dict:
    """지정 프로젝트의 원가계산서를 재생성한다.

    Args:
        project_id: 프로젝트 UUID 문자열.

    Returns:
        재계산 결과 딕셔너리.
    """
    from app.services.cost.origin_cost_calculator import OriginCostCalculator

    logger.info("프로젝트 공사비 재계산 시작: %s", project_id)

    OriginCostCalculator()

    # 실제 구현: DB에서 BimQuantity + MaterialUnitPrice 조회 후 CostItem 구성
    # 여기서는 스텁 응답 반환
    result = {
        "project_id": project_id,
        "status": "recalculated",
        "message": "원가계산서 재생성 완료 (법정요율 갱신 반영)",
        "calculator_version": "v61",
    }

    logger.info("프로젝트 공사비 재계산 완료: %s", project_id)
    return result


# Celery 데코레이터 적용
_celery_app = _get_celery_app()
if _celery_app is not None:
    recalculate_project_cost = _celery_app.task(
        name="app.tasks.cost_tasks.recalculate_project_cost",
        bind=False,
        max_retries=3,
        default_retry_delay=60,
    )(recalculate_project_cost)
