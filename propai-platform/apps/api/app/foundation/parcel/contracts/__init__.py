"""F-Parcel 배치 계약(Contracts) — 입력/결과 스키마와 상태 enum."""

from app.foundation.parcel.contracts.batch import (
    ItemStatus,
    Completeness,
    JobState,
    BatchInput,
    BatchItemResult,
    BatchCounts,
    BatchAggregate,
    ParcelBatchJob,
    BatchResult,
)

__all__ = [
    "ItemStatus",
    "Completeness",
    "JobState",
    "BatchInput",
    "BatchItemResult",
    "BatchCounts",
    "BatchAggregate",
    "ParcelBatchJob",
    "BatchResult",
]