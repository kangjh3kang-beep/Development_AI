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

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

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


def _batch_input_from_region(region_input: dict[str, Any]) -> BatchInput:
    """저장된 region_input(정규화 dict)에서 내부 키(_geo/_target_pnus/_normalized)를
    걷어내고 BatchInput을 재구성한다 — run()의 지연 정규화에 사용."""
    fields = ("pnu_list", "polygon", "bbox", "admin_code", "district_code",
              "center_address", "radius_m")
    kwargs = {k: region_input[k] for k in fields if region_input.get(k) is not None}
    return BatchInput(**kwargs)


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
    # H1: 동일값 군집 — 확정 필지의 면적이 과반 동일하면(오매칭/중복 정황) 정직 경고.
    #     중앙값 비교(분산 이상치)는 '전부 동일' 케이스를 못 잡으므로 별도 검사.
    uniform: list[dict[str, Any]] = []
    if len(areas) >= 3:
        from collections import Counter
        vc = Counter(round(a, 1) for a, _, _ in areas)
        top_val, top_cnt = vc.most_common(1)[0]
        if top_cnt >= max(3, int(len(areas) * 0.6)):
            uniform.append({
                "kind": "uniform_area", "area_sqm": top_val, "count": top_cnt, "total": len(areas),
                "reason": f"{len(areas)}필지 중 {top_cnt}필지가 동일 면적({top_val}㎡) — 오매칭/중복 정황, 주소 정밀화 권고",
            })
    if len(areas) < 5:
        return uniform
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
    return uniform + out


class BatchService:
    """대량 다필지 배치 서비스."""

    def __init__(
        self,
        store: JobStore | None = None,
        runner: JobRunner | None = None,
        aggregator: Aggregator | None = None,
        vworld: Any = None,
    ) -> None:
        self.store = store or InMemoryJobStore()
        self.runner = runner or JobRunner(vworld=vworld)
        self.aggregator = aggregator or Aggregator(vworld=vworld)
        self._vworld = vworld

    async def submit(
        self, inp: BatchInput, snapshot_id: str | None = None
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
        # H2: 단, degrade(미해석)·전건 미확정(confirmed=0)·실패 잡은 재사용 금지 — 잘못된 결과가
        #     멱등으로 영구 고착되는 것을 막고 새 잡으로 재시도(사용자가 주소 보완 후 재실행 가능).
        existing = await self.store.find_by_idempotency(key)
        if existing is not None:
            ej = existing.job
            # 진행 중(QUEUED/RUNNING)이거나 정상 종료면 재사용. 터미널인데 degrade·전건미확정·실패면
            # 잘못된 결과 고착이므로 멱등 해제 후 새 잡 생성(사용자 주소 보완 재시도 허용).
            in_progress = ej.state in (JobState.QUEUED, JobState.RUNNING)
            bad_terminal = (not in_progress) and (
                bool(existing.degrade_reason) or ej.counts.confirmed == 0 or ej.state == JobState.FAILED
            )
            if not bad_terminal:
                return ej
            await self.store.unbind_idempotency(key)

        job = ParcelBatchJob(
            id=str(uuid.uuid4()),
            snapshot_id=snapshot_id,
            state=JobState.QUEUED,
            region_input=region_input,
            completeness=Completeness.PARTIAL,
        )
        record = JobRecord(job=job)

        # ★정규화(geocode+bbox 조회=무거움)는 submit에서 하지 않고 run()(백그라운드)으로 미룬다.
        #   submit은 즉시 QUEUED 잡만 만들어 응답 → UI 반응성 확보(동기 19s 지연 제거).
        await self.store.save(record)
        await self.store.bind_idempotency(key, job.id)
        return job

    async def run(self, job_id: str) -> JobRecord:
        """인라인 실행 — 청크별 store 갱신 → 완료 시 집계 → 상태 확정.

        ★버그수정(FAILED 도달불가): 실행 중 예외는 여기서 잡아 JobRecord.mark_failed로
        FAILED 상태를 저장한 뒤 재전파한다. 과거엔 호출측(라우터의 인프로세스 백그라운드
        태스크)이 `except Exception: pass`로 예외를 완전히 삼켜 아무 코드도 FAILED를 쓰지
        않았다 — 잡이 RUNNING에 영구 고착돼 프론트가 1.5s 간격으로 무한 폴링했다. 여기서
        선(先)저장 후 재전파하면 호출측(인프로세스 background task·Celery run_batch 둘 다)의
        기존 예외 처리/로깅은 그대로 유지되면서, 폴링은 항상 터미널 상태로 수렴한다.
        """
        record = await self.store.get(job_id)
        if record is None:
            raise KeyError(f"잡을 찾을 수 없음: {job_id}")

        if record.cancelled:
            record.mark_state_from_progress()
            await self.store.save(record)
            return record

        try:
            # ★정규화(submit에서 이전) — 아직 정규화 전이면 여기서 geocode+bbox 조회를 수행.
            ri = record.job.region_input or {}
            if not ri.get("_normalized"):
                inp = _batch_input_from_region(ri)
                norm = await region_normalizer.normalize(inp, vworld=self._vworld)
                record.target_pnus = norm.pnus
                record.degrade_reason = norm.reason if norm.degraded else None
                new_ri = {**ri, "_normalized": True}
                if norm.geo:
                    new_ri["_geo"] = norm.geo
                record.job.region_input = new_ri
                await self.store.save(record)

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
        except Exception as e:  # noqa: BLE001 — FAILED로 표면화(무음 고착 방지) 후 재전파(호출측 처리 유지).
            try:
                current = await self.store.get(job_id) or record
            except Exception:  # noqa: BLE001 — store 조회 자체 실패 시 최초 record로 폴백 저장.
                current = record
            if not current.cancelled:
                current.mark_failed(str(e))
                try:
                    await self.store.save(current)
                except Exception:  # noqa: BLE001 — 저장까지 실패하면 상태 고착은 불가피(로그로만 표면화).
                    logger.warning("배치 잡 FAILED 상태 저장 실패: job_id=%s", job_id)
            raise

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
            error=(record.job.region_input or {}).get("_error"),
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

    async def get(self, job_id: str) -> ParcelBatchJob | None:
        """잡 헤더 조회."""
        record = await self.store.get(job_id)
        return record.job if record else None
