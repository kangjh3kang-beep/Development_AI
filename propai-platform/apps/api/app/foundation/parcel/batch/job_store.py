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
import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any

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

logger = logging.getLogger(__name__)


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
    async def get(self, job_id: str) -> JobRecord | None:
        """잡 레코드 조회."""

    @abstractmethod
    async def save(self, record: JobRecord) -> None:
        """잡 레코드 저장(생성/갱신)."""

    @abstractmethod
    async def find_by_idempotency(self, key: str) -> JobRecord | None:
        """멱등키로 기존 잡 조회."""

    @abstractmethod
    async def bind_idempotency(self, key: str, job_id: str) -> None:
        """멱등키 ↔ 잡 ID 매핑 등록."""

    async def unbind_idempotency(self, key: str) -> None:
        """멱등키 매핑 해제(잘못된 잡 재사용 방지 — 기본 no-op, 구현체가 override)."""
        return None


class InMemoryJobStore(JobStore):
    """메모리 저장소 — 테스트 및 단일 프로세스 폴백."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._idem: dict[str, str] = {}   # 멱등키 → job_id

    async def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    async def save(self, record: JobRecord) -> None:
        self._jobs[record.job.id] = record

    async def find_by_idempotency(self, key: str) -> JobRecord | None:
        jid = self._idem.get(key)
        return self._jobs.get(jid) if jid else None

    async def bind_idempotency(self, key: str, job_id: str) -> None:
        self._idem[key] = job_id

    async def unbind_idempotency(self, key: str) -> None:
        self._idem.pop(key, None)


# ★같은 (job, pnu) 행이 **여럿일 때 어느 것을 남길지** — 순서 컬럼이 없어서 규칙이 필요하다.
#
#   `batch_item_result` 에는 `created_at` 도 시퀀스도 없고 `id` 는 **랜덤 UUID** 다.
#   즉 **「마지막 행」을 알 수 없다.** 그래서 시간이 아니라 **정보량**으로 고른다:
#
#     ① 상태 우선순위  confirmed > ambiguous > not_found > error
#        (뒤에 성공한 실행이 앞선 실패를 대체하는 것이 옳다)
#     ② 같으면 `record_ref` 키가 **많은 것**
#        ★「풍부함 ⇒ 나중」은 **참이 아니다** — 나중 실행에서 대장/공유자 외부호출이
#        실패하면(`job_runner` 의 `getattr` 폴백) 나중 행이 **더 빈약**하다.
#        선호 근거는 시간이 아니라 **정보 보존**이다: 잃을 것이 적은 쪽을 남긴다.
#     ③ 그래도 같으면 `pnu` 안에서 **결정적**이도록 `id` 사전순
#        (재현 불가능한 결과를 만들지 않는다)
# ★**목록이 아니라 파생이다.** 손으로 나열하면 `ItemStatus` 에 값이 하나 늘 때
#   그 값이 `.get(..., -1)` 로 조용히 **최하위**가 되어 언제나 진다.
#   여기서는 **선호 순서만** 선언하고, 나머지는 `ItemStatus` 전수에서 채운다 —
#   빠뜨린 상태가 있으면 `test_상태표가_ItemStatus_전수를_덮는다` 가 실패한다.
_STATUS_PREFERENCE: tuple[str, ...] = (
    ItemStatus.CONFIRMED.value,
    ItemStatus.AMBIGUOUS.value,
    ItemStatus.NOT_FOUND.value,
    ItemStatus.ERROR.value,
)
_STATUS_RANK: dict[str, int] = {
    v: len(_STATUS_PREFERENCE) - 1 - i for i, v in enumerate(_STATUS_PREFERENCE)
}


def _dedupe_key(row: Any) -> tuple[int, int, str]:
    return (
        _STATUS_RANK.get(str(getattr(row, "status", "") or ""), -1),
        len(dict(getattr(row, "record_ref", None) or {})),
        str(getattr(row, "id", "")),
    )


def dedupe_item_rows(item_rows: Any) -> list[Any]:
    """(job, pnu) 중복 행을 **PNU 당 한 건**으로 줄인다(결정적).

    ## 왜 읽는 쪽에서 고치나 (2026-09-03 라이브 실측)

    잡 **25건 중 9건(36%)** 에 중복 행이 있었고, 최악은 `counts` 가 **2,800** 인데
    고유 PNU 는 **1,000**(2.8배)이었다. 그 `counts.confirmed` 는 `batch_service` 에서
    **화면에 보이는 예상 사용료**(`estimated_fee_krw`)에 곱해진다.
    ★**청구 축은 없다** — 2026-09-03 실측: `charge_once`/`charge_service` 실호출부 **5파일**
    (대조군: 조회기 생존)에 대해 배치/필지 경로 **0건**. 피해는 「돈이 빠져나감」이 아니라
    **「사용자가 최대 2.8배 틀린 견적을 보고 판단함」** 이다.

    ★그리고 `counts` 도 **여기서 다시 센다** — 배열만 중복제거하면 `counts` 가 여전히 거짓이라
    **소비처마다 다른 답**을 받는다(그 모순이 이 결함의 본체였다).

    ## ★★쓰기 왕복은 **의도적으로 정리한다**(초판의 「지우지 않는다」는 거짓이었다)

    `save()` 는 `job_id` 의 행을 **전부 DELETE 한 뒤 `record.items` 를 재삽입**한다
    (`save()` 의 「필지 결과는 통째로 교체」 블록). 따라서 이 함수가 접은 뒤 어떤 경로로든
    저장이 일어나면 **중복 행은 DB 에서 영구히 사라진다** — `cancel()`·`run()`·
    `result(wait=True)` 가 전부 그 경로다.

    ★초판 주석은 *"데이터를 지우지 않는다"* 라고 적었고 **그것은 거짓이었다.**
    적대 리뷰가 4-arm 대조(이 변경만 되돌린 팔 포함)로 실증했다. 지금은 **의도로 승격**한다:
    중복 행은 재실행이 만든 **쓰레기**이고, 고유 필지 정보는 하나도 잃지 않는다
    (PNU 당 최상위 상태·최다 정보 행이 남는다). 즉 **쓰면서 자가치유**한다.

    ★다만 **조용히 지우지는 않는다** — 접을 때마다 접힌 수를 로그로 남긴다.
    계획서가 *"9건 전부가 같은 기전인지는 미측정"* 이라고 적어 둔 그 조사의 증거가
    삭제와 함께 사라지면 안 되기 때문이다.
    """
    best: dict[str, Any] = {}
    passthrough: list[Any] = []
    for r in item_rows:
        pnu = str(getattr(r, "pnu", "") or "").strip()
        if not pnu:
            # ★PNU 가 비면 **중복인지 판정할 수 없다.** 판정 불가를 「같다」로 뭉개면
            #   서로 다른 미해석 입력이 한 건으로 사라진다 — 결함을 고치려다 데이터를 지운다.
            passthrough.append(r)
            continue
        cur = best.get(pnu)
        # ★`>` 를 `>=` 로 바꿔도 결과가 같다(**설명 가능한 생존**): 키의 세 번째 성분이
        #   `id` 이고 그것은 PK 라 **키 튜플이 유일**하므로 동점 자체가 성립하지 않는다.
        #   구멍이 아니라 도달 불가 분기다 — 다음 사람이 이 생존을 구멍으로 읽지 않도록 적는다.
        if cur is None or _dedupe_key(r) > _dedupe_key(cur):
            best[pnu] = r
    kept = list(best.values()) + passthrough
    folded = len(list(item_rows)) - len(kept) if isinstance(item_rows, list) else 0
    if folded > 0:
        # ★**조용히 지우지 않는다.** 다음 `save()` 가 원본 행을 영구 삭제하므로,
        #   그 전에 「무엇이 몇 건 접혔는지」를 남긴다 — 근본원인 조사의 유일한 증거다.
        logger.warning(
            "배치 중복행 접힘: %d행 → %d행(중복 %d) job_pnu_sample=%s",
            len(item_rows), len(kept), folded,
            [str(getattr(r, "pnu", "")) for r in item_rows[:3]],
        )
    return kept


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

    async def get(self, job_id: str) -> JobRecord | None:
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

            # 잡 헤더를 먼저 DB에 반영(flush)해야 자식(item/aggregate)의 FK가 만족된다.
            # (한 트랜잭션 안에서도 PostgreSQL은 INSERT마다 FK를 즉시 검사하므로
            #  부모 행을 명시적으로 먼저 flush 하지 않으면 자식 INSERT가 먼저 나가 위반 가능.)
            await session.flush()

            # 필지 결과는 통째로 교체(멱등 갱신).
            await session.execute(
                delete(BatchItemResultRow).where(
                    BatchItemResultRow.job_id == record.job.id
                )
            )
            for it in record.items:
                # area_sqm/address는 전용 컬럼이 없어 record_ref(JSON)에 실어 영속화
                # (마이그레이션 없이 DB 라운드트립 보존 → 이상치/동일값 경고가 prod서 실동작).
                ref = dict(it.record_ref or {})
                if it.area_sqm is not None:
                    ref["_area_sqm"] = it.area_sqm
                if it.address:
                    ref["_address"] = it.address
                session.add(BatchItemResultRow(
                    id=str(uuid.uuid4()),
                    job_id=record.job.id,
                    pnu=it.pnu,
                    status=it.status.value,
                    record_ref=ref or None,
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

    async def find_by_idempotency(self, key: str) -> JobRecord | None:
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

    async def unbind_idempotency(self, key: str) -> None:
        from sqlalchemy import select

        from app.models.parcel_batch import ParcelBatchJobRow

        async with self._sf()() as session:
            job_row = (
                await session.execute(
                    select(ParcelBatchJobRow).where(ParcelBatchJobRow.idempotency_key == key)
                )
            ).scalar_one_or_none()
            if job_row is not None:
                job_row.idempotency_key = None  # 키 해제 → 새 잡이 동일 키 재사용 가능
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
        items = []
        # ★중복 행을 **읽는 순간** 접는다(라이브 실측: 잡 25건 중 9건이 오염 · 최악 2.8배).
        for r in dedupe_item_rows(item_rows):
            ref = dict(r.record_ref or {})
            # area_sqm/address 복원(save에서 record_ref에 실어둠) — 이상치/동일값 경고 실동작.
            area = ref.pop("_area_sqm", None)
            addr = ref.pop("_address", None)
            items.append(BatchItemResult(
                pnu=r.pnu,
                status=ItemStatus(r.status),
                address=addr,
                area_sqm=area,
                record_ref=ref or None,
                reason=r.reason,
            ))
        # ★`counts` 를 **접힌 items 로 다시 센다.** 저장된 값은 오염 시점에 부풀어 있고,
        #   그 값이 `batch_service` 에서 **견적 금액에 곱해진다**(돈이 걸린 자리).
        #   배열만 접고 counts 를 그대로 두면 **소비처마다 다른 답**을 받는다.
        job.counts = BatchCounts.from_items(items)

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
