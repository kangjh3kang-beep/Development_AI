"""배치 잡 저장소(JobStore).

- 추상 JobStore: save/get/upsert_idempotent 인터페이스.
- InMemoryJobStore: 테스트/인프로세스 폴백(네트워크·DB 불필요).
- DbJobStore: async SQLAlchemy 로 app/models/parcel_batch.py 테이블에 영속.

멱등키(INV-M2) = sha256(정규화 region_input + snapshot_id).
동일 키의 잡이 이미 있으면 새로 만들지 않고 기존 잡을 반환한다(중복 작업 미생성).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from abc import ABC, abstractmethod
from typing import Any, Optional

from app.foundation.parcel.batch.job_state import JobRecord
from app.foundation.parcel.contracts.batch import (
    BatchAggregate,
    BatchCounts,
    BatchItemResult,
    Completeness,
    ItemStatus,
    JobState,
    ParcelBatchJob,
)


def idempotency_key(region_input: dict[str, Any], snapshot_id: str) -> str:
    """정규화된 region_input + snapshot_id 로 멱등키를 만든다."""
    payload = json.dumps(
        {"region": region_input, "snapshot": snapshot_id},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class JobStore(ABC):
    """배치 잡 저장소 인터페이스."""

    @abstractmethod
    async def get(self, job_id: str) -> Optional[JobRecord]:
        """잡 레코드 조회."""

    @abstractmethod
    async def save(self, record: JobRecord) -> None:
        """잡 레코드 저장(생성/갱신)."""

    @abstractmethod
    async def find_by_idempotency(self, key: str) -> Optional[JobRecord]:
        """멱등키로 기존 잡 조회."""

    @abstractmethod
    async def bind_idempotency(self, key: str, job_id: str) -> None:
        """멱등키 ↔ 잡 ID 매핑 등록."""


class InMemoryJobStore(JobStore):
    """메모리 저장소 — 테스트 및 단일 프로세스 폴백."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._idem: dict[str, str] = {}   # 멱등키 → job_id

    async def get(self, job_id: str) -> Optional[JobRecord]:
        return self._jobs.get(job_id)

    async def save(self, record: JobRecord) -> None:
        self._jobs[record.job.id] = record

    async def find_by_idempotency(self, key: str) -> Optional[JobRecord]:
        jid = self._idem.get(key)
        return self._jobs.get(jid) if jid else None

    async def bind_idempotency(self, key: str, job_id: str) -> None:
        self._idem[key] = job_id


