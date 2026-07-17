"""배치 잡의 진행 상태 컨테이너(JobRecord).

JobStore 가 보관하는 단위. 헤더(ParcelBatchJob) + 필지 결과 목록 + 집계 + 대상 PNU 전체 +
취소 플래그를 함께 담는다. store 구현(InMemory/DB)이 이 구조를 직렬화/역직렬화한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.foundation.parcel.contracts.batch import (
    BatchAggregate,
    BatchCounts,
    BatchItemResult,
    Completeness,
    JobState,
    ParcelBatchJob,
)


@dataclass
class JobRecord:
    """배치 잡의 전체 상태(런타임 + 영속 공용)."""

    job: ParcelBatchJob
    target_pnus: list[str] = field(default_factory=list)   # 처리 대상 PNU 전체
    items: list[BatchItemResult] = field(default_factory=list)   # 처리된 필지 결과
    aggregate: BatchAggregate = field(default_factory=BatchAggregate)
    cancelled: bool = False
    degrade_reason: str | None = None

    def processed_pnus(self) -> set[str]:
        """이미 처리된(결과가 있는) PNU 집합."""
        return {it.pnu for it in self.items}

    def pending_pnus(self) -> list[str]:
        """아직 처리 안 됐거나(미처리) 미확정(non-CONFIRMED)인 PNU 목록.

        완결성 신호(INV-M4)에 쓰인다. COMPLETE 가 아니면 이 목록이 비어있지 않다.
        """
        done = self.processed_pnus()
        not_yet = [p for p in self.target_pnus if p not in done]
        from app.foundation.parcel.contracts.batch import ItemStatus

        not_confirmed = [
            it.pnu for it in self.items if it.status != ItemStatus.CONFIRMED
        ]
        # 중복 제거하면서 순서 보존
        seen: set[str] = set()
        out: list[str] = []
        for p in not_yet + not_confirmed:
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def recompute_counts(self) -> None:
        """현재 결과로 카운트/완결성을 다시 계산한다(부분성 1급)."""
        self.job.counts = BatchCounts.from_items(self.items)
        all_processed = len(self.items) >= len(self.target_pnus) and self.target_pnus
        all_confirmed = bool(all_processed) and not self.pending_pnus()
        self.job.completeness = (
            Completeness.COMPLETE if all_confirmed else Completeness.PARTIAL
        )

    def mark_failed(self, reason: str) -> None:
        """실행 중 예외로 잡이 실패했음을 기록한다(터미널 상태 FAILED).

        ★버그수정: 과거엔 백그라운드 러너의 `except Exception: pass`가 예외를 완전히 삼켜
        아무 코드도 이 전이를 호출하지 않았다 — 잡이 RUNNING에 영구 고착돼 프론트가 1.5s
        무한 폴링했다(도달불가 FAILED). 사유는 region_input._error 에 보존한다(신규 DB 컬럼
        없이 기존 JSON 필드 재사용 — _geo/_normalized 와 동일 관례라 DbJobStore 라운드트립을
        그대로 통과한다). 500자로 캡(로그·페이로드 폭주 방지).
        """
        msg = (reason or "알 수 없는 오류").strip()[:500]
        self.job.region_input = {**(self.job.region_input or {}), "_error": msg}
        self.job.state = JobState.FAILED

    def mark_state_from_progress(self) -> None:
        """진행 상태에 따라 JobState 를 갱신한다(취소/완료/부분/실행중)."""
        if self.cancelled:
            self.job.state = JobState.CANCELLED
            return
        if not self.target_pnus:
            # 대상 0개(예: degrade) → 처리 끝났으나 비어있음 = PARTIAL(부분/공백)
            self.job.state = JobState.PARTIAL
            return
        if len(self.items) < len(self.target_pnus):
            self.job.state = JobState.RUNNING
            return
        # 모두 처리됨
        if self.job.completeness == Completeness.COMPLETE:
            self.job.state = JobState.COMPLETE
        else:
            self.job.state = JobState.PARTIAL
