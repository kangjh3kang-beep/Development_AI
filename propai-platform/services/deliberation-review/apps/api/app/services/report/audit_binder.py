"""L6 — 감사 결속(INV-29 재현/감사). 각 항목에 snapshot_id + 모델버전 + 입력해시 결속."""
from __future__ import annotations

from app.contracts.report import ReportItem
from app.core.hashing import input_hash


class AuditBinder:
    def bind(
        self,
        item: ReportItem,
        snapshot_id: str,
        model_version: str,
        raw: dict,
    ) -> ReportItem:
        ih = input_hash({"item_id": item.item_id, "raw": raw, "snapshot_id": snapshot_id})
        return item.model_copy(update={
            "snapshot_id": snapshot_id,
            "model_version": model_version,
            "input_hash": ih,
        })