class DbJobStore(JobStore):
    """async SQLAlchemy 영속 저장소.

    app/models/parcel_batch.py 의 3개 테이블에 잡/필지결과/집계를 저장한다.
    멱등키는 parcel_batch_job 의 idempotency_key 컬럼에서 조회한다.
    """

    def __init__(self, session_factory: Any = None) -> None:
        """session_factory: AsyncSession 컨텍스트 매니저를 만드는 팩토리.

        미지정 시 app.core.database.AsyncSessionLocal 을 지연 사용한다.
        """
        self._session_factory = session_factory

    def _sf(self) -> Any:
        if self._session_factory is not None:
            return self._session_factory
        from app.core.database import AsyncSessionLocal

        self._session_factory = AsyncSessionLocal
        return self._session_factory

    async def get(self, job_id: str) -> Optional[JobRecord]:
        from sqlalchemy import select

        from app.models.parcel_batch import (
            BatchAggregateRow,
            BatchItemResultRow,
            ParcelBatchJobRow,
        )

        async with self._sf()() as session:
            job_row = (
                await session.execute(
                    select(ParcelBatchJobRow).where(ParcelBatchJobRow.id == job_id)
                )
            ).scalar_one_or_none()
            if job_row is None:
                return None
            item_rows = (
                await session.execute(
                    select(BatchItemResultRow).where(
                        BatchItemResultRow.job_id == job_id
                    )
                )
            ).scalars().all()
            agg_row = (
                await session.execute(
                    select(BatchAggregateRow).where(BatchAggregateRow.job_id == job_id)
                )
            ).scalar_one_or_none()
            return self._to_record(job_row, item_rows, agg_row)

    async def save(self, record: JobRecord) -> None:
        from sqlalchemy import delete, select

        from app.models.parcel_batch import (
            BatchAggregateRow,
            BatchItemResultRow,
            ParcelBatchJobRow,
        )

        async with self._sf()() as session:
            job_row = (
                await session.execute(
                    select(ParcelBatchJobRow).where(
                        ParcelBatchJobRow.id == record.job.id
                    )
                )
            ).scalar_one_or_none()
            counts = record.job.counts.model_dump()
            region = dict(record.job.region_input)
            if record.target_pnus:
                # 대상 PNU 전체를 region_input 안에 보관(재구성용).
                region = {**region, "_target_pnus": record.target_pnus}
            if job_row is None:
                job_row = ParcelBatchJobRow(
                    id=record.job.id,
                    snapshot_id=record.job.snapshot_id,
                    state=record.job.state.value,
                    region_input=region,
                    completeness=record.job.completeness.value,
                    counts=counts,
                )
                session.add(job_row)
            else:
                job_row.snapshot_id = record.job.snapshot_id
                job_row.state = record.job.state.value
                job_row.region_input = region
                job_row.completeness = record.job.completeness.value
                job_row.counts = counts

            # 필지 결과는 통째로 교체(멱등 갱신).
            await session.execute(
                delete(BatchItemResultRow).where(
                    BatchItemResultRow.job_id == record.job.id
                )
            )
            for it in record.items:
                session.add(BatchItemResultRow(
                    id=str(uuid.uuid4()),
                    job_id=record.job.id,
                    pnu=it.pnu,
                    status=it.status.value,
                    record_ref=it.record_ref,
                    reason=it.reason,
                ))

            await session.execute(
                delete(BatchAggregateRow).where(
                    BatchAggregateRow.job_id == record.job.id
                )
            )
            session.add(BatchAggregateRow(
                id=str(uuid.uuid4()),
                job_id=record.job.id,
                union_boundary=record.aggregate.union_boundary,
                total_area_sqm=record.aggregate.total_area_sqm,
                jurisdiction_flags=record.aggregate.jurisdiction_flags,
                held=record.aggregate.held,
            ))
            await session.commit()

    async def find_by_idempotency(self, key: str) -> Optional[JobRecord]:
        from sqlalchemy import select

        from app.models.parcel_batch import ParcelBatchJobRow

        async with self._sf()() as session:
            job_row = (
                await session.execute(
                    select(ParcelBatchJobRow).where(
                        ParcelBatchJobRow.idempotency_key == key
                    )
                )
            ).scalar_one_or_none()
        if job_row is None:
            return None
        return await self.get(job_row.id)

    async def bind_idempotency(self, key: str, job_id: str) -> None:
        from sqlalchemy import select

        from app.models.parcel_batch import ParcelBatchJobRow

        async with self._sf()() as session:
            job_row = (
                await session.execute(
                    select(ParcelBatchJobRow).where(ParcelBatchJobRow.id == job_id)
                )
            ).scalar_one_or_none()
            if job_row is not None:
                job_row.idempotency_key = key
                await session.commit()

    def _to_record(self, job_row: Any, item_rows: Any, agg_row: Any) -> JobRecord:
        """DB 행들을 런타임 JobRecord 로 복원한다."""
        region = dict(job_row.region_input or {})
        target_pnus = region.pop("_target_pnus", [])
        counts_data = job_row.counts or {}
        job = ParcelBatchJob(
            id=str(job_row.id),
            snapshot_id=job_row.snapshot_id,
            state=JobState(job_row.state),
            region_input=region,
            completeness=Completeness(job_row.completeness),
            counts=BatchCounts(**counts_data) if counts_data else BatchCounts(),
        )
        items = [
            BatchItemResult(
                pnu=r.pnu,
                status=ItemStatus(r.status),
                record_ref=r.record_ref,
                reason=r.reason,
            )
            for r in item_rows
        ]
        aggregate = BatchAggregate(held=True)
        if agg_row is not None:
            aggregate = BatchAggregate(
                union_boundary=agg_row.union_boundary,
                total_area_sqm=agg_row.total_area_sqm,
                jurisdiction_flags=agg_row.jurisdiction_flags,
                held=bool(agg_row.held),
            )
        return JobRecord(
            job=job, target_pnus=list(target_pnus), items=items, aggregate=aggregate,
        )
