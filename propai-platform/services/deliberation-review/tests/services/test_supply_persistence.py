"""INC-13 — 수집 데이터 DB 영속화 검증.

미러(공급측) DB 영속 + 소비측 warm → DB-backed 미러를 read-only로 조회(INV-13, 라이브 미호출).
프로세스 재시작 휘발 제거·다중워커 공유. in-memory 폴백 유지(직접 run_analysis 비파괴). 출처 강제(INV-23).
"""
from datetime import date

import pytest
from sqlalchemy import delete, select

from app.contracts.analysis import AnalysisInput
from app.contracts.mirror import MirrorSnapshot
from app.contracts.precedent import PrecedentCase
from app.contracts.source_document import DocTier, SourceDocument
from app.core.errors import SourceMissing
from app.db.models.l4_models import PrecedentCaseModel
from app.db.models.r2_models import MirrorSnapshotModel, SourceDocumentModel
from app.services.pipeline.analysis_pipeline import run_analysis
from app.supply.db_persist import persist_cases, persist_documents
from app.supply.mirror.mirror_store import (
    default_store,
    load_active_snapshot_from_db,
    warm_mirror_from_db,
    write_snapshot_to_db,
)

_PNU = "8888888888888888881"


async def test_mirror_db_roundtrip_warm_and_consumer(db):
    # 공급측 DB 영속 → load → warm(in-memory) → 소비측 run_analysis가 DB-backed 미러를 SUPPLY_STORE로 조회.
    await db.execute(delete(MirrorSnapshotModel).where(MirrorSnapshotModel.jurisdiction == _PNU))
    await db.commit()
    default_store()._by_jurisdiction.pop(_PNU, None)

    snap = MirrorSnapshot(snapshot_id="snap-inc13", jurisdiction=_PNU, version="v1",
                          rules=[{"ref": "건축법 시행령", "effective_date": "2025-01-01"}],
                          active_candidate_ids=["c1"])
    await write_snapshot_to_db(db, snap)
    await write_snapshot_to_db(db, snap)  # 멱등 — 동일 (jurisdiction, snapshot_id) 재기록 시 추가 안 함

    rows = (await db.execute(
        select(MirrorSnapshotModel).where(MirrorSnapshotModel.jurisdiction == _PNU))).scalars().all()
    assert len(rows) == 1  # append-only 멱등

    loaded = await load_active_snapshot_from_db(db, _PNU)
    assert loaded is not None and loaded.snapshot_id == "snap-inc13" and loaded.rules == snap.rules

    # warm → in-memory default_store → 소비측 sync get(소비 로직 불변, INV-13 read-only)
    default_store()._by_jurisdiction.pop(_PNU, None)
    assert await warm_mirror_from_db(db, _PNU) is True
    assert default_store().get(_PNU) is not None

    r = run_analysis(AnalysisInput(pnu=_PNU, application_date=date(2026, 1, 1),
                                   citations=[{"ref": "건축법 시행령"}]))
    assert r.mirror_source == "SUPPLY_STORE"

    await db.execute(delete(MirrorSnapshotModel).where(MirrorSnapshotModel.jurisdiction == _PNU))
    await db.commit()
    default_store()._by_jurisdiction.pop(_PNU, None)


async def test_mirror_in_memory_fallback_preserved(db):
    # warm 미호출(직접 경로) + DB 미적재 → default_store 빈 → 소비측 미적재 보수 게이팅(폴백 비파괴).
    pnu = "8888888888888888882"
    await db.execute(delete(MirrorSnapshotModel).where(MirrorSnapshotModel.jurisdiction == pnu))
    await db.commit()
    default_store()._by_jurisdiction.pop(pnu, None)
    r = run_analysis(AnalysisInput(pnu=pnu, application_date=date(2026, 1, 1),
                                   citations=[{"ref": "건축법 시행령"}]))
    assert r.mirror_source is None
    assert any("mirror 미적재" in s for s in r.skipped)


async def test_persist_documents_idempotent(db):
    doc_id = "inc13-doc-1"
    await db.execute(delete(SourceDocumentModel).where(SourceDocumentModel.doc_id == doc_id))
    await db.commit()
    docs = [SourceDocument(doc_id=doc_id, tier=DocTier.TIER1, uri="http://x", content_hash="h",
                           jurisdiction="J", title="T")]
    assert await persist_documents(db, docs) == 1
    assert await persist_documents(db, docs) == 1  # upsert 멱등(중복 행/오류 없음)
    rows = (await db.execute(
        select(SourceDocumentModel).where(SourceDocumentModel.doc_id == doc_id))).scalars().all()
    assert len(rows) == 1 and rows[0].tier == "TIER1"
    await db.execute(delete(SourceDocumentModel).where(SourceDocumentModel.doc_id == doc_id))
    await db.commit()


def test_harvest_persist_repeatable_across_loops():
    # 동일 프로세스 2회 호출 — 일회용 NullPool 엔진이라 교차-이벤트루프 무음 실패 없이 둘 다 영속(회귀 잠금).
    import asyncio

    from app.contracts.source_document import DocTier, SourceDocument
    from app.tasks.supply_tasks import _persist_documents_best_effort

    docs = [SourceDocument(doc_id="inc13-harvest-1", tier=DocTier.TIER1, uri="u", content_hash="h",
                           jurisdiction="J", title="T")]

    async def _cleanup():
        from sqlalchemy import delete
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.db.models.r2_models import SourceDocumentModel
        from app.settings import settings
        eng = create_async_engine(settings.database_url, poolclass=NullPool)
        try:
            async with async_sessionmaker(eng)() as s:
                await s.execute(delete(SourceDocumentModel).where(
                    SourceDocumentModel.doc_id == "inc13-harvest-1"))
                await s.commit()
        finally:
            await eng.dispose()

    try:
        r1 = _persist_documents_best_effort(docs)
        r2 = _persist_documents_best_effort(docs)
        assert r1 == 1 and r2 == 1  # 2회차도 성공(글로벌 엔진 교차루프 버그 회귀 방지)
    finally:
        asyncio.run(_cleanup())


def test_mirror_store_eviction_cap(monkeypatch):
    # 상한 초과 시 최오래 관할 회수(장수 워커 메모리 가드).
    from app.supply.mirror import mirror_store as ms
    monkeypatch.setattr(ms, "_MAX_ENTRIES", 3)
    store = ms.MirrorStore()
    for i in range(5):
        store.put(MirrorSnapshot(snapshot_id=f"s{i}", jurisdiction=f"J{i}"))
    assert len(store._by_jurisdiction) <= 3


async def test_persist_cases_roundtrip_and_source_enforced(db):
    cid = "inc13-case-1"
    await db.execute(delete(PrecedentCaseModel).where(PrecedentCaseModel.case_id == cid))
    await db.commit()
    cases = [PrecedentCase(case_id=cid, source="의결서-1", issue_labels=["FAR"], conditions=["공개공지"])]
    assert await persist_cases(db, cases) == 1
    row = (await db.execute(
        select(PrecedentCaseModel).where(PrecedentCaseModel.case_id == cid))).scalars().first()
    assert row is not None and row.source == "의결서-1"
    # 출처 없는 사례 → emit이 차단(INV-23)
    with pytest.raises(SourceMissing):
        await persist_cases(db, [PrecedentCase(case_id="inc13-nosrc", source=None)])
    await db.execute(delete(PrecedentCaseModel).where(PrecedentCaseModel.case_id == cid))
    await db.commit()
