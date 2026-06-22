"""R2 — 공급측 비동기 Celery 태스크. 소비 경로와 분리(소비 지연 미유발).

run_harvest_job: 수집 실행(외부 실패 시 fallback). 결과는 후속 파싱/추출/HITL 파이프로 연결.
"""
from __future__ import annotations

from app.supply.harvester.harvester import Harvester
from app.tasks.celery_app import celery_app


def _persist_documents_best_effort(documents) -> int:
    """INC-13 — 수집 문서를 source_document에 영속(best-effort). Celery 워커(별 프로세스)는 자체 루프로 실행.
    이미 실행 중인 루프(async 컨텍스트)면 skip, 실패는 무시(수집 자체는 성공 — 무음 단정 금지와 무관한 영속 부가)."""
    if not documents:
        return 0
    import asyncio
    try:
        asyncio.get_running_loop()
        return 0  # 실행 중 루프 → asyncio.run 불가 → skip(best-effort)
    except RuntimeError:
        pass  # 루프 없음(Celery 워커) → 영속 진행

    async def _go() -> int:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.settings import settings
        from app.supply.db_persist import persist_documents
        # 호출마다 일회용 엔진(NullPool) — 글로벌 엔진 풀 연결이 새 asyncio.run 루프에 결속돼 장수 워커
        # 재호출 시 'Event loop is closed'로 무음 실패하는 교차-이벤트루프 버그 회피. 연결이 루프를 넘기지 않음.
        eng = create_async_engine(settings.database_url, poolclass=NullPool)
        try:
            async with async_sessionmaker(eng, expire_on_commit=False)() as s:
                return await persist_documents(s, documents)
        finally:
            await eng.dispose()

    try:
        return asyncio.run(_go())
    except Exception:
        import logging
        # 무음0/정직 — 반복 가능한 영속 실패를 삼키지 않고 로그로 표면화(수집 자체는 성공, best-effort degrade).
        logging.getLogger("supply").warning(
            "source_document 영속 실패(best-effort) — 배선/DB 점검 필요", exc_info=True)
        return 0


@celery_app.task(name="supply.run_harvest_job")
def run_harvest_job(jurisdiction: str) -> dict:
    result = Harvester().run(jurisdiction)
    persisted = _persist_documents_best_effort(result.documents)
    return {
        "jurisdiction": jurisdiction,
        "used_fallback": result.used_fallback,
        "documents": len(result.documents),
        "persisted": persisted,
    }
