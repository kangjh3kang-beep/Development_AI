"""Phase1-C 세대(동호수) 실시간 선점 동시성 — DB 원자 조건부 UPDATE를 SSOT로.

★설계 결정(정직)
  프로덕션 Redis가 health상 unhealthy로 불확실하므로 **Redis 없이도 정확성 보장**한다.
  단일행 원자 UPDATE의 WHERE 조건이 race를 막는다(2직원 동시 hold → 정확히 1행 RETURNING).
  Redis는 보조(있으면 짧은 락으로 DB부하 경감)이며 연결실패시 graceful 폴백한다.
  절대 Redis를 정확성에 의존하지 않는다.

상태 모델(sales_unit_inventory.status)
  AVAILABLE → HOLD → CONTRACTED(확정) / CANCELLED
  만료된 HOLD(hold_expires_at < now())는 조회·선점시 AVAILABLE로 취급(lazy expire).

신규 컬럼(멱등 ALTER, ensure_unit_concurrency_columns)
  held_by uuid           : 임시선점한 직원(staff/user) id
  hold_expires_at timestamptz : 선점 만료시각(now()+5min)
  hold_token text        : 선점 토큰(release/reserve 본인검증)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 임시선점 TTL(분). 좌석예약형 기본 5분.
HOLD_TTL_MINUTES = 5

# 동시성 컬럼/인덱스 보강을 프로세스당 1회만 하기 위한 플래그(매 요청마다 ALTER 재실행 방지).
_COLUMNS_READY = False
# 동일 프로세스 안에서 동시 첫 호출(코루틴 경합)을 1회로 합류시키는 락(_COLUMNS_READY 게이트만으론
# 동시 첫 요청 2개가 둘 다 통과해 DDL 을 중복 진입할 수 있다).
_columns_lock = asyncio.Lock()
# 여러 워커가 동시에 ALTER/CREATE INDEX 를 실행할 때의 DDL race 를 막는 advisory-lock 키.
# 트랜잭션 스코프(pg_advisory_xact_lock)라 commit/rollback 시 자동 해제된다.
# 정본(canonical)은 Alembic 마이그레이션이며, 본 함수는 마이그레이션 미적용 환경의 1회성 보강 안전망이다.
_DDL_LOCK_KEY = 728_311_002


# ── 멱등 스키마 보강 ──────────────────────────────────────────────────────────
async def ensure_unit_concurrency_columns(db: AsyncSession | None = None) -> None:
    """sales_unit_inventory 에 선점 동시성 컬럼을 멱등 추가(프로세스당 1회 + DDL race 제거).

    기존 status/hold_id/contract_id 컬럼은 그대로 두고, 본 Phase에 필요한
    held_by/hold_expires_at/hold_token 만 보강한다. (project_id|site_id, unit_no)
    대신 본 스키마는 (site_id, dong, ho) 가 동호 유니크의 자연키이므로 부분 유니크
    인덱스(WHERE deleted_at IS NULL)로 1세대 1행을 보강한다.

    ★[락 스코프·격리] 과거엔 호출자 세션(db)에서 세션 레벨 pg_advisory_lock + 수동 unlock 을 썼는데,
      Supabase pgbouncer(transaction pooling, database.py)에선 try 안의 commit() 이 물리 backend 를
      풀로 반환해 finally 의 unlock 이 '다른 backend' 에서 돌아 락이 누수(no-op)됐다. 이제 코드베이스
      표준(market._ensure / commission)대로 (1) 별도 단명 세션(async_session_factory)에서 (2) 트랜잭션
      스코프 advisory-lock(pg_advisory_xact_lock — commit/rollback 시 자동 해제) 으로 DDL 을 직렬화한다.
      호출자 세션에서 DDL/commit 하면 같은 요청의 미커밋 쓰기가 조기 부분커밋 되므로 격리한다(인자 db 는
      하위호환 위해 받지만 사용하지 않는다). 동일 프로세스 코루틴 경합은 asyncio.Lock 으로 합류한다.
    """
    global _COLUMNS_READY
    if _COLUMNS_READY:  # 이미 보장됨 → DB 왕복 없이 즉시 반환.
        return
    async with _columns_lock:  # 동시 첫 호출(코루틴 경합)을 1회로 합류.
        if _COLUMNS_READY:
            return
        # ★별도 단명 세션 — 호출자 세션(db)의 미커밋 쓰기를 휩쓸지 않도록 DDL/commit 을 격리.
        from app.core.database import async_session_factory  # noqa: PLC0415
        async with async_session_factory() as ddl_db:
            # advisory-lock: 트랜잭션 종료(commit/rollback) 시 자동 해제(누수 없음).
            await ddl_db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _DDL_LOCK_KEY})
            await ddl_db.execute(text(
                "ALTER TABLE sales_unit_inventory "
                "ADD COLUMN IF NOT EXISTS held_by uuid, "
                "ADD COLUMN IF NOT EXISTS hold_expires_at timestamptz, "
                "ADD COLUMN IF NOT EXISTS hold_token text"
            ))
            # status 기본값 보강(기존 server_default='AVAILABLE'와 동일, 누락행 정리)
            await ddl_db.execute(text(
                "UPDATE sales_unit_inventory SET status = 'AVAILABLE' WHERE status IS NULL"
            ))
            # 1세대(동·호) 1행 — 동호 유니크(확정 1호1계약의 물리적 토대). 부분 유니크.
            await ddl_db.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_unit_inventory_site_dong_ho "
                "ON sales_unit_inventory (site_id, dong, ho) WHERE deleted_at IS NULL"
            ))
            # 보드 조회 가속(현장별 status).
            await ddl_db.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_unit_inventory_site_status "
                "ON sales_unit_inventory (site_id, status)"
            ))
            await ddl_db.commit()
        _COLUMNS_READY = True  # 성공 시에만 게이트 닫음(실패 시 다음 호출이 재시도).


# ── Redis 보조(있으면 가속, 없으면 graceful 폴백) ─────────────────────────────
async def _redis():
    """redis 클라이언트(연결가능시) 또는 None. 정확성은 DB가 보장하므로 실패시 무시."""
    try:
        import redis.asyncio as aioredis  # noqa: PLC0415

        from app.core.config import settings  # noqa: PLC0415

        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=0.5,
                                   socket_timeout=0.5)
        await client.ping()
        return client
    except Exception as exc:  # noqa: BLE001
        logger.info("unit-concurrency: Redis 미사용(폴백, DB-SSOT) — %s", exc)
        return None


async def _redis_try_lock(unit_id: str) -> tuple[object | None, bool]:
    """짧은 보조락(SET NX EX). (client, acquired). Redis 없으면 (None, True)=통과."""
    client = await _redis()
    if client is None:
        return None, True
    try:
        ok = await client.set(f"unitlock:{unit_id}", "1", nx=True, ex=3)
        return client, bool(ok)
    except Exception:  # noqa: BLE001
        return None, True  # 락 실패는 DB가 막으므로 통과


async def _redis_unlock(client: object | None, unit_id: str) -> None:
    if client is None:
        return
    # 보조락 해제 실패는 무해(TTL 로 자연만료). 정확성은 DB 가 보장하므로 조용히 무시.
    with contextlib.suppress(Exception):
        await client.delete(f"unitlock:{unit_id}")  # type: ignore[attr-defined]


async def _redis_publish(channel: str, payload: dict) -> None:
    """pub/sub 브로드캐스트(worker>1 백플레인 보조). 실패 무시."""
    import json  # noqa: PLC0415

    client = await _redis()
    if client is None:
        return
    # pub/sub 브로드캐스트 실패는 무해(인프로세스 WS 가 정본). 조용히 무시.
    with contextlib.suppress(Exception):
        await client.publish(channel, json.dumps(payload, default=str))  # type: ignore[attr-defined]


# ── 원자 선점/해제/확정(DB-SSOT) ──────────────────────────────────────────────
async def atomic_hold(db: AsyncSession, site_id, unit_id, held_by, ttl_minutes: int = HOLD_TTL_MINUTES):
    """원자 조건부 UPDATE로 임시선점.

    WHERE: 같은 현장의 해당 세대가 (AVAILABLE) 이거나 (HOLD이지만 만료된) 경우에만 성공.
    → 두 직원이 동시에 호출해도 단일행 UPDATE는 직렬화되어 정확히 1건만 RETURNING.
    반환: 성공시 row(hold_token, hold_expires_at), 실패시 None.
    """
    token = uuid.uuid4().hex
    row = (await db.execute(text(
        "UPDATE sales_unit_inventory SET "
        "  status = 'HOLD', held_by = :u, "
        "  hold_expires_at = now() + (:ttl || ' minutes')::interval, "
        "  hold_token = :t "
        "WHERE id = :id AND site_id = :s AND deleted_at IS NULL "
        "  AND ( status = 'AVAILABLE' "
        "        OR (status = 'HOLD' AND (hold_expires_at IS NULL OR hold_expires_at < now())) ) "
        "RETURNING id, hold_token, hold_expires_at"
    ), {"u": str(held_by), "t": token, "ttl": str(int(ttl_minutes)),
        "id": str(unit_id), "s": str(site_id)})).mappings().first()
    return row


async def atomic_release(db: AsyncSession, site_id, unit_id, held_by, hold_token: str | None = None):
    """본인 HOLD 해제 → AVAILABLE. 토큰 주어지면 토큰까지 일치해야 해제(타인 토큰 차단)."""
    params = {"u": str(held_by), "id": str(unit_id), "s": str(site_id)}
    token_cond = ""
    if hold_token:
        token_cond = " AND hold_token = :t"
        params["t"] = hold_token
    row = (await db.execute(text(
        "UPDATE sales_unit_inventory SET "
        "  status = 'AVAILABLE', held_by = NULL, hold_expires_at = NULL, hold_token = NULL "
        "WHERE id = :id AND site_id = :s AND status = 'HOLD' AND held_by = :u" + token_cond +
        " RETURNING id"
    ), params)).mappings().first()
    return row


async def atomic_reserve(db: AsyncSession, site_id, unit_id, held_by, hold_token: str):
    """확정(계약 직전 동호 점유) — HOLD & 본인 & 미만료 & 토큰일치 → CONTRACTED.

    만료된 hold(hold_expires_at < now())는 RETURNING 0행 → 호출측에서 409.
    status='CONTRACTED' 전이 + (site,dong,ho) 유니크가 영구 1호1계약을 물리 보장한다.
    """
    # ★[보강·iter-7 MED correctness] 확정(CONTRACTED) 시 임시선점 메타(held_by/hold_token/
    #   hold_expires_at)도 함께 NULL 로 정리한다 — 확정된 세대에 만료된 선점 흔적이 남아 감사·디버깅을
    #   혼동시키지 않게. create_contract(HOLD→RESERVED)의 정리와 일관(두 확정 경로 동일 거동).
    row = (await db.execute(text(
        "UPDATE sales_unit_inventory SET "
        "  status = 'CONTRACTED', held_by = NULL, hold_token = NULL, hold_expires_at = NULL "
        "WHERE id = :id AND site_id = :s AND status = 'HOLD' AND held_by = :u "
        "  AND hold_token = :t AND hold_expires_at IS NOT NULL AND hold_expires_at >= now() "
        "RETURNING id, dong, ho"
    ), {"u": str(held_by), "t": hold_token, "id": str(unit_id), "s": str(site_id)})).mappings().first()
    return row


async def current_status(db: AsyncSession, site_id, unit_id):
    """단건 현재 상태(lazy expire 반영). held_by/만료시각 포함."""
    row = (await db.execute(text(
        "SELECT id, status, held_by, hold_expires_at, "
        "  (status = 'HOLD' AND (hold_expires_at IS NULL OR hold_expires_at < now())) AS expired "
        "FROM sales_unit_inventory WHERE id = :id AND site_id = :s"
    ), {"id": str(unit_id), "s": str(site_id)})).mappings().first()
    return row


async def board_rows(db: AsyncSession, site_id):
    """보드 전체 세대 status. 만료된 HOLD는 effective_status='AVAILABLE'(lazy expire)."""
    rows = (await db.execute(text(
        "SELECT id, dong, ho, floor, line, type_id, status, held_by, hold_expires_at, "
        "  CASE WHEN status = 'HOLD' AND (hold_expires_at IS NULL OR hold_expires_at < now()) "
        "       THEN 'AVAILABLE' ELSE status END AS effective_status "
        "FROM sales_unit_inventory "
        "WHERE site_id = :s AND deleted_at IS NULL "
        "ORDER BY dong NULLS LAST, floor NULLS LAST, ho NULLS LAST"
    ), {"s": str(site_id)})).mappings().all()
    return rows
