"""Phase1-C 세대(동호수) 실시간 선점 동시성 엔드포인트(prefix=/api/v1/sales).

DB 원자 조건부 UPDATE(SSOT)로 동시 hold 중 정확히 1명만 임시선점, 확정(reserve)은
영구 1호1계약 보장. site별 보드 구독자에게 hold/release/reserve 를 WS 브로드캐스트.

엔드포인트
  POST /units/{id}/hold      → {hold_token, expires_at} | 409 {current_status, held_by_me}
  POST /units/{id}/release   → {released} | 409
  POST /units/{id}/reserve   → {reserved, contract?} | 409(만료/타인/미보유)
  GET  /units/board          → 전 세대 status(만료 HOLD는 available 표시, held_by 마스킹)
실시간: 기존 /ws/sales/{channel_id} (channel_id = board:{site_id}) 채널 재사용.
"""

import uuid
from datetime import datetime, timezone, UTC

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_sales import SalesCtx, sales_ctx
from app.services.sales.mh.ws import ws_manager
from app.services.sales.units.concurrency import (
    HOLD_TTL_MINUTES,
    atomic_hold,
    atomic_release,
    atomic_reserve,
    board_rows,
    current_status,
    ensure_unit_concurrency_columns,
    _redis_publish,
)

units_live_router = APIRouter(tags=["sales-units-live"])


def _board_channel(site_id) -> str:
    return f"board:{site_id}"


async def _broadcast(site_id, event: str, unit_id, status: str, held_by=None, expires_at=None):
    """site 보드 구독자에게 상태변경 push(인프로세스 WS + Redis pub/sub 보조)."""
    payload = {
        "type": "UNIT_STATUS",
        "event": event,  # HOLD|RELEASE|RESERVE|EXPIRE
        "unit_id": str(unit_id),
        "status": status,
        "held_by": str(held_by) if held_by else None,  # 보드 표시용(상세는 GET에서 마스킹)
        "expires_at": expires_at.isoformat() if isinstance(expires_at, datetime) else expires_at,
        "ts": datetime.now(UTC).isoformat(),
    }
    channel = _board_channel(site_id)
    await ws_manager.broadcast(channel, payload)  # 단일워커 인프로세스
    await _redis_publish(f"sales:{channel}", payload)  # worker>1 백플레인 보조(있으면)


class HoldBody(BaseModel):
    minutes: int | None = None
    staff_id: uuid.UUID | None = None      # 선점한 직원(감사용)
    customer_id: uuid.UUID | None = None   # 선점 대상 고객(감사용)


class ReleaseBody(BaseModel):
    hold_token: str | None = None


class ReserveBody(BaseModel):
    hold_token: str
    customer_id: uuid.UUID | None = None


