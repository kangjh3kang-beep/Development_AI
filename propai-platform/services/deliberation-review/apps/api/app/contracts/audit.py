"""R0 — 감사로그 계약(audit). 모든 단계 호출에 snapshot/모델버전/입력해시 기록(INV-7).

input_hash는 정규화 입력의 안정 해시 → 동일 입력+스냅샷 재현 키.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.core.hashing import input_hash as _input_hash


class AuditRecord(BaseModel):
    """단계별 감사 1건."""

    analysis_id: str
    snapshot_id: str
    model_version: str
    input_hash: str
    layer: str
    decision_ref: str | None = None


def build_audit_record(
    *,
    analysis_id: str,
    snapshot_id: str,
    model_version: str,
    layer: str,
    payload: object,
    decision_ref: str | None = None,
) -> AuditRecord:
    """입력 payload로부터 input_hash를 산출해 감사 레코드 생성."""
    return AuditRecord(
        analysis_id=analysis_id,
        snapshot_id=snapshot_id,
        model_version=model_version,
        input_hash=_input_hash(payload),
        layer=layer,
        decision_ref=decision_ref,
    )
