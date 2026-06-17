"""R2 — 공급측 비동기 Celery 태스크. 소비 경로와 분리(소비 지연 미유발).

run_harvest_job: 수집 실행(외부 실패 시 fallback). 결과는 후속 파싱/추출/HITL 파이프로 연결.
"""
from __future__ import annotations

from app.supply.harvester.harvester import Harvester
from app.tasks.celery_app import celery_app


@celery_app.task(name="supply.run_harvest_job")
def run_harvest_job(jurisdiction: str) -> dict:
    result = Harvester().run(jurisdiction)
    return {
        "jurisdiction": jurisdiction,
        "used_fallback": result.used_fallback,
        "documents": len(result.documents),
    }
