"""성장 뇌(MemoryHub) — 에이전트/패널 경험을 비동기 임베딩·저장하는 Celery 태스크.

★중요(버그수정): 과거 `from app.tasks.celery_app import celery_app` 는 celery_app 모듈이
`app` 심볼만 export 하므로 ImportError → 이 모듈 전체 로드 실패 → 호출부(specialist_agent·
expert_panel_service)의 `from app.tasks.memory_tasks import ingest_experience_task` 가 항상
실패 → 자동 기억저장(ingest)이 모든 경로에서 silent 스킵되던 단절이었다. growth_tasks/rate_tasks
선례(_get_celery_app 지연 임포트 + 조건부 등록)로 통일해 모듈이 항상 import 가능하게 한다.

★실제 저장은 인프라 의존(deploy-pending): Celery 워커 가동 + Qdrant(QDRANT_HOST·미설정 시
프로세스-로컬 :memory: 라 워커↔API 교차 불가) + OPENAI_API_KEY(임베딩). 미비 시 graceful 스킵.
"""

import asyncio
import logging

from app.core.database import async_session_factory
from app.schemas.memory import MemoryCreate
from app.services.memory_hub.memory_service import get_memory_hub

logger = logging.getLogger(__name__)


def _get_celery_app():
    """Celery 앱을 지연 임포트한다(growth_tasks/rate_tasks 선례). 미설치/미생성 시 None."""
    try:
        from app.tasks.celery_app import app
        return app
    except (ImportError, RuntimeError):
        return None


_celery = _get_celery_app()


async def _ingest_async(memory_data_dict: dict) -> bool:
    """경험 요약 → 임베딩 + Qdrant upsert + agent_memories 저장(MemoryHubService 단일경유)."""
    try:
        memory_data = MemoryCreate(**memory_data_dict)
    except Exception as e:  # noqa: BLE001 — 스키마 불일치는 정직하게 실패 반환
        logger.error("Invalid memory_data format: %s", str(e)[:200])
        return False
    service = get_memory_hub()
    async with async_session_factory() as db:
        await service.store_experience(db, memory_data)
    logger.info("Successfully ingested memory (session=%s).", memory_data_dict.get("session_id"))
    return True


def _ingest_experience(memory_data_dict: dict) -> bool:
    """Celery 워커 스레드에서 async 저장을 동기 실행(원본 동작 보존)."""
    logger.info("Starting memory ingestion task (session=%s).", memory_data_dict.get("session_id"))
    try:
        return asyncio.run(_ingest_async(memory_data_dict))
    except Exception as e:  # noqa: BLE001 — 임베딩/Qdrant/DB 실패는 graceful(분석 무중단)
        logger.error("Error during memory ingestion: %s", str(e)[:200])
        return False


def dispatch_memory_ingest(memory_data_dict: dict) -> None:
    """성장 뇌 경험 적재를 핫패스 비차단으로 발화(★G1 해소).

    워커가 명시 활성(GROWTH_CELERY_WORKER)이고 celery 가용이면 Celery(.delay)로 위임하고,
    아니면(기본·워커부재) in-process 백그라운드로 실제 적재한다. 과거 `.delay()` 는 워커 부재 시
    no-op 이라 적재가 死였다. 호출부는 이걸 부르기만 하면 된다(dead-path 재발 방지).
    """
    from app.services.agents.growth_dispatch import fire_and_forget, worker_enabled

    if _celery is not None and worker_enabled():
        ingest_experience_task.delay(memory_data_dict)
        return
    fire_and_forget(_ingest_async(memory_data_dict), label="memory-ingest")


if _celery is not None:
    # Celery 등록 — .delay() 로 워커에 비동기 위임(원본 계약 유지·워커 배포 시).
    ingest_experience_task = _celery.task(name="tasks.memory.ingest_experience")(_ingest_experience)
else:
    # Celery 부재(테스트/워커 외 프로세스) — .delay() 가 graceful no-op(이벤트루프 충돌·크래시 회피).
    #   호출부는 try/except 로 감싸지만, 모듈 import 자체는 항상 성공해야 한다(과거 단절 재발 방지).
    class _NoopTask:
        @staticmethod
        def delay(*_a, **_k) -> None:
            logger.debug("celery 부재 — memory ingest .delay no-op(워커 미가동)")

        @staticmethod
        def run(memory_data_dict: dict) -> bool:
            return _ingest_experience(memory_data_dict)

    ingest_experience_task = _NoopTask()  # type: ignore[assignment]
