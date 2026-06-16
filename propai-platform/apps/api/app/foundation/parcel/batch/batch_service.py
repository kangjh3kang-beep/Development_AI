"""배치 서비스(BatchService) — submit / run / result / cancel 오케스트레이션.

생성자 주입(store, runner, aggregator)으로 테스트가 쉽다.
기본은 InMemoryJobStore + 인라인 JobRunner + Aggregator.

불변식:
- INV-M2 멱등: 동일 region+snapshot 재제출 → 동일 job_id(중복 작업 미생성).
- INV-M3 스냅샷: submit 시 snapshot_id 고정, 잡 내내 불변.
- INV-M4 완결성: result 에 completeness + pending 항상 포함.
- INV-M5 집계: 모두 CONFIRMED 일 때만 aggregate 채움, 아니면 held=True.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from app.foundation.parcel.batch import region_normalizer
from app.foundation.parcel.batch.aggregator import Aggregator
from app.foundation.parcel.batch.job_runner import JobRunner
from app.foundation.parcel.batch.job_state import JobRecord
from app.foundation.parcel.batch.job_store import (
    InMemoryJobStore,
    JobStore,
    idempotency_key,
)
from app.foundation.parcel.contracts.batch import (
    BatchAggregate,
    BatchInput,
    BatchItemResult,
    BatchResult,
    Completeness,
    JobState,
    ParcelBatchJob,
)


def _area_outliers(items: list[BatchItemResult]) -> list[dict[str, Any]]:
    """신뢰루프: 확정 필지들의 면적 분포에서 이상치를 표시한다(검토 권고, 배제 아님).

    중앙값(median) 기준 robust 비교 — 면적이 중앙값의 5배 초과 또는 1/5 미만이면 이상치.
    표본이 적으면(<5) 통계 불안정이라 건너뛴다(과경보 방지). 무목업: 가짜 보정 없이 '플래그'만.
    """
    areas = sorted(
        (it.area_sqm, it.pnu, it.address)
        for it in items
        if it.status.value == "confirmed" and it.area_sqm and it.area_sqm > 0
    )
    if len(areas) < 5:
        return []
    vals = [a for a, _, _ in areas]
    mid = len(vals) // 2
    median = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
    if median <= 0:
        return []
    out: list[dict[str, Any]] = []
    for area, pnu, addr in areas:
        ratio = area / median
        if ratio > 5 or ratio < 0.2:
            out.append({
                "pnu": pnu, "address": addr, "area_sqm": round(area, 1),
                "median_sqm": round(median, 1), "ratio": round(ratio, 2),
                "reason": f"면적이 구역 중앙값({round(median)}㎡)의 {round(ratio, 1)}배 — 데이터 확인 권고",
            })
    return out


class BatchService:
    """대량 다필지 배치 서비스."""

    def __init__(
        self,
        store: Optional[JobStore] = None,
        runner: Optional[JobRunner] = None,
        aggregator: Optional[Aggregator] = None,
        vworld: Any = None,
    ) -> None:
        self.store = store or InMemoryJobStore()
        self.runner = runner or JobRunner(vworld=vworld)
        self.aggregator = aggregator or Aggregator(vworld=vworld)
        self._vworld = vworld

    async def submit(
        self, inp: BatchInput, snapshot_id: Optional[str] = None
    ) -> ParcelBatchJob:
        """배치 잡을 등록한다(멱등). snapshot_id 없으면 고정 생성(INV-M3).

        멱등키 규칙:
        - snapshot_id 명시 → (region+snapshot) 기준(스펙: 마스터 버전별 재분석 허용).
        - snapshot_id 미지정 → region 기준만(같은 구역 중복 제출 방지). 잡 자체에는
          여전히 고정 snapshot_id(uuid)를 부여해 INV-M3(배치 내 단일 버전)를 지킨다.
        """
        explicit_snapshot = snapshot_id is not None
        snapshot_id = snapshot_id or uuid.uuid4().hex
        region_input = inp.normalized()
        key = idempotency_key(region_input, snapshot_id if explicit_snapshot else "")

        # 멱등: 동일 키 잡이 있으면 그대로 반환(중복 작업 미생성).
        existing = await self.store.find_by_idempotency(key)
        if existing is not None:
            return existing.job

        job = ParcelBatchJob(
            id=str(uuid.uuid4()),
            snapshot_id=snapshot_id,
            state=JobState.QUEUED,
            region_input=region_input,
            completeness=Completeness.PARTIAL,
        )
        record = JobRecord(job=job)

        # 대상 PNU 정규화(외부 미가용이면 degrade).
        norm = await region_normalizer.normalize(inp, vworld=self._vworld)
        record.target_pnus = norm.pnus
        record.degrade_reason = norm.reason if norm.degraded else None
        if norm.geo:
            # 지도 미리보기용 해석 좌표를 region_input에 보관(결과로 노출).
            job.region_input = {**region_input, "_geo": norm.geo}

        await self.store.save(record)
        await self.store.bind_idempotency(key, job.id)
        return job

    async def run(self, job_id: str) -> JobRecord:
        """인라인 실행 — 청크별 store 갱신 → 완료 시 집계 → 상태 확정."""
        record = await self.store.get(job_id)
        if record is None:
            raise KeyError(f"잡을 찾을 수 없음: {job_id}")

        if record.cancelled:
            record.mark_state_from_progress()
            await self.store.save(record)
            return record

        # 대상이 없으면(예: degrade) 바로 PARTIAL 로 마감(부분/공백).
        if not record.target_pnus:
            record.recompute_counts()
            record.aggregate = BatchAggregate(held=True)
            record.mark_state_from_progress()
            await self.store.save(record)
            return record

        record.job.state = JobState.RUNNING
        await self.store.save(record)

        async def on_chunk(results: list[BatchItemResult]) -> None:
            # 매 청크마다 부분 결과를 반영(PARTIAL 진행률 노출).
            current = await self.store.get(job_id)
            if current is None:
                return
            current.items.extend(results)
            current.recompute_counts()
            current.mark_state_from_progress()
            await self.store.save(current)

        def is_cancelled() -> bool:
            # 매번 store 에서 최신 취소 상태 확인.
            return record.cancelled

        await self.runner.run_chunks(record.target_pnus, on_chunk, is_cancelled)

        # 최종 상태 재로딩 후 집계.
        final = await self.store.get(job_id)
        if final is None:
            return record
        if final.cancelled:
            final.mark_state_from_progress()
            await self.store.save(final)
            return final

        final.recompute_counts()
        final.aggregate = await self.aggregator.run(final)
        final.mark_state_from_progress()
        await self.store.save(final)
        return final

    async def result(
        self, job_id: str, page: int = 1, size: int = 500, wait: bool = False
    ) -> BatchResult:
        """폴링 응답(페이지네이션). wait=True 면 인라인 실행 완료까지 기다린다(테스트용)."""
        record = await self.store.get(job_id)
        if record is None:
            raise KeyError(f"잡을 찾을 수 없음: {job_id}")

        # 아직 실행 전(QUEUED)이고 wait=True 면 인라인으로 돌려 완료시킨다.
        if wait and record.job.state in (JobState.QUEUED, JobState.RUNNING):
            record = await self.run(job_id)

        page = max(1, int(page))
        size = max(1, int(size))
        start = (page - 1) * size
        end = start + size
        page_items = record.items[start:end]
        has_next = end < len(record.items)

        # 과금: 필지당 단가(관리자 설정·미설정 0=무료) × 확정 필지수. 하드코딩 금지.
        try:
            from app.core.billing import service_fee_bulk_parcel_per_unit
            per_unit = service_fee_bulk_parcel_per_unit()
        except Exception:  # noqa: BLE001 - 빌링 모듈 미가용(테스트 등) → 무료
            per_unit = 0.0
        estimated_fee = per_unit * float(record.job.counts.confirmed)

        return BatchResult(
            job_id=record.job.id,
            state=record.job.state,
            completeness=record.job.completeness,
            counts=record.job.counts,
            items=page_items,
            aggregate=record.aggregate,
            pending=record.pending_pnus(),
            outliers=_area_outliers(record.items),
            fee_per_unit_krw=per_unit,
            estimated_fee_krw=estimated_fee,
            region_geo=(record.job.region_input or {}).get("_geo"),
            page=page,
            size=size,
            has_next=has_next,
        )

    async def cancel(self, job_id: str) -> ParcelBatchJob:
        """잡을 취소한다(상태기계: → CANCELLED)."""
        record = await self.store.get(job_id)
        if record is None:
            raise KeyError(f"잡을 찾을 수 없음: {job_id}")
        record.cancelled = True
        record.job.state = JobState.CANCELLED
        await self.store.save(record)
        return record.job

    async def get(self, job_id: str) -> Optional[ParcelBatchJob]:
        """잡 헤더 조회."""
        record = await self.store.get(job_id)
        return record.job if record else None