"""INC-14 — reconcile_mirror 완결: 라이브 1차출처 재대조 → content_hash diff → 미러 새 snapshot
append → 영향 분석 재실행 트리거. 라이브는 공급측(reconcile)에서만(INV-13). 미러 갱신=append(불변).
"""
import asyncio

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.contracts.mirror import MirrorSnapshot
from app.db.models.analysis_models import AnalysisRunModel
from app.db.models.l5_models import ReconcileLogModel
from app.db.models.r2_models import MirrorSnapshotModel
from app.settings import settings
from app.supply.mirror.mirror_store import (
    default_store,
    load_active_snapshot_from_db,
    write_snapshot_to_db,
)
from app.tasks import reconcile_tasks
from app.tasks.reconcile_tasks import _body_hash, reconcile_mirror, reconcile_mirror_db

_JUR = "7777777777777777771"


async def _clean(session, jur):
    await session.execute(delete(MirrorSnapshotModel).where(MirrorSnapshotModel.jurisdiction == jur))
    await session.execute(delete(ReconcileLogModel).where(ReconcileLogModel.citation_ref == jur))
    await session.execute(delete(AnalysisRunModel).where(
        AnalysisRunModel.input_payload["pnu"].astext == jur))
    await session.commit()
    default_store()._by_jurisdiction.pop(jur, None)


async def test_mirror_content_hash_roundtrip(db):
    # content_hash(라이브 본문 해시 provenance)가 미러 snapshot에 영속·재조회됨(설명가능성·diff 근거).
    await db.execute(delete(MirrorSnapshotModel).where(MirrorSnapshotModel.jurisdiction == _JUR))
    await db.commit()
    snap = MirrorSnapshot(snapshot_id="snap-ch", jurisdiction=_JUR, version="v1",
                          rules=[{"ref": "건축법 시행령"}], active_candidate_ids=["c1"],
                          content_hash="abc123")
    await write_snapshot_to_db(db, snap)
    loaded = await load_active_snapshot_from_db(db, _JUR)
    assert loaded is not None
    assert loaded.content_hash == "abc123"
    await db.execute(delete(MirrorSnapshotModel).where(MirrorSnapshotModel.jurisdiction == _JUR))
    await db.commit()


# ── async DB core ────────────────────────────────────────────────────────────


async def test_reconcile_db_match_no_change(db):
    jur = "7777777777777777772"
    await _clean(db, jur)
    await write_snapshot_to_db(db, MirrorSnapshot(
        snapshot_id="snap-m", jurisdiction=jur, rules=[{"ref": "r"}], content_hash="HASH-A"))
    out = await reconcile_mirror_db(db, citation_ref=jur, jurisdiction=jur, live_hash="HASH-A")
    assert out["mismatch"] is False and out["reason"] == "match"
    rows = (await db.execute(select(MirrorSnapshotModel).where(
        MirrorSnapshotModel.jurisdiction == jur))).scalars().all()
    assert len(rows) == 1  # 일치 → append 없음
    await _clean(db, jur)


async def test_reconcile_db_no_baseline_surfaces(db):
    # content_hash 미기록(하베스트가 미설정) → diff 불가 표면화, append/재분석 없음(정직).
    jur = "7777777777777777773"
    await _clean(db, jur)
    await write_snapshot_to_db(db, MirrorSnapshot(
        snapshot_id="snap-nb", jurisdiction=jur, rules=[{"ref": "r"}], content_hash=None))
    out = await reconcile_mirror_db(db, citation_ref=jur, jurisdiction=jur, live_hash="HASH-X")
    assert out["mismatch"] is False and out["reason"] == "no_baseline"
    rows = (await db.execute(select(MirrorSnapshotModel).where(
        MirrorSnapshotModel.jurisdiction == jur))).scalars().all()
    assert len(rows) == 1
    await _clean(db, jur)


async def test_reconcile_db_no_mirror_surfaces(db):
    jur = "7777777777777777774"
    await _clean(db, jur)
    out = await reconcile_mirror_db(db, citation_ref=jur, jurisdiction=jur, live_hash="HASH-X")
    assert out["mismatch"] is False and out["reason"] == "no_mirror"
    # 무음0 일관성: no_mirror도 reconcile_log에 영속(no_baseline/match/mismatch와 대칭, 시도 관측).
    logs = (await db.execute(select(ReconcileLogModel).where(
        ReconcileLogModel.citation_ref == jur))).scalars().all()
    assert any((lg.detail or {}).get("reason") == "no_mirror" for lg in logs)
    await _clean(db, jur)


