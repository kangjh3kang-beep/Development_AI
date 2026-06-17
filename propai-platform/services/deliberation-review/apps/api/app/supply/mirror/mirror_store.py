"""R2 — 미러 저장소(dev in-memory). 공급측 writer가 적재, 소비측 reader가 읽기 전용으로 조회.

실제 영속화는 mirror_snapshot 테이블(0005)로 후속 배선. 테스트는 격리 위해 자체 store 주입 가능.
"""
from __future__ import annotations

from app.contracts.mirror import MirrorSnapshot


class MirrorStore:
    def __init__(self) -> None:
        self._by_jurisdiction: dict[str, MirrorSnapshot] = {}

    def put(self, snapshot: MirrorSnapshot) -> None:
        self._by_jurisdiction[snapshot.jurisdiction] = snapshot

    def get(self, jurisdiction: str) -> MirrorSnapshot | None:
        return self._by_jurisdiction.get(jurisdiction)

    def has(self, jurisdiction: str) -> bool:
        return jurisdiction in self._by_jurisdiction

    def active_candidate_ids(self) -> set[str]:
        ids: set[str] = set()
        for snap in self._by_jurisdiction.values():
            ids.update(snap.active_candidate_ids)
        return ids


_DEFAULT_STORE = MirrorStore()


def default_store() -> MirrorStore:
    return _DEFAULT_STORE
