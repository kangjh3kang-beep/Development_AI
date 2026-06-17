"""L5 — 라이브 정합 잡 디스크립터. **분석경로와 분리**(in_analysis_path=False).

실제 라이브 1차출처 대조는 Celery 태스크(tasks/reconcile_tasks.py)에서만 수행 → services/verify/는
네트워크 토큰 0 유지(INV-13 정적검사 통과). 본 모듈은 잡 메타데이터/트리거만 보유.
"""
from __future__ import annotations


class ReconcileJob:
    is_async = True
    in_analysis_path = False
    task_name = "verify.reconcile_mirror"

    @classmethod
    def descriptor(cls) -> dict:
        return {
            "is_async": cls.is_async,
            "in_analysis_path": cls.in_analysis_path,
            "task_name": cls.task_name,
        }
