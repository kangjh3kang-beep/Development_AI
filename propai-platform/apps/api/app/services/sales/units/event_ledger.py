"""세대 이벤트 원장 — 블록체인식 append-only 해시체인.

각 세대(동·호)에서 발생하는 모든 이벤트(동·호지정 대기/취소·계약 대기/취소·계약 체결·특이사항)를
'년월일 시분 + content_hash + prev_hash'로 영속한다. 세대별 체인(prev_hash=그 세대 직전 이벤트 해시)
이라 사후 변조탐지(verify)가 가능하고, 동·호추첨 결과·seed도 동일 원장에 기록해 공정성을 감사한다.

기존 SalesUnitStatusLog(상태전이 로그)는 보존하되, 본 원장은 '특이사항 메시지 + 모든 행위 이벤트 +
타임스탬프 + 해시체인'으로 한 단계 상위의 감사 가능 타임라인을 제공한다(추가·무손상).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 이벤트 유형(한글 라벨은 프론트에서). 상태전이형 + 특이사항(NOTE) + 추첨(DRAW).
EVENT_TYPES = {
    "HOLD_REQUEST": "동·호지정 대기",
    "HOLD_CANCEL": "동·호지정 취소",
    "CONTRACT_WAIT": "계약 대기",
    "CONTRACT_CANCEL": "계약 취소",
    "CONTRACT_SIGN": "계약 체결",
    "NOTE": "특이사항",
    "DRAW_ASSIGN": "추첨 배정",
}

_DDL = (
    "CREATE TABLE IF NOT EXISTS sales_unit_events ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  site_id uuid NOT NULL,"
    "  unit_id uuid NOT NULL,"
    "  seq integer NOT NULL,"                    # 세대별 1,2,3...
    "  event_type varchar(20) NOT NULL,"
    "  from_status varchar(20),"
    "  to_status varchar(20),"
    "  message text,"
    "  meta jsonb,"                               # 추첨 seed·그룹 등 부가정보
    "  created_by uuid,"
    "  occurred_at timestamptz NOT NULL DEFAULT now(),"
    "  occurred_iso varchar(40) NOT NULL,"        # 해시에 쓴 정확한 iso(검증 결정성)
    "  content_hash varchar(64) NOT NULL,"
    "  prev_hash varchar(64),"
    "  UNIQUE (unit_id, seq)"
    ")"
)
_READY = False


async def _ensure(db: AsyncSession) -> None:
    global _READY
    if _READY:
        return
    await db.execute(text(_DDL))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_unit_events_unit ON sales_unit_events(unit_id, seq)"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_unit_events_site ON sales_unit_events(site_id, occurred_at)"))
    await db.commit()
    _READY = True


def _hash(prev_hash: str | None, unit_id: str, seq: int, event_type: str,
          to_status: str | None, message: str | None, occurred_at: str, meta: dict | None) -> str:
    """content_hash = sha256(prev_hash + 핵심 페이로드). 체인 변조 시 후속 해시 전부 불일치."""
    payload = json.dumps({
        "prev": prev_hash or "", "unit": unit_id, "seq": seq, "type": event_type,
        "to": to_status or "", "msg": message or "", "at": occurred_at,
        "meta": meta or {},
    }, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def append_event(db: AsyncSession, site_id, unit_id, event_type: str,
                       from_status: str | None = None, to_status: str | None = None,
                       message: str | None = None, by=None, meta: dict | None = None) -> dict[str, Any]:
    """세대 이벤트를 원장에 append(해시체인). 같은 세대의 직전 이벤트 해시를 prev_hash로 잇는다."""
    await _ensure(db)
    uid = str(unit_id)
    last = (await db.execute(text(
        "SELECT seq, content_hash FROM sales_unit_events WHERE unit_id=:u ORDER BY seq DESC LIMIT 1"),
        {"u": uid})).first()
    seq = (int(last[0]) + 1) if last else 1
    prev_hash = last[1] if last else None
    occurred_dt = datetime.now(timezone.utc)          # timestamptz 컬럼용 datetime(asyncpg 네이티브)
    occurred_at = occurred_dt.isoformat()              # 해시·occurred_iso 용 정확한 문자열
    chash = _hash(prev_hash, uid, seq, event_type, to_status, message, occurred_at, meta)
    await db.execute(text(
        "INSERT INTO sales_unit_events (site_id, unit_id, seq, event_type, from_status, to_status, "
        "  message, meta, created_by, occurred_at, occurred_iso, content_hash, prev_hash) "
        "VALUES (:s,:u,:seq,:et,:fs,:ts,:msg,CAST(:meta AS jsonb),:by,:dt,:iso,:ch,:ph)"),
        {"s": str(site_id), "u": uid, "seq": seq, "et": event_type, "fs": from_status, "ts": to_status,
         "msg": message, "meta": json.dumps(meta, ensure_ascii=False) if meta else None,
         "by": str(by) if by else None, "dt": occurred_dt, "iso": occurred_at, "ch": chash, "ph": prev_hash})
    await db.commit()
    return {"seq": seq, "content_hash": chash, "prev_hash": prev_hash, "occurred_at": occurred_at}


async def unit_timeline(db: AsyncSession, unit_id) -> list[dict[str, Any]]:
    """세대 1곳의 이벤트 타임라인(오름차순) — 프론트 타임라인 표시용."""
    await _ensure(db)
    rows = (await db.execute(text(
        "SELECT seq, event_type, from_status, to_status, message, meta, created_by, occurred_at, content_hash "
        "FROM sales_unit_events WHERE unit_id=:u ORDER BY seq ASC"), {"u": str(unit_id)})).all()
    out = []
    for r in rows:
        out.append({
            "seq": int(r[0]), "event_type": r[1], "event_label": EVENT_TYPES.get(r[1], r[1]),
            "from_status": r[2], "to_status": r[3], "message": r[4],
            "meta": r[5], "by": str(r[6]) if r[6] else None,
            "occurred_at": str(r[7]), "content_hash": r[8],
        })
    return out


async def verify_chain(db: AsyncSession, unit_id) -> dict[str, Any]:
    """세대 이벤트 체인 무결성 검증 — content_hash 재계산이 저장값과 모두 일치하는지(변조탐지)."""
    await _ensure(db)
    rows = (await db.execute(text(
        "SELECT seq, event_type, to_status, message, meta, occurred_iso, content_hash, prev_hash "
        "FROM sales_unit_events WHERE unit_id=:u ORDER BY seq ASC"), {"u": str(unit_id)})).all()
    prev = None
    for r in rows:
        seq, et, ts, msg, meta, at_iso, stored, ph = int(r[0]), r[1], r[2], r[3], r[4], r[5], r[6], r[7]
        if (ph or None) != (prev or None):
            return {"valid": False, "broken_at": seq, "reason": "prev_hash 불일치"}
        recalc = _hash(prev, str(unit_id), seq, et, ts, msg, at_iso,
                       meta if isinstance(meta, dict) else (json.loads(meta) if meta else None))
        if recalc != stored:
            return {"valid": False, "broken_at": seq, "reason": "content_hash 불일치(변조)"}
        prev = stored
    return {"valid": True, "events": len(rows)}
