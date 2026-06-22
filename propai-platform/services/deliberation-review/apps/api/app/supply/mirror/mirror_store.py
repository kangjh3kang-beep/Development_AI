"""R2 — 미러 저장소. 공급측 writer가 적재, 소비측 reader가 읽기 전용으로 조회(INV-13).

INC-13: 프로세스 인메모리(L1, 테스트/폴백) + **DB 영속(L2, mirror_snapshot 테이블 0005)**. 공급측이
write_snapshot_to_db로 영속하면, 소비측은 async 라우트 경계에서 warm_mirror_from_db로 in-memory에 적재해
기존 sync get 경로 그대로 DB-backed 데이터를 읽는다(소비 로직 불변·라이브 미호출). 프로세스 재시작·다중워커 공유.
"""
from __future__ import annotations

from app.contracts.mirror import MirrorSnapshot

_MAX_ENTRIES = 10000  # L1 미러 상한 — 초과 시 가장 오래 적재된 관할부터 회수(장수 워커 메모리 가드).


class MirrorStore:
    def __init__(self) -> None:
        self._by_jurisdiction: dict[str, MirrorSnapshot] = {}

    def put(self, snapshot: MirrorSnapshot) -> None:
        self._by_jurisdiction[snapshot.jurisdiction] = snapshot
        # 상한 초과 시 최오래 항목 회수(DB가 진실원천 → 재warm 저렴, 정합·결정론 무영향).
        if len(self._by_jurisdiction) > _MAX_ENTRIES:
            oldest = next(iter(self._by_jurisdiction))
            if oldest != snapshot.jurisdiction:
                self._by_jurisdiction.pop(oldest, None)

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


# ── INC-13 DB 영속(L2) ─────────────────────────────────────────────────────────
# 미러는 불변(MirrorSnapshot frozen) → append-only·멱등. 소비측은 read-only(INV-13).


async def write_snapshot_to_db(session, snapshot: MirrorSnapshot) -> None:
    """ACTIVE 미러를 DB에 영속(원자적 멱등). 동일 (jurisdiction, snapshot_id)는 무시 — 불변 미러·동시writer 안전.

    DB 유니크 제약(uq_mirror_snapshot_jur_sid, 0014)에 기반한 on_conflict_do_nothing → 경합에도 중복 행 없음.
    """
    import uuid

    from sqlalchemy.dialects.postgresql import insert

    from app.db.models.r2_models import MirrorSnapshotModel as M

    stmt = insert(M).values(
        id=uuid.uuid4(), snapshot_id=snapshot.snapshot_id, jurisdiction=snapshot.jurisdiction,
        version=snapshot.version, rules=list(snapshot.rules),
        active_candidate_ids=list(snapshot.active_candidate_ids),
        content_hash=snapshot.content_hash,  # INC-14: 라이브 본문 해시 provenance(reconcile diff 기준)
    ).on_conflict_do_nothing(constraint="uq_mirror_snapshot_jur_sid")
    await session.execute(stmt)
    await session.commit()


async def load_active_snapshot_from_db(session, jurisdiction: str) -> MirrorSnapshot | None:
    """관할의 최신 미러를 DB에서 조회(소비측 read-only, INV-13 라이브 미호출). 없으면 None."""
    from sqlalchemy import select

    from app.db.models.r2_models import MirrorSnapshotModel as M

    row = (await session.execute(
        select(M).where(M.jurisdiction == jurisdiction)
        .order_by(M.created_at.desc()).limit(1))).scalars().first()
    if row is None:
        return None
    return MirrorSnapshot(snapshot_id=row.snapshot_id, jurisdiction=row.jurisdiction,
                          version=row.version or "v1", rules=row.rules or [],
                          active_candidate_ids=row.active_candidate_ids or [],
                          content_hash=row.content_hash)


async def warm_mirror_from_db(session, jurisdiction: str) -> bool:
    """DB 미러를 in-memory default_store에 적재(소비측 sync get이 DB-backed 데이터를 읽도록). 적재 여부 반환."""
    snap = await load_active_snapshot_from_db(session, jurisdiction)
    if snap is not None:
        default_store().put(snap)
    await session.rollback()  # 읽기 전용 트랜잭션 즉시 종료(INC-11 패턴, idle-in-transaction 방지)
    return snap is not None
