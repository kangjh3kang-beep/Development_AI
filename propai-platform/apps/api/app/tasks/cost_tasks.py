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
    # W3-10: 미구현 스텁이 "재생성 완료" 허위 성공을 반환하던 것을 정직화(무날조) —
    # 아무것도 재계산하지 않으면서 성공 메시지를 주면 법정요율 갱신이 반영된 것처럼
    # 오인된다. 실제 구현은 DB에서 BimQuantity+MaterialUnitPrice 조회 후 CostItem 구성.
    logger.warning("프로젝트 공사비 재계산 태스크 호출 — 미구현 스텁(재계산 미수행): %s", project_id)
    return {
        "project_id": project_id,
        "status": "not_implemented",
        "message": "원가계산서 자동 재생성 미구현 — 재계산은 수행되지 않았습니다(수동 재산출 필요).",
        "calculator_version": "v61",
    }


# Celery 데코레이터 적용
_celery_app = _get_celery_app()
if _celery_app is not None:
    recalculate_project_cost = _celery_app.task(
        name="app.tasks.cost_tasks.recalculate_project_cost",
        bind=False,
        max_retries=3,
        default_retry_delay=60,
    )(recalculate_project_cost)