# ── 임시선점 ──────────────────────────────────────────────────────────────────
@units_live_router.post("/units/{unit_id}/hold")
async def hold_unit_live(unit_id: uuid.UUID, body: HoldBody | None = None,
                         db: AsyncSession = Depends(get_db),
                         ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    """원자 선점 시도. 성공시 토큰·만료시각, 실패시 409(이미 타인 선점/계약)."""
    await ensure_unit_concurrency_columns(db)
    ttl = (body.minutes if body and body.minutes else HOLD_TTL_MINUTES)
    me = ctx.user.id
    row = await atomic_hold(db, ctx.site_id, unit_id, me, ttl_minutes=ttl)
    if row is None:
        # 실패 — 현재 상태 회신(이미 held/contracted). 본인 hold면 held_by_me=True(idempotent UX).
        cur = await current_status(db, ctx.site_id, unit_id)
        await db.rollback()
        if cur is None:
            raise HTTPException(404, "세대를 찾을 수 없습니다")
        held_by_me = str(cur["held_by"]) == str(me) if cur["held_by"] else False
        raise HTTPException(409, detail={
            "message": "이미 다른 직원이 선점했거나 계약된 세대입니다",
            "current_status": cur["status"],
            "held_by_me": held_by_me,
        })
    # 선점 감사행 남기기(누가·누구를 위해 언제까지 선점했는지 추적). actions.py에 있던 중복
    # hold 핸들러를 제거하면서 이 감사 기록을 정식 핸들러(units_live)로 옮겨왔다.
    from apps.api.database.models.sales.units_pricing import SalesUnitHold
    db.add(SalesUnitHold(site_id=ctx.site_id, unit_id=unit_id,
                         staff_id=(body.staff_id if body else None),
                         customer_id=(body.customer_id if body else None),
                         expires_at=row["hold_expires_at"]))
    await db.commit()
    await _broadcast(ctx.site_id, "HOLD", unit_id, "HOLD",
                     held_by=me, expires_at=row["hold_expires_at"])
    return {
        "ok": True,
        "unit_id": str(unit_id),
        "hold_token": row["hold_token"],
        "expires_at": row["hold_expires_at"].isoformat() if row["hold_expires_at"] else None,
        "ttl_minutes": int(ttl),
    }


# ── 해제 ──────────────────────────────────────────────────────────────────────
@units_live_router.post("/units/{unit_id}/release")
async def release_unit_live(unit_id: uuid.UUID, body: ReleaseBody | None = None,
                            db: AsyncSession = Depends(get_db),
                            ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    """본인 선점 해제 → AVAILABLE. 본인 hold 아니면 409."""
    await ensure_unit_concurrency_columns(db)
    token = body.hold_token if body else None
    row = await atomic_release(db, ctx.site_id, unit_id, ctx.user.id, hold_token=token)
    if row is None:
        cur = await current_status(db, ctx.site_id, unit_id)
        await db.rollback()
        if cur is None:
            raise HTTPException(404, "세대를 찾을 수 없습니다")
        raise HTTPException(409, detail={
            "message": "본인이 선점한 세대가 아니거나 이미 해제되었습니다",
            "current_status": cur["status"],
        })
    await db.commit()
    await _broadcast(ctx.site_id, "RELEASE", unit_id, "AVAILABLE")
    return {"ok": True, "unit_id": str(unit_id), "released": True}


# ── 확정(계약 점유) ───────────────────────────────────────────────────────────
@units_live_router.post("/units/{unit_id}/reserve")
async def reserve_unit_live(unit_id: uuid.UUID, body: ReserveBody,
                            db: AsyncSession = Depends(get_db),
                            ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    """확정 — HOLD & 본인 & 미만료 & 토큰일치 → CONTRACTED(+상태로그). 만료시 409.

    영구 1호1계약은 status='CONTRACTED' 전이 + (site,dong,ho) 부분 유니크 인덱스가 보장.
    계약레코드 정식 생성은 /contracts/{id}/sign 으로 이어진다(여기선 동호 점유 확정).
    """
    await ensure_unit_concurrency_columns(db)
    me = ctx.user.id
    row = await atomic_reserve(db, ctx.site_id, unit_id, me, hold_token=body.hold_token)
    if row is None:
        cur = await current_status(db, ctx.site_id, unit_id)
        await db.rollback()
        if cur is None:
            raise HTTPException(404, "세대를 찾을 수 없습니다")
        reason = "선점이 만료되었습니다" if cur["expired"] else \
                 ("이미 계약된 세대입니다" if cur["status"] == "CONTRACTED" else
                  "본인 선점이 아니거나 토큰이 일치하지 않습니다")
        raise HTTPException(409, detail={"message": reason, "current_status": cur["status"]})
    # 상태전이 로그(기존 sales_unit_status_log 재사용)
    from sqlalchemy import text  # noqa: PLC0415
    await db.execute(text(
        "INSERT INTO sales_unit_status_log (unit_id, site_id, from_status, to_status, by) "
        "VALUES (:uid, :s, 'HOLD', 'CONTRACTED', :by)"
    ), {"uid": str(unit_id), "s": str(ctx.site_id), "by": str(me)})
    await db.commit()
    await _broadcast(ctx.site_id, "RESERVE", unit_id, "CONTRACTED")
    return {
        "ok": True,
        "unit_id": str(unit_id),
        "reserved": True,
        "status": "CONTRACTED",
        "dong": row["dong"],
        "ho": row["ho"],
    }


# ── 보드 조회 ─────────────────────────────────────────────────────────────────
def _mask_held_by(held_by, me, role: str) -> dict:
    """held_by 마스킹 — 본인/관리자만 상세 노출, 그 외엔 점유여부만."""
    if not held_by:
        return {"held": False, "held_by_me": False, "held_by": None}
    is_me = str(held_by) == str(me)
    privileged = is_me or role in ("DEVELOPER", "AGENCY", "SUPERADMIN", "DIRECTOR", "GM_DIRECTOR")
    return {
        "held": True,
        "held_by_me": is_me,
        "held_by": str(held_by) if privileged else None,
    }


@units_live_router.get("/units/board")
async def units_board(db: AsyncSession = Depends(get_db),
                      ctx: SalesCtx = Depends(sales_ctx)) -> dict:
    """현장 세대배치도 보드 — 전 세대 effective_status(만료 HOLD=AVAILABLE), held_by 마스킹."""
    await ensure_unit_concurrency_columns(db)
    rows = await board_rows(db, ctx.site_id)
    me = ctx.user.id
    units = []
    counts = {"AVAILABLE": 0, "HOLD": 0, "CONTRACTED": 0, "CANCELLED": 0}
    for r in rows:
        eff = r["effective_status"]
        counts[eff] = counts.get(eff, 0) + 1
        mask = _mask_held_by(r["held_by"] if eff == "HOLD" else None, me, ctx.role)
        units.append({
            "unit_id": str(r["id"]),
            "dong": r["dong"], "ho": r["ho"], "floor": r["floor"], "line": r["line"],
            "type_id": str(r["type_id"]) if r["type_id"] else None,
            "status": eff,
            "expires_at": (r["hold_expires_at"].isoformat()
                           if (eff == "HOLD" and r["hold_expires_at"]) else None),
            **mask,
        })
    return {"site_id": str(ctx.site_id), "channel": _board_channel(ctx.site_id),
            "counts": counts, "units": units}
