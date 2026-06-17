"""R2 — 소비측 룰셋 리더(읽기 전용). 미러만 조회. 라이브 호출/트리거 절대 금지(INV-13).

미수집 관할 → 차단 대신 degraded(상위표준) + ETA + HarvestJob enqueue(비동기)로 즉시 반환(INV-15).
미승인(DRAFT) 후보는 미러에 없으므로 is_active=False(INV-14).
"""
from __future__ import annotations

from collections.abc import Callable

from app.contracts.mirror import HarvestJob, RulesetLoad
from app.core.parameters import param
from app.supply.mirror.mirror_store import MirrorStore, default_store

# 공급측 비동기 enqueue(기본: in-memory). 실제 배선은 Celery .delay로 교체 가능.
_PENDING_JOBS: list[HarvestJob] = []


def _default_enqueue(job: HarvestJob) -> None:
    _PENDING_JOBS.append(job)


def pending_jobs() -> list[HarvestJob]:
    return list(_PENDING_JOBS)


class RulesetReader:
    def __init__(
        self,
        store: MirrorStore | None = None,
        enqueue: Callable[[HarvestJob], None] | None = None,
    ) -> None:
        self.store = store or default_store()
        self.enqueue = enqueue or _default_enqueue

    def load(self, jurisdiction: str) -> RulesetLoad:
        snapshot = self.store.get(jurisdiction)
        if snapshot is not None:
            # 깊은 복사로 반환 — 소비자 변형이 store의 정본 미러를 오염시키지 못한다(immutable).
            return RulesetLoad(
                jurisdiction=jurisdiction, degraded=False, blocked=False,
                snapshot=snapshot.model_copy(deep=True),
            )

        # 미수집 — 비차단 degraded + ETA + 공급측 수집 요청(비동기).
        self.enqueue(HarvestJob(jurisdiction=jurisdiction))
        return RulesetLoad(
            jurisdiction=jurisdiction,
            degraded=True,
            blocked=False,
            eta=int(param("harvest_eta_business_days")),
            standard_level="national",
        )

    def is_active(self, candidate_id: str) -> bool:
        return candidate_id in self.store.active_candidate_ids()
