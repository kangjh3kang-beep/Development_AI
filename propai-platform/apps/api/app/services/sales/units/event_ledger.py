"""세대 이벤트 원장 — 블록체인식 append-only 해시체인.

각 세대(동·호)에서 발생하는 모든 이벤트(동·호지정 대기/취소·계약 대기/취소·계약 체결·특이사항)를
'년월일 시분 + content_hash + prev_hash'로 영속한다. 세대별 체인(prev_hash=그 세대 직전 이벤트 해시)
이라 사후 변조탐지(verify)가 가능하고, 동·호추첨 결과·seed도 동일 원장에 기록해 공정성을 감사한다.

기존 SalesUnitStatusLog(상태전이 로그)는 보존하되, 본 원장은 '특이사항 메시지 + 모든 행위 이벤트 +
타임스탬프 + 해시체인'으로 한 단계 상위의 감사 가능 타임라인을 제공한다(추가·무손상).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
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
# 동일 프로세스 안에서 동시 첫 호출(코루틴 경합)을 1회로 합류시키는 락. _READY 게이트만으론
# 동시 첫 요청 2개가 둘 다 게이트를 통과해 DDL 을 중복 진입할 수 있다(asyncio.Lock 으로 합류).
_ensure_lock = asyncio.Lock()


# 런타임 DDL을 동시에 여러 워커가 실행할 때의 race(같은 IF NOT EXISTS 가 겹쳐 충돌)를 막기 위한
# advisory-lock 키. 트랜잭션 스코프(pg_advisory_xact_lock)라 commit/rollback 시 자동 해제된다.
# 정본(canonical)은 Alembic 마이그레이션(041_sales_unit_events_ledger.py)이며, _ensure 는 마이그레이션이
# 아직 적용되지 않은 환경(샌드박스 등)에서의 1회성 보강 + race 제거용 안전망이다.
_DDL_LOCK_KEY = 728_311_001


async def _ensure(db: AsyncSession | None = None) -> None:
    """세대 이벤트 원장 테이블/인덱스 멱등 보장(부팅 안전망) — 프로세스 1회만 실제 DDL 수행.

    ★[락 스코프·격리] 과거엔 세션 레벨 pg_advisory_lock + 수동 unlock 을 호출자 세션(db)에서 썼는데,
      Supabase pgbouncer(transaction pooling, database.py)에선 try 안의 commit() 이 물리 backend 를
      풀로 반환해 finally 의 unlock 이 '다른 backend' 에서 돌아 락이 누수(no-op)됐다. 이제 코드베이스
      표준(market._ensure / commission)대로 (1) 별도 단명 세션(async_session_factory)에서 (2) 트랜잭션
      스코프 advisory-lock(pg_advisory_xact_lock — commit/rollback 시 자동 해제, 풀링 backend 미스매치·
      commit 예외 시 unlock 추가예외로 원오류 은폐가 동시에 사라짐) 으로 DDL 을 직렬화한다. 호출자 세션
      (db)에서 DDL/commit 하면 같은 요청의 미커밋 쓰기가 휩쓸려 조기 부분커밋 되므로 격리한다. 인자 db 는
      하위호환 위해 받지만 사용하지 않는다(별도 세션으로 DDL 수행).
    동시 부팅(멀티프로세스) race 는 advisory-lock 으로, 동일 프로세스 코루틴 경합은 asyncio.Lock 으로 막는다.
    """
    global _READY
    if _READY:  # 이미 보장됨 → DB 왕복 없이 즉시 반환.
        return
    async with _ensure_lock:  # 동시 첫 호출(코루틴 경합)을 1회로 합류.
        if _READY:
            return
        # ★별도 단명 세션 — 호출자 세션(db)의 미커밋 쓰기를 휩쓸지 않도록 DDL/commit 을 격리.
        from app.core.database import async_session_factory  # noqa: PLC0415
        async with async_session_factory() as ddl_db:
            # advisory-lock: 트랜잭션 종료(commit/rollback) 시 자동 해제(누수 없음).
            await ddl_db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _DDL_LOCK_KEY})
            await ddl_db.execute(text(_DDL))
            await ddl_db.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_unit_events_unit ON sales_unit_events(unit_id, seq)"))
            await ddl_db.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_unit_events_site ON sales_unit_events(site_id, occurred_at)"))
            await ddl_db.commit()
        _READY = True  # 성공 시에만 게이트 닫음(실패 시 다음 호출이 재시도).


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
                       message: str | None = None, by=None, meta: dict | None = None,
                       do_commit: bool = True) -> dict[str, Any]:
    """세대 이벤트를 원장에 append(해시체인). 같은 세대의 직전 이벤트 해시를 prev_hash로 잇는다.

    do_commit=False 이면 INSERT만 하고 커밋하지 않는다 — 호출부(상태전이·추첨)가 세대 UPDATE와
    이벤트 기록을 '한 트랜잭션'으로 묶어 한 번에 커밋하기 위함(상태는 안 바뀌었는데 원장엔 전이
    기록이 남는 원자성 붕괴를 막는다). do_commit=True(기본)는 단독 호출 시의 기존 동작 유지.
    """
    await _ensure(db)
    uid = str(unit_id)
    # ★[correctness·해시체인 fork 방지] 같은 세대에 두 이벤트가 동시에 append 되면, 둘 다 직전 seq(N)을
    #   읽고 둘 다 seq=N+1·동일 prev_hash 로 INSERT 를 시도한다(체인 fork). UNIQUE(unit_id,seq)가 한쪽을
    #   막지만 진 쪽은 IntegrityError(500)로 터진다. 트랜잭션 스코프 advisory-lock(같은 unit 키)으로 두
    #   append 를 직렬화하면, 뒤 트랜잭션은 앞 트랜잭션 커밋까지 대기 → 갱신된 seq(N+1)을 읽어 seq=N+2 로
    #   잇는다. xact 락이라 commit/rollback 시 자동 해제(누수 없음). 2개 인자(site,unit) 해시로 키 분산.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:u, 0))"), {"u": uid})
    last = (await db.execute(text(
        "SELECT seq, content_hash FROM sales_unit_events WHERE unit_id=:u ORDER BY seq DESC LIMIT 1"),
        {"u": uid})).first()
    seq = (int(last[0]) + 1) if last else 1
    prev_hash = last[1] if last else None
    occurred_dt = datetime.now(UTC)          # timestamptz 컬럼용 datetime(asyncpg 네이티브)
    occurred_at = occurred_dt.isoformat()              # 해시·occurred_iso 용 정확한 문자열
    chash = _hash(prev_hash, uid, seq, event_type, to_status, message, occurred_at, meta)
    await db.execute(text(
        "INSERT INTO sales_unit_events (site_id, unit_id, seq, event_type, from_status, to_status, "
        "  message, meta, created_by, occurred_at, occurred_iso, content_hash, prev_hash) "
        "VALUES (:s,:u,:seq,:et,:fs,:ts,:msg,CAST(:meta AS jsonb),:by,:dt,:iso,:ch,:ph)"),
        {"s": str(site_id), "u": uid, "seq": seq, "et": event_type, "fs": from_status, "ts": to_status,
         "msg": message, "meta": json.dumps(meta, ensure_ascii=False) if meta else None,
         "by": str(by) if by else None, "dt": occurred_dt, "iso": occurred_at, "ch": chash, "ph": prev_hash})
    if do_commit:
        await db.commit()
    return {"seq": seq, "content_hash": chash, "prev_hash": prev_hash, "occurred_at": occurred_at}


async def unit_timeline(db: AsyncSession, unit_id, site_id=None) -> list[dict[str, Any]]:
    """세대 1곳의 이벤트 타임라인(오름차순) — 프론트 타임라인 표시용.

    ★[security·IDOR] site_id 가 주어지면 WHERE 에 site_id=:s 를 더해 '그 현장의 그 세대' 이벤트만
      돌려준다(교차테넌트 원장 열람 차단). site_id 가 None 이면(내부 호출·테스트) 세대 단위로만 조회한다.
    """
    await _ensure(db)
    sql = ("SELECT seq, event_type, from_status, to_status, message, meta, created_by, occurred_at, content_hash "
           "FROM sales_unit_events WHERE unit_id=:u")
    params: dict[str, Any] = {"u": str(unit_id)}
    if site_id is not None:
        sql += " AND site_id=:s"
        params["s"] = str(site_id)
    sql += " ORDER BY seq ASC"
    rows = (await db.execute(text(sql), params)).all()
    out = []
    for r in rows:
        out.append({
            "seq": int(r[0]), "event_type": r[1], "event_label": EVENT_TYPES.get(r[1], r[1]),
            "from_status": r[2], "to_status": r[3], "message": r[4],
            "meta": r[5], "by": str(r[6]) if r[6] else None,
            "occurred_at": str(r[7]), "content_hash": r[8],
        })
    return out


async def verify_chain(db: AsyncSession, unit_id, site_id=None) -> dict[str, Any]:
    """세대 이벤트 체인 무결성 검증 — content_hash 재계산이 저장값과 모두 일치하는지(변조탐지).

    ★[security·IDOR] site_id 가 주어지면 WHERE 에 site_id=:s 를 더해 '그 현장의 그 세대' 체인만
      검증한다(교차테넌트 원장 검증 차단). site_id 가 None 이면(내부 호출·테스트) 세대 단위로만 조회.

    ★[탐지 범위·정직] 본 검증은 (1) content_hash 변조 (2) prev_hash 단절 (3) seq 단조성 위반(중간 행
      삭제·재정렬·중복)을 적발한다. 단, '끝에서 잘라낸 tail-truncation'(가장 최근 N개 이벤트를 통째로
      삭제)은 앵커(현장/세대별 기대 head seq 영속) 없이 해시체인 자체로는 self-탐지가 불가능하다 —
      잘린 뒤 남은 1..k 행은 여전히 정합이라 {valid:True} 로 보인다. tail-truncation 실탐지는 외부
      앵커 교차검증이 필요하며 backlog 로 이연한다(여기선 한계를 정직히 명시하고 미구현으로 둔다).
    """
    await _ensure(db)
    sql = ("SELECT seq, event_type, to_status, message, meta, occurred_iso, content_hash, prev_hash "
           "FROM sales_unit_events WHERE unit_id=:u")
    params: dict[str, Any] = {"u": str(unit_id)}
    if site_id is not None:
        sql += " AND site_id=:s"
        params["s"] = str(site_id)
    sql += " ORDER BY seq ASC"
    rows = (await db.execute(text(sql), params)).all()
    prev = None
    expected_seq = 1  # 세대 체인 seq 는 1,2,3...(append 가 단조 증가로 부여).
    for r in rows:
        seq, et, ts, msg, meta, at_iso, stored, ph = int(r[0]), r[1], r[2], r[3], r[4], r[5], r[6], r[7]
        # ★[변조탐지] seq 단조성 검사 — 중간 행 삭제(누락)·재정렬·중복으로 seq 가 1,2,3 연속이 아니게
        #   되면 즉시 깨진 것으로 본다(끝잘림 tail-truncation 은 docstring 명시대로 앵커 없이 미탐지).
        if seq != expected_seq:
            return {"valid": False, "broken_at": seq, "reason": "seq 누락·재정렬(단조성 위반)"}
        if (ph or None) != (prev or None):
            return {"valid": False, "broken_at": seq, "reason": "prev_hash 불일치"}
        recalc = _hash(prev, str(unit_id), seq, et, ts, msg, at_iso,
                       meta if isinstance(meta, dict) else (json.loads(meta) if meta else None))
        if recalc != stored:
            return {"valid": False, "broken_at": seq, "reason": "content_hash 불일치(변조)"}
        prev = stored
        expected_seq += 1
    return {"valid": True, "events": len(rows)}
