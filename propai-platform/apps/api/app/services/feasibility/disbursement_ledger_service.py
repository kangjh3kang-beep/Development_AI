"""예산-실적 집행 원장 (설계도 §13 영속) — DisbursementEvent append-only 해시체인.

수지 라인아이템별 실제 지출(집행) 이벤트를 append-only로 누적해, 비용 지출 시 해당 항목의
기지출·미지출·집행률이 실시간 갱신되게 한다. analysis_ledger_service의 lazy-DDL + 해시체인
패턴을 재사용(재구현 최소).

★무결성: content_hash = sha256(정규화 이벤트), prev_hash = 같은 (project_id,line_item_key) 체인의
직전 해시 → 변조탐지(감사추적: 누가·언제·얼마).
★deploy 안전: CREATE TABLE IF NOT EXISTS 자가 프로비저닝(deploy.sh가 alembic 미실행이어도 첫 사용시
테이블 생성) + 모든 DB 접근 graceful(실패 시 빈 결과 — 상위 /budget-execution 무상태 폴백 유지).
★무목업: 증빙(evidence) 없는 이벤트도 저장하되 기록으로만(임의 반영은 상위 UI 게이트).
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
    "  project_id text NOT NULL,"
    "  line_item_key text NOT NULL,"
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
    "ON disbursement_events(project_id, line_item_key, created_at)",
)


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _content_hash(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


async def _ensure(db) -> None:
    """테이블·인덱스 lazy 생성(멱등·additive·CREATE IF NOT EXISTS).

    ★analysis_ledger와 동일 패턴: 서비스가 첫 사용 시 자가 프로비저닝하므로 deploy.sh가 alembic을
    실행하지 않아도(또는 형식 마이그레이션 전이라도) 동작한다. 형식 alembic 마이그레이션은 분기된
    head(032~038 다중)를 `alembic heads`로 해소한 뒤 이 _DDL과 1:1로 사후 형식화(analysis_ledger가
    031로 그랬듯) — 후속 증분.
    """
    from sqlalchemy import text

    await db.execute(text(_DDL))
    for ix in _IDX:
        await db.execute(text(ix))


async def append_disbursement(
    *,
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
    """집행 이벤트 1건 append(해시체인). 실패 시 graceful({persisted: False})."""
    payload = {
        "project_id": project_id, "line_item_key": line_item_key,
        "amount_won": int(amount_won), "event_date": event_date,
        "memo": memo, "evidence": evidence,
    }
    chash = _content_hash(payload)
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory

        async with async_session_factory() as db:
            await _ensure(db)
            prev = (await db.execute(text(
                "SELECT content_hash FROM disbursement_events "
                "WHERE project_id=:p AND line_item_key=:k ORDER BY created_at DESC LIMIT 1"
            ), {"p": project_id, "k": line_item_key})).scalar()
            await db.execute(text(
                "INSERT INTO disbursement_events"
                "(project_id, line_item_key, group_name, label, amount_won, event_date,"
                " memo, evidence, content_hash, prev_hash, created_by)"
                " VALUES(:p,:k,:g,:l,:a,:d,:m,:e,:h,:ph,:cb)"
            ), {
                "p": project_id, "k": line_item_key, "g": group_name, "l": label,
                "a": int(amount_won), "d": event_date, "m": memo, "e": evidence,
                "h": chash, "ph": prev, "cb": created_by,
            })
            await db.commit()
        return {"persisted": True, "content_hash": chash, "prev_hash": prev}
    except Exception as e:  # noqa: BLE001 — DB 미가용은 무상태 폴백(집행추적 실패가 수지 무손상)
        logger.warning("disbursement_append_skip", error=str(e)[:160])
        return {"persisted": False, "content_hash": chash, "reason": str(e)[:160]}


async def list_disbursements(project_id: str) -> dict[str, list[dict[str, Any]]]:
    """프로젝트의 라인아이템별 집행 이벤트 목록 {line_item_key: [{amount_won, event_date, ...}]}.

    실패/테이블 부재 시 빈 dict(graceful) → 상위는 예산만으로 무상태 계산.
    """
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory

        async with async_session_factory() as db:
            await _ensure(db)
            rows = (await db.execute(text(
                "SELECT line_item_key, amount_won, event_date, memo, evidence, created_at"
                " FROM disbursement_events WHERE project_id=:p ORDER BY created_at ASC"
            ), {"p": project_id})).mappings().all()
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
