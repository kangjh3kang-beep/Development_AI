"""L5 — 미러↔라이브 1차출처 주기 정합(Celery 잡). **분석경로와 분리**, 라이브는 여기서만(INV-13).

흐름(불일치 시): 라이브 본문 재취득 → content_hash diff → 새 snapshot append(기존 불변·재현성) →
영향 분석(동일 관할) 재분석 트리거(reanalyze_task: 새 미러 warm → 동일입력 재실행 → 결과 영속).
분석(소비)경로는 미러만 read-only로 읽음(INV-13).

설계 메모(정직):
- 라이브는 LiveNetwork(공급측 choke point). 기본 mock(LIVE_NETWORK off)이면 live_reconciled=False로 표면화(무음0).
- content_hash 미기록(no_baseline)·미러 부재(no_mirror)는 diff 불가로 표면화 — append/재분석 없음(결손 단정 금지).
- 미러 갱신 snapshot_id는 결정론(rcl-<live_hash[:16]>) → 동일 drift 재대조 시 on_conflict_do_nothing으로 멱등.
- **한계(정직)**: content_hash diff는 "라이브 본문이 달라졌다"만 탐지한다. 새 본문을 rules로 재파싱하는 것은
  하베스트(공급 수집)의 몫 — reconcile는 기존 rules를 verbatim 복사한 새 snapshot_id를 append한다(버전 마커).
  따라서 재분석은 같은 rules를 새 미러 버전 라벨로 재실행·재영속하는 것(드리프트가 affected run에 추적됨)이며,
  규칙 내용 자체의 재평가는 재하베스트 후 다음 reconcile 사이클에서 일어난다.
- 영향 분석 조회는 analysis_run.input_payload.pnu == jurisdiction(0015). input_payload 없는 legacy run은
  재실행 불가(동일입력 미보존) — affected_total로 표면화하되 재실행 디스패치에서 제외.
- 재분석 디스패치는 동일입력(새 snapshot_id 주입 후) 중복 제거 + 상한(RECONCILE_MAX_REANALYZE) 절단(로깅, 무음0).
"""
from __future__ import annotations

import hashlib
import logging
import urllib.parse

from app.adapters.network import LiveNetwork, NetworkError
from app.contracts.mirror import MirrorSnapshot
from app.core.hashing import canonical
from app.supply.mirror.mirror_store import (
    default_store,
    load_active_snapshot_from_db,
    write_snapshot_to_db,
)
from app.tasks.celery_app import celery_app

_log = logging.getLogger("reconcile")


def _body_hash(raw: bytes) -> str:
    """라이브 본문 → 안정 sha256(content_hash diff 기준). bytes 외엔 문자열화 후 해시(결정론)."""
    data = raw if isinstance(raw, bytes) else str(raw).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


async def _write_reconcile_log(session, *, citation_ref, live_reconciled, mismatch, detail) -> None:
    """정합 결과를 reconcile_log에 기록(관측성·무음0). best-effort 영속 — 호출측 트랜잭션에서 commit."""
    from app.db.models.l5_models import ReconcileLogModel

    session.add(ReconcileLogModel(citation_ref=citation_ref, live_reconciled=live_reconciled,
                                  mismatch=mismatch, detail=detail))
    await session.commit()


async def _affected_run_payloads(session, jurisdiction: str) -> list[dict]:
    """이 관할(input_payload.pnu)을 입력으로 쓴 분석 run의 원시 입력 목록(재실행 대상). input_payload 보존분만."""
    from sqlalchemy import select

    from app.db.models.analysis_models import AnalysisRunModel as A

    rows = (await session.execute(
        select(A.input_payload).where(A.input_payload["pnu"].astext == jurisdiction))).scalars().all()
    await session.rollback()  # 읽기 전용 트랜잭션 즉시 종료(idle-in-transaction 방지, INC-11 패턴)
    return [p for p in rows if p]