async def test_reconcile_db_mismatch_appends_and_flags_affected(db):
    jur = "7777777777777777775"
    await _clean(db, jur)
    await write_snapshot_to_db(db, MirrorSnapshot(
        snapshot_id="snap-old", jurisdiction=jur, version="v1",
        rules=[{"ref": "건축법 시행령 제119조"}], active_candidate_ids=["c1"], content_hash="HASH-OLD"))
    # 이 관할을 쓴 분석 run(input_payload 보존) — 재실행 대상.
    db.add(AnalysisRunModel(snapshot_id="snap-1", input_hash="ih", status="DONE",
                            result={"snapshot_id": "snap-1"},
                            input_payload={"pnu": jur, "application_date": "2026-01-01"}))
    await db.commit()

    out = await reconcile_mirror_db(db, citation_ref=jur, jurisdiction=jur, live_hash="HASH-NEW")
    assert out["mismatch"] is True and out["reason"] == "mismatch"
    assert out["old_snapshot_id"] == "snap-old"
    assert out["new_snapshot_id"] == "rcl-HASH-NEW"[:20]  # f"rcl-{live_hash[:16]}"
    # 새 snapshot append(기존 불변) + content_hash=live.
    rows = (await db.execute(select(MirrorSnapshotModel).where(
        MirrorSnapshotModel.jurisdiction == jur).order_by(MirrorSnapshotModel.created_at))).scalars().all()
    assert len(rows) == 2
    new = [r for r in rows if r.snapshot_id == out["new_snapshot_id"]][0]
    assert new.content_hash == "HASH-NEW" and new.rules == [{"ref": "건축법 시행령 제119조"}]
    # 영향 분석 payload 노출(재실행 가능).
    assert len(out["affected_payloads"]) == 1 and out["affected_payloads"][0]["pnu"] == jur
    # reconcile_log 기록(무음0 관측성).
    logs = (await db.execute(select(ReconcileLogModel).where(
        ReconcileLogModel.citation_ref == jur))).scalars().all()
    assert any(lg.mismatch for lg in logs)
    await _clean(db, jur)


async def test_reconcile_db_mismatch_idempotent(db):
    # 동일 drift 재대조 → 결정론 snapshot_id(rcl-<hash>) + on_conflict_do_nothing → 중복 append 없음.
    jur = "7777777777777777776"
    await _clean(db, jur)
    await write_snapshot_to_db(db, MirrorSnapshot(
        snapshot_id="snap-old", jurisdiction=jur, rules=[{"ref": "r"}], content_hash="HASH-OLD"))
    await reconcile_mirror_db(db, citation_ref=jur, jurisdiction=jur, live_hash="HASH-NEW")
    await reconcile_mirror_db(db, citation_ref=jur, jurisdiction=jur, live_hash="HASH-NEW")
    rows = (await db.execute(select(MirrorSnapshotModel).where(
        MirrorSnapshotModel.jurisdiction == jur))).scalars().all()
    assert len(rows) == 2  # old + 1 new(멱등)
    await _clean(db, jur)


# ── sync Celery wrapper ────────────────────────────────────────────────────────


def test_reconcile_mirror_live_disabled_surfaces(monkeypatch):
    # 기본 mock(LIVE_NETWORK off) → 라이브 비활성 표면화, DB 미접근(소비경로 무관·무음0).
    monkeypatch.setattr(settings, "LIVE_NETWORK", False, raising=False)
    called = {"db": False}
    monkeypatch.setattr(reconcile_tasks, "_run_reconcile_db",
                        lambda *a, **k: called.__setitem__("db", True))
    out = reconcile_mirror("건축법 시행령 제119조", "9999999999999999991")
    assert out["live_reconciled"] is False and out["mismatch"] is False
    assert out["reason"] == "live_disabled_or_failed"
    assert called["db"] is False


def test_reconcile_mirror_dispatches_reanalysis_on_mismatch(monkeypatch):
    # 라이브 OK + 불일치(core canned) → default_store 갱신 + 영향 run마다 reanalyze_task.delay(새 snapshot_id).
    jur = "9999999999999999992"
    monkeypatch.setattr(settings, "LIVE_NETWORK", True, raising=False)
    monkeypatch.setattr(reconcile_tasks.LiveNetwork, "get", lambda self, url: b"BODY")
    new_snap = MirrorSnapshot(snapshot_id="rcl-xyz", jurisdiction=jur, rules=[{"ref": "r"}],
                              content_hash=_body_hash(b"BODY"))
    canned = {"mismatch": True, "reason": "mismatch", "old_snapshot_id": "snap-old",
              "new_snapshot_id": "rcl-xyz", "new_snapshot": new_snap, "affected_total": 2,
              "affected_payloads": [{"pnu": jur}, {"pnu": jur, "address": "A"}]}
    monkeypatch.setattr(reconcile_tasks, "_run_reconcile_db", lambda *a, **k: canned)
    dispatched = []
    monkeypatch.setattr(reconcile_tasks.reanalyze_task, "delay", lambda p: dispatched.append(p))

    out = reconcile_mirror("ref", jur)
    assert out["mismatch"] is True and out["reanalyzed"] == 2
    assert all(p["snapshot_id"] == "rcl-xyz" for p in dispatched)  # 새 미러로 재평가
    assert default_store().get(jur) is not None  # in-memory도 최신 미러 반영(공급측 writer)
    default_store()._by_jurisdiction.pop(jur, None)


