"""R2 — 미러 적재기. ACTIVE 후보만 MirrorSnapshot에 적재(INV-14). snapshot_id 부여.

DRAFT/REJECTED는 절대 적재 안 함 → 소비측이 미승인 룰을 읽을 수 없음.
"""
from __future__ import annotations

from app.contracts.mirror import MirrorSnapshot
from app.contracts.rule_candidate import CandidateStatus, RuleCandidate
from app.supply.mirror.mirror_store import MirrorStore, default_store


class MirrorWriter:
    def __init__(self, store: MirrorStore | None = None) -> None:
        self.store = store or default_store()

    def write(
        self,
        jurisdiction: str,
        candidates: list[RuleCandidate],
        snapshot_id: str,
        version: str = "v1",
    ) -> MirrorSnapshot:
        active = [c for c in candidates if c.status == CandidateStatus.ACTIVE]
        snapshot = MirrorSnapshot(
            snapshot_id=snapshot_id,
            jurisdiction=jurisdiction,
            version=version,
            rules=[c.content for c in active],
            active_candidate_ids=[c.candidate_id for c in active],
        )
        self.store.put(snapshot)
        return snapshot

    async def persist_to_db(self, session, snapshot: MirrorSnapshot) -> None:
        """INC-13 — write()로 만든 미러를 DB에 영속(재시작·다중워커 공유). ACTIVE-only는 write가 이미 보장."""
        from app.supply.mirror.mirror_store import write_snapshot_to_db
        await write_snapshot_to_db(session, snapshot)
