"""R2 — 인용검증(분석경로). 미러 스냅샷 대조만. 라이브 호출 절대 없음(INV-13/WB10 해소).

라이브 1차출처 정합 점검은 분석경로와 분리된 주기 Celery 잡(tasks/verify_tasks.py)이 수행.
이 모듈은 네트워크를 import/사용하지 않음(test_consume_static로 강제).
"""
from __future__ import annotations

from pydantic import BaseModel

from app.contracts.mirror import MirrorSnapshot


class CitationCheck(BaseModel):
    citation_ref: str | None = None
    matched: bool = False
    method: str = "MIRROR"
    snapshot_id: str | None = None


class CitationVerifier:
    def verify(self, citation: dict, snapshot: MirrorSnapshot) -> CitationCheck:
        ref = citation.get("ref")
        rules = snapshot.rules if snapshot else []
        matched = any(r.get("ref") == ref for r in rules)
        return CitationCheck(
            citation_ref=ref,
            matched=matched,
            method="MIRROR",
            snapshot_id=snapshot.snapshot_id if snapshot else None,
        )