def test_reconcile_mirror_dedupes_identical_reanalysis(monkeypatch):
    # 동일 입력 다수 run → 새 snapshot_id 주입 후 중복 제거 → 재실행 1회(M4 fan-out 폭주 방지).
    jur = "9999999999999999994"
    monkeypatch.setattr(settings, "LIVE_NETWORK", True, raising=False)
    monkeypatch.setattr(reconcile_tasks.LiveNetwork, "get", lambda self, url: b"BODY")
    new_snap = MirrorSnapshot(snapshot_id="rcl-dup", jurisdiction=jur, rules=[], content_hash="h")
    canned = {"mismatch": True, "reason": "mismatch", "old_snapshot_id": "old",
              "new_snapshot_id": "rcl-dup", "new_snapshot": new_snap, "affected_total": 3,
              # snapshot_id만 다른 동일 입력 3건 → 주입 후 전부 동일 → 1회만 디스패치.
              "affected_payloads": [{"pnu": jur, "snapshot_id": "snap-1"},
                                    {"pnu": jur, "snapshot_id": "snap-2"},
                                    {"pnu": jur}]}
    monkeypatch.setattr(reconcile_tasks, "_run_reconcile_db", lambda *a, **k: canned)
    dispatched = []
    monkeypatch.setattr(reconcile_tasks.reanalyze_task, "delay", lambda p: dispatched.append(p))
    out = reconcile_mirror("ref", jur)
    assert out["reanalyzed"] == 1 and len(dispatched) == 1
    assert out["affected_total"] == 3  # 영향 총수는 정직하게 표면화(중복 제거는 디스패치 한정)
    default_store()._by_jurisdiction.pop(jur, None)


def test_reconcile_mirror_urlencodes_citation_ref(monkeypatch):
    # citation_ref가 URL 쿼리에 안전 인코딩(파라미터 오염/인젝션 방지, M3).
    seen = {}

    def capture(self, url):
        seen["url"] = url
        raise reconcile_tasks.NetworkError("stop")  # 캡처 후 조기 종료(DB 미접근)

    monkeypatch.setattr(settings, "LIVE_NETWORK", True, raising=False)
    monkeypatch.setattr(reconcile_tasks.LiveNetwork, "get", capture)
    reconcile_mirror("건축법&evil=1 제119조", "JX")
    assert "&evil=1" not in seen["url"].split("ref=")[1]  # 원시 & 미주입(인코딩됨)
    assert "%26" in seen["url"] or "%20" in seen["url"]  # 인코딩 흔적


def test_reconcile_mirror_end_to_end(monkeypatch):
    # 실 DB end-to-end: 미러(content_hash=H1) + 영향 run 적재 → 라이브 본문(H2) → mismatch → 새 snapshot
    # append + 재분석 트리거. sync 태스크(asyncio.run+NullPool) 경로 회귀 잠금.
    jur = "9999999999999999993"
    monkeypatch.setattr(settings, "LIVE_NETWORK", True, raising=False)
    body = b"LIVE-DRIFTED-BODY"
    monkeypatch.setattr(reconcile_tasks.LiveNetwork, "get", lambda self, url: body)
    live_hash = _body_hash(body)
    new_sid = f"rcl-{live_hash[:16]}"
    dispatched = []
    monkeypatch.setattr(reconcile_tasks.reanalyze_task, "delay", lambda p: dispatched.append(p))

    async def _setup():
        eng = create_async_engine(settings.database_url, poolclass=NullPool)
        try:
            async with async_sessionmaker(eng, expire_on_commit=False)() as s:
                await _clean(s, jur)
                await write_snapshot_to_db(s, MirrorSnapshot(
                    snapshot_id="snap-old", jurisdiction=jur, rules=[{"ref": "r"}],
                    content_hash="HASH-DIFFERENT"))
                s.add(AnalysisRunModel(snapshot_id="snap-1", input_hash="ih", status="DONE",
                                       result={}, input_payload={"pnu": jur}))
                await s.commit()
        finally:
            await eng.dispose()

    async def _verify_and_clean():
        eng = create_async_engine(settings.database_url, poolclass=NullPool)
        try:
            async with async_sessionmaker(eng, expire_on_commit=False)() as s:
                rows = (await s.execute(select(MirrorSnapshotModel).where(
                    MirrorSnapshotModel.jurisdiction == jur))).scalars().all()
                sids = {r.snapshot_id for r in rows}
                await _clean(s, jur)
                return sids
        finally:
            await eng.dispose()

    asyncio.run(_setup())
    try:
        out = reconcile_mirror("ref", jur)
        assert out["mismatch"] is True
        assert out["new_snapshot_id"] == new_sid
        assert out["reanalyzed"] == 1
        assert dispatched and dispatched[0]["snapshot_id"] == new_sid
    finally:
        sids = asyncio.run(_verify_and_clean())
    assert new_sid in sids and "snap-old" in sids