async def reconcile_mirror_db(session, *, citation_ref: str, jurisdiction: str, live_hash: str) -> dict:
    """미러 로드 → content_hash diff → 불일치 시 새 snapshot append + 영향 run 조회 + 정합 로그.

    재현성/불변: 기존 snapshot 불변(append-only), 새 snapshot_id 결정론(멱등). celery dispatch/in-memory
    갱신은 호출측(sync wrapper) 책임 — 본 함수는 순수 DB 로직(테스트 용이·async 경계 단일).
    """
    out: dict = {"jurisdiction": jurisdiction or None, "mismatch": False, "reason": None,
                 "old_snapshot_id": None, "new_snapshot_id": None, "new_snapshot": None,
                 "affected_payloads": [], "affected_total": 0}
    if not jurisdiction:
        out["reason"] = "no_jurisdiction"
        # 무음0 일관성 — 정합 시도(라이브 성공)했으나 관할 부재를 reconcile_log에 영속(관측).
        await _write_reconcile_log(session, citation_ref=citation_ref, live_reconciled=True,
                                   mismatch=False, detail={"reason": "no_jurisdiction"})
        return out
    snap = await load_active_snapshot_from_db(session, jurisdiction)
    if snap is None:
        out["reason"] = "no_mirror"  # 미러 부재 — diff 불가 표면화(무음0)
        await _write_reconcile_log(session, citation_ref=citation_ref, live_reconciled=True,
                                   mismatch=False, detail={"reason": "no_mirror", "live_hash": live_hash})
        return out
    out["old_snapshot_id"] = snap.snapshot_id
    if snap.content_hash is None:
        # 하베스트가 본문 해시를 기록하지 않음 → diff 근거 없음. 갱신/재분석 없이 관측만(정직).
        out["reason"] = "no_baseline"
        await _write_reconcile_log(session, citation_ref=citation_ref, live_reconciled=True,
                                   mismatch=False, detail={"reason": "no_baseline", "live_hash": live_hash})
        return out
    if snap.content_hash == live_hash:
        out["reason"] = "match"
        await _write_reconcile_log(session, citation_ref=citation_ref, live_reconciled=True,
                                   mismatch=False, detail={"reason": "match", "content_hash": live_hash})
        return out

    # 불일치 — 미러 갱신: 새 snapshot append(기존 불변). 결정론 snapshot_id로 동일 drift 멱등.
    out["mismatch"] = True
    out["reason"] = "mismatch"
    new_sid = f"rcl-{live_hash[:16]}"
    new_snap = MirrorSnapshot(snapshot_id=new_sid, jurisdiction=jurisdiction, version=snap.version,
                              rules=list(snap.rules), active_candidate_ids=list(snap.active_candidate_ids),
                              content_hash=live_hash)
    await write_snapshot_to_db(session, new_snap)  # on_conflict_do_nothing → 멱등 append
    out["new_snapshot_id"] = new_sid
    out["new_snapshot"] = new_snap

    payloads = await _affected_run_payloads(session, jurisdiction)
    out["affected_payloads"] = payloads
    out["affected_total"] = len(payloads)
    await _write_reconcile_log(
        session, citation_ref=citation_ref, live_reconciled=True, mismatch=True,
        detail={"reason": "mismatch", "old_snapshot_id": snap.snapshot_id, "new_snapshot_id": new_sid,
                "live_hash": live_hash, "reanalyzable": len(payloads)})
    return out


def _run_reconcile_db(citation_ref: str, jurisdiction: str, live_hash: str) -> dict | None:
    """sync Celery 태스크에서 async DB 로직 실행 — 일회용 NullPool 엔진(교차-이벤트루프 무음실패 회피, INC-13).

    이미 실행 중 루프(async 컨텍스트)면 None(asyncio.run 불가). 실패는 로깅(무음0) 후 None.
    """
    import asyncio

    try:
        asyncio.get_running_loop()
        return None  # async 컨텍스트 → asyncio.run 불가 → skip(호출측이 표면화)
    except RuntimeError:
        pass  # 루프 없음(Celery 워커/sync) → 진행

    async def _go() -> dict:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.settings import settings
        eng = create_async_engine(settings.database_url, poolclass=NullPool)
        try:
            async with async_sessionmaker(eng, expire_on_commit=False)() as s:
                return await reconcile_mirror_db(
                    s, citation_ref=citation_ref, jurisdiction=jurisdiction, live_hash=live_hash)
        finally:
            await eng.dispose()

    try:
        return asyncio.run(_go())
    except Exception:
        # 무음0/정직 — DB/배선 실패를 삼키지 않고 표면화(reconcile 실패, 소비경로 무영향).
        _log.warning("reconcile DB 처리 실패(best-effort) — 배선/DB 점검 필요", exc_info=True)
        return None


