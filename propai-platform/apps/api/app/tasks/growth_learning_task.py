"""자가성장 엔진 Phase 5 — L3 자가학습 주간 배치(설계서 §6.4).

learning_loop.run_learning_cycle 를 주 1회 구동한다(일요일 04:00, celery_app beat).
이어서 improvement_agent.generate_prompt_candidates 로 down율 높은 service 의
프롬프트 개선후보를 **A/B 후보군에만 등록**한다(자동 채택 아님 — 설계 §6.2 안전장치).

안전경계(절대 준수):
- 파인튜닝 잡 자동실행 금지(learning_loop 는 JSONL 생성까지만).
- few-shot 자동 활성 금지(candidate 등록만, promote API 사람 승인).
- 프롬프트 개선후보는 A/B 후보군 등록까지만(임의 자동 적용 금지).

analyze/heal/correct 선례와 동일하게 DB(platform_events/ai_feedback/analysis_ledger
/learning_examples)를 읽으므로 별도 Celery 워커에서도 정상 동작(프로세스-로컬 큐 비의존).
best-effort: 어떤 예외도 워커를 죽이지 않는다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _get_celery_app():
    """Celery 앱을 지연 임포트한다(growth_tasks 선례)."""
    try:
        from app.tasks.celery_app import app
        return app
    except (ImportError, RuntimeError):
        return None


async def _learn_async() -> dict:
    """1회 L3 학습 사이클 + 프롬프트 개선후보 등록을 새 AsyncSession 으로 구동한다."""
    from app.services.growth import improvement_agent, learning_loop
    from apps.api.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        cycle = await learning_loop.run_learning_cycle(session)
        # down율 개선대상 service → 프롬프트 개선후보 생성(A/B 후보군 등록까지만).
        targets = ((cycle.get("down_targets") or {}).get("services")) or []
        prompt = await improvement_agent.generate_prompt_candidates(
            session, target_services=targets
        )
    return {"cycle": cycle, "prompt_candidates": prompt}


def run_learning() -> dict:
    """L3 자가학습 주간 배치. Beat 일요일 04:00 호출.

    반환: {"cycle": {...}, "prompt_candidates": {...}}. 동기 진입점(Celery 워커)에서
    asyncio.run 으로 구동. best-effort: 어떤 예외도 워커를 죽이지 않는다.
    """
    import asyncio

    try:
        result = asyncio.run(_learn_async())
    except RuntimeError:
        # 이미 이벤트 루프가 도는 환경 — 새 루프로 격리(flush/analyze/heal 선례 동일).
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_learn_async())
        finally:
            loop.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("run_learning 실패: %s", str(e)[:160])
        return {"cycle": {}, "prompt_candidates": {}, "error": str(e)[:160]}

    cur = (result.get("cycle") or {}).get("curation") or {}
    pc = result.get("prompt_candidates") or {}
    if cur.get("curated") or pc.get("registered"):
        logger.info("growth L3: few-shot 후보 %d건 / 프롬프트 개선후보 %d건",
                    cur.get("curated", 0), pc.get("registered", 0))
    return result


# Celery 태스크 등록(앱이 있을 때만; 미설치 환경에서도 함수는 직접 호출 가능).
_celery = _get_celery_app()
if _celery is not None:
    run_learning = _celery.task(
        name="app.tasks.growth_learning_task.run_learning"
    )(run_learning)