# ── 주기잡(reconcile_all) ───────────────────────────────────────────────────────


async def test_distinct_jurisdictions_db(db):
    jur = "8888888888888888871"
    await _clean(db, jur)
    await write_snapshot_to_db(db, MirrorSnapshot(
        snapshot_id="s1", jurisdiction=jur, rules=[{"ref": "r"}], content_hash="H"))
    js = await reconcile_tasks._distinct_jurisdictions_db(db)
    assert jur in js
    await _clean(db, jur)


# ── 재분석(reanalyze_task): 새 미러 warm + 결과 영속(H1·H2 해소) ─────────────────────


def test_reanalyze_task_warms_mirror_and_persists(monkeypatch):
    # 다중워커 안전: DB의 최신 미러를 warm(인메모리)한 뒤 동일입력 분석 → 결과를 새 run으로 영속.
    # (트리거가 계산만 하고 버리지 않음 — H2; 새 미러 반영 — H1).
    jur = "8888888888888888872"

    async def _setup():
        eng = create_async_engine(settings.database_url, poolclass=NullPool)
        try:
            async with async_sessionmaker(eng, expire_on_commit=False)() as s:
                await _clean(s, jur)
                # reconcile가 append했을 새 미러를 모사(DB에만 존재, 인메모리엔 없음).
                await write_snapshot_to_db(s, MirrorSnapshot(
                    snapshot_id="rcl-new", jurisdiction=jur,
                    rules=[{"ref": "건축법 시행령", "effective_date": "2025-01-01"}],
                    active_candidate_ids=["c1"], content_hash="H"))
                await s.commit()
        finally:
            await eng.dispose()

    async def _count_and_clean():
        from sqlalchemy import select
        eng = create_async_engine(settings.database_url, poolclass=NullPool)
        try:
            async with async_sessionmaker(eng, expire_on_commit=False)() as s:
                rows = (await s.execute(select(AnalysisRunModel).where(
                    AnalysisRunModel.input_payload["pnu"].astext == jur))).scalars().all()
                n, src = len(rows), {r.result.get("mirror_source") for r in rows if r.result}
                await _clean(s, jur)
                return n, src
        finally:
            await eng.dispose()

    default_store()._by_jurisdiction.pop(jur, None)
    asyncio.run(_setup())
    try:
        out = reconcile_tasks.reanalyze_task({"pnu": jur, "application_date": "2026-01-01",
                                              "snapshot_id": "rcl-new",
                                              "citations": [{"ref": "건축법 시행령"}]})
        assert out["persisted"] is True
        assert out["warmed"] is True  # DB 미러를 인메모리로 적재(다중워커 stale 방지)
    finally:
        n, src = asyncio.run(_count_and_clean())
        default_store()._by_jurisdiction.pop(jur, None)
    assert n == 1  # 재분석 결과가 새 run으로 영속됨(버려지지 않음)
    assert "SUPPLY_STORE" in src  # warm된 DB 미러를 소비측이 사용


def test_reconcile_all_dispatches_per_jurisdiction(monkeypatch):
    # distinct 관할 enumerate → 관할마다 reconcile_mirror.delay 1회(주기잡 fan-out).
    monkeypatch.setattr(reconcile_tasks, "_distinct_jurisdictions", lambda: ["J1", "J2"])
    dispatched = []
    monkeypatch.setattr(reconcile_tasks.reconcile_mirror, "delay",
                        lambda citation_ref, jurisdiction: dispatched.append(jurisdiction))
    out = reconcile_tasks.reconcile_all()
    assert out["jurisdictions"] == 2 and out["dispatched"] == 2
    assert set(dispatched) == {"J1", "J2"}
