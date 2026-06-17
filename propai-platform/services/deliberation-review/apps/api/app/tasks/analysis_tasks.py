"""P-D — 심의분석 비동기 태스크. 대량 도면/실 LLM 호출을 백그라운드로(소비 지연 미유발).

dev(브로커 없음)는 eager 동기 폴백, 운영은 worker+redis로 진짜 비동기. 결정론 보존(run_analysis 순수).
"""
from __future__ import annotations

from app.tasks.celery_app import celery_app


@celery_app.task(name="analysis.analyze")
def analyze_task(payload: dict) -> dict:
    """원시 입력(dict) → 11계층 분석 → AnalysisResult(JSON dict). 영속화는 호출측 책임."""
    from app.contracts.analysis import AnalysisInput
    from app.services.pipeline.analysis_pipeline import run_analysis

    result = run_analysis(AnalysisInput(**payload))
    return result.model_dump(mode="json")
