"""예산-실적 집행 원장 (설계도 §13 영속) — DisbursementEvent append-only 해시체인.

수지 라인아이템별 실제 지출(집행) 이벤트를 append-only로 누적해, 비용 지출 시 해당 항목의
기지출·미지출·집행률이 실시간 갱신되게 한다. analysis_ledger_service의 lazy-DDL + 해시체인
패턴을 재사용(재구현 최소).

★무결성(정통 해시체인): content_hash = sha256(정규화 이벤트 ‖ prev_hash ‖ seq) — 이전 해시를 입력에
접어넣어, 중간 행 변조 시 후행 전체가 깨지는 캐스케이드가 생긴다(행별 체크섬이 아님). 같은
(tenant_id, project_id, line_item_key) 체인 단위. verify_chain으로 재계산 대조.
★보안: tenant_id 스코프 — append/list 모두 tenant_id로 격리(형제 엔드포인트 tenant 소유권과 동일).
★동시성: 같은 체인 append는 pg_advisory_xact_lock으로 직렬화(prev_hash 포크 방지).
★deploy 안전: CREATE TABLE IF NOT EXISTS 자가 프로비저닝(analysis_ledger 패턴 — deploy.sh가 alembic
미실행이어도 첫 사용시 생성) + 모든 DB 접근 graceful(실패 시 빈 결과·수지 무손상).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_DDL = (
    "CREATE TABLE IF NOT EXISTS disbursement_events ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  tenant_id text,"
    "  project_id text NOT NULL,"
    "  line_item_key text NOT NULL,"
    "  seq int NOT NULL DEFAULT 1,"
    "  group_name text,"
    "  label text,"
    "  amount_won bigint NOT NULL,"
    "  event_date date,"
    "  memo text,"
    "  evidence text,"
    "  content_hash text NOT NULL,"
    "  prev_hash text,"
    "  created_by text,"
    "  created_at timestamptz DEFAULT now()"
    ")"
)
_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_disb_chain "
    "ON disbursement_events(tenant_id, project_id, line_item_key, seq)",
)


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _chain_hash(payload: Any, prev_hash: str | None, seq: int) -> str:
    """정통 해시체인: H(contentₙ ‖ prev_hashₙ₋₁ ‖ seq). prev를 접어넣어 캐스케이드 변조탐지."""
    material = f"{_canonical(payload)}|{prev_hash or 'genesis'}|{seq}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


async def _ensure(db) -> None:
    """테이블·인덱스 lazy 생성(멱등·additive·CREATE IF NOT EXISTS).

    ★analysis_ledger와 동일 패턴: 서비스가 첫 사용 시 자가 프로비저닝하므로 deploy.sh가 alembic을
    실행하지 않아도(또는 형식 마이그레이션 전이라도) 동작. 형식 alembic 마이그레이션은 분기 head
    (032~038 다중)를 `alembic heads`로 해소한 뒤 이 _DDL과 1:1로 사후 형식화 — 후속 증분.
    """
    from sqlalchemy import text

    await db.execute(text(_DDL))
    for ix in _IDX:
        await db.execute(text(ix))


async def append_disbursement(
    *,
    tenant_id: str | None,
    project_id: str,
    line_item_key: str,
    amount_won: int,
    group_name: str | None = None,
    label: str | None = None,
    event_date: str | None = None,
    memo: str | None = None,
    evidence: str | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    """집행 이벤트 1건 append(해시체인·tenant 스코프·동시성 직렬화). 실패 시 graceful({persisted:False})."""
    payload = {
        "tenant_id": tenant_id, "project_id": project_id, "line_item_key": line_item_key,
        "amount_won": amount_won, "event_date": event_date, "memo": memo, "evidence": evidence,
    }
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory

        async with async_session_factory() as db:
            await _ensure(db)
            # ★동시성: 같은 체인(tenant·project·line_item) append 직렬화 — prev_hash 포크 방지.
            await db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lk)::bigint)"),
                {"lk": f"disb:{tenant_id}:{project_id}:{line_item_key}"},
            )
            prev = (await db.execute(text(
                "SELECT content_hash, seq FROM disbursement_events "
                "WHERE tenant_id IS NOT DISTINCT FROM :t AND project_id=:p AND line_item_key=:k "
                "ORDER BY seq DESC LIMIT 1"
            ), {"t": tenant_id, "p": project_id, "k": line_item_key})).first()
            prev_hash = prev[0] if prev else None
            seq = (prev[1] + 1) if prev else 1
            chash = _chain_hash(payload, prev_hash, seq)
            await db.execute(text(
                "INSERT INTO disbursement_events"
                "(tenant_id, project_id, line_item_key, seq, group_name, label, amount_won,"
                " event_date, memo, evidence, content_hash, prev_hash, created_by)"
                " VALUES(:t,:p,:k,:s,:g,:l,:a,:d,:m,:e,:h,:ph,:cb)"
            ), {
                "t": tenant_id, "p": project_id, "k": line_item_key, "s": seq,
                "g": group_name, "l": label, "a": amount_won, "d": event_date,
                "m": memo, "e": evidence, "h": chash, "ph": prev_hash, "cb": created_by,
            })
            await db.commit()
        return {"persisted": True, "seq": seq, "content_hash": chash, "prev_hash": prev_hash}
    except Exception as e:  # noqa: BLE001 — DB 미가용은 무상태 폴백(집행추적 실패가 수지 무손상)
        logger.warning("disbursement_append_skip", error=str(e)[:160])
        return {"persisted": False, "reason": str(e)[:160]}


async def list_disbursements(tenant_id: str | None, project_id: str) -> dict[str, list[dict[str, Any]]]:
    """테넌트·프로젝트의 라인아이템별 집행 이벤트 {line_item_key: [{amount_won, event_date, ...}]}.

    실패/테이블 부재 시 빈 dict(graceful). tenant_id 스코프 — 타 테넌트 조회 불가.
    """
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory

        async with async_session_factory() as db:
            await _ensure(db)
            rows = (await db.execute(text(
                "SELECT line_item_key, amount_won, event_date, memo, evidence"
                " FROM disbursement_events"
                " WHERE tenant_id IS NOT DISTINCT FROM :t AND project_id=:p ORDER BY seq ASC"
            ), {"t": tenant_id, "p": project_id})).mappings().all()
        out: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            out.setdefault(r["line_item_key"], []).append({
                "amount_won": int(r["amount_won"]),
                "event_date": str(r["event_date"]) if r["event_date"] else None,
                "memo": r["memo"], "evidence": r["evidence"],
            })
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("disbursement_list_skip", error=str(e)[:160])
        return {}


async def verify_chain(tenant_id: str | None, project_id: str, line_item_key: str) -> dict[str, Any]:
    """해시체인 재계산 대조로 변조탐지. {ok, count, broken_at?}. 실패 시 graceful(ok=None)."""
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory

        async with async_session_factory() as db:
            await _ensure(db)
            rows = (await db.execute(text(
                "SELECT seq, amount_won, event_date, memo, evidence, content_hash, prev_hash"
                " FROM disbursement_events"
                " WHERE tenant_id IS NOT DISTINCT FROM :t AND project_id=:p AND line_item_key=:k"
                " ORDER BY seq ASC"
            ), {"t": tenant_id, "p": project_id, "k": line_item_key})).mappings().all()
        prev = None
        for r in rows:
            payload = {
                "tenant_id": tenant_id, "project_id": project_id, "line_item_key": line_item_key,
                "amount_won": int(r["amount_won"]),
                "event_date": str(r["event_date"]) if r["event_date"] else None,
                "memo": r["memo"], "evidence": r["evidence"],
            }
            expect = _chain_hash(payload, prev, r["seq"])
            if r["prev_hash"] != prev or r["content_hash"] != expect:
                return {"ok": False, "count": len(rows), "broken_at": r["seq"]}
            prev = r["content_hash"]
        return {"ok": True, "count": len(rows)}
    except Exception as e:  # noqa: BLE001
        logger.warning("disbursement_verify_skip", error=str(e)[:160])
        return {"ok": None, "reason": str(e)[:160]}