@celery_app.task(name="verify.reconcile_mirror")
def reconcile_mirror(citation_ref: str, jurisdiction: str = "") -> dict:
    """라이브 재대조 → 미러 diff/갱신 → 영향 분석 재실행 트리거. 라이브 비활성/실패는 표면화(무음0)."""
    # citation_ref는 안전 인코딩(쿼리 파라미터 오염/URL 인젝션 방지).
    url = f"https://www.law.go.kr/reconcile?ref={urllib.parse.quote(citation_ref, safe='')}"
    try:
        raw = LiveNetwork().get(url)
        live_ok = True
    except NetworkError:
        raw = None
        live_ok = False

    result: dict = {"citation_ref": citation_ref, "jurisdiction": jurisdiction or None,
                    "live_reconciled": live_ok, "mismatch": False, "reanalyzed": 0,
                    "affected_total": 0, "reason": None}
    if not live_ok:
        result["reason"] = "live_disabled_or_failed"  # 라이브 비활성/실패 — 정합 미수행(표면화)
        return result

    db = _run_reconcile_db(citation_ref, jurisdiction, _body_hash(raw))
    if db is None:
        result["reason"] = "db_unavailable_or_async_ctx"  # DB 미접근/async 컨텍스트 — 표면화
        return result

    result["mismatch"] = db["mismatch"]
    result["reason"] = db["reason"]
    result["new_snapshot_id"] = db.get("new_snapshot_id")
    result["affected_total"] = db.get("affected_total", 0)

    # 미러 갱신 시: in-memory default_store도 최신 미러로 갱신(공급측 writer — 소비측 sync get이 최신을 읽음).
    new_snap = db.get("new_snapshot")
    if new_snap is not None:
        default_store().put(new_snap)

    # 영향 분석 재실행 트리거 — 새 미러(snapshot_id)로 동일입력 재실행. 중복 제거(같은 입력 1회) + 상한 절단.
    new_sid = db.get("new_snapshot_id")
    seen: set[str] = set()
    unique: list[dict] = []
    for payload in db.get("affected_payloads", []):
        repay = {**payload, "snapshot_id": new_sid} if new_sid else dict(payload)
        key = canonical(repay)
        if key in seen:
            continue
        seen.add(key)
        unique.append(repay)

    from app.settings import settings
    cap = settings.RECONCILE_MAX_REANALYZE
    if cap and len(unique) > cap:
        # 무음0 — 절단을 삼키지 않고 표면화(큐 폭주 방어).
        _log.warning("reconcile 재분석 디스패치 절단: unique=%d > cap=%d (관할=%s)",
                     len(unique), cap, jurisdiction)
        unique = unique[:cap]

    for repay in unique:
        reanalyze_task.delay(repay)
    result["reanalyzed"] = len(unique)
    return result


def _warm_mirror_best_effort(pnu: str) -> bool:
    """DB의 최신 미러를 in-memory default_store에 적재(다중워커 재분석이 stale 미러를 쓰지 않도록, H1).

    async 컨텍스트/실패 시 False(표면화) — run_analysis는 그대로 진행(미적재 보수 게이팅으로 degrade).
    """
    if not pnu:
        return False
    import asyncio

    try:
        asyncio.get_running_loop()
        return False
    except RuntimeError:
        pass

    async def _go() -> bool:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.settings import settings
        from app.supply.mirror.mirror_store import warm_mirror_from_db
        eng = create_async_engine(settings.database_url, poolclass=NullPool)
        try:
            async with async_sessionmaker(eng, expire_on_commit=False)() as s:
                return await warm_mirror_from_db(s, pnu)
        finally:
            await eng.dispose()

    try:
        return asyncio.run(_go())
    except Exception:
        _log.warning("재분석 미러 warm 실패(best-effort) — 배선/DB 점검 필요", exc_info=True)
        return False


def _persist_reanalysis_best_effort(result, payload: dict) -> bool:
    """재분석 결과를 analysis_run에 새 run으로 영속(input_payload 보존). 트리거가 계산만 하고 버리지 않음(H2).

    async 컨텍스트/실패 시 False(표면화). 기존 run은 불변(append) — lineage는 후속 범위(정직).
    """
    import asyncio

    try:
        asyncio.get_running_loop()
        return False
    except RuntimeError:
        pass

    async def _go() -> bool:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.services.pipeline.analysis_store import save_analysis
        from app.settings import settings
        eng = create_async_engine(settings.database_url, poolclass=NullPool)
        try:
            async with async_sessionmaker(eng, expire_on_commit=False)() as s:
                await save_analysis(s, result, input_payload=payload)
            return True
        finally:
            await eng.dispose()

    try:
        return asyncio.run(_go())
    except Exception:
        _log.warning("재분석 결과 영속 실패(best-effort) — 배선/DB 점검 필요", exc_info=True)
        return False


@celery_app.task(name="verify.reanalyze")
def reanalyze_task(payload: dict) -> dict:
    """reconcile 영향 분석 재실행 — DB 최신 미러 warm(H1) → 동일입력 분석(결정론) → 결과 영속(H2).

    run_analysis는 순수(항상 수행). warm/persist는 best-effort DB(NullPool, 교차루프 안전) — 실패 표면화.
    """
    from app.contracts.analysis import AnalysisInput
    from app.services.pipeline.analysis_pipeline import run_analysis

    warmed = _warm_mirror_best_effort(str(payload.get("pnu") or ""))
    result = run_analysis(AnalysisInput(**payload))
    persisted = _persist_reanalysis_best_effort(result, payload)
    return {"snapshot_id": result.snapshot_id, "input_hash": result.input_hash,
            "warmed": warmed, "persisted": persisted}


async def _distinct_jurisdictions_db(session) -> list[str]:
    """미러가 존재하는 distinct 관할 목록(주기 정합 대상). read-only."""
    from sqlalchemy import select

    from app.db.models.r2_models import MirrorSnapshotModel as M

    rows = (await session.execute(select(M.jurisdiction).distinct())).scalars().all()
    await session.rollback()
    return [j for j in rows if j]


def _distinct_jurisdictions() -> list[str]:
    """sync 진입 — 일회용 NullPool 엔진(INC-13 패턴). async 컨텍스트/실패 시 [](표면화)."""
    import asyncio

    try:
        asyncio.get_running_loop()
        return []
    except RuntimeError:
        pass

    async def _go() -> list[str]:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.settings import settings
        eng = create_async_engine(settings.database_url, poolclass=NullPool)
        try:
            async with async_sessionmaker(eng, expire_on_commit=False)() as s:
                return await _distinct_jurisdictions_db(s)
        finally:
            await eng.dispose()

    try:
        return asyncio.run(_go())
    except Exception:
        _log.warning("관할 enumerate 실패(best-effort) — 배선/DB 점검 필요", exc_info=True)
        return []


@celery_app.task(name="verify.reconcile_all")
def reconcile_all() -> dict:
    """주기 정합 fan-out — 미러 보유 관할마다 reconcile_mirror 디스패치(celery beat 진입점). 라이브 비활성이면
    각 reconcile가 표면화만 하고 종료(무음0)."""
    jurisdictions = _distinct_jurisdictions()
    dispatched = 0
    for j in jurisdictions:
        reconcile_mirror.delay(f"jurisdiction:{j}", j)
        dispatched += 1
    return {"jurisdictions": len(jurisdictions), "dispatched": dispatched}
