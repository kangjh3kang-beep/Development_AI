"""세대 상태전이 액션 — 세대 클릭 컨텍스트 메뉴(동·호지정 대기/취소·계약 대기/취소·계약 체결·특이사항).

각 액션은 (1) 상태머신 검증 → (2) 세대 status 전이 → (3) 이벤트 원장(해시체인) append +
SalesUnitStatusLog 기록을 한 번에 수행한다. 모든 이벤트는 년월일·시분(occurred_at)으로 영속된다.

상태 매핑(sales_unit_inventory.status, 기존 모델 보존):
  AVAILABLE(분양가능) → HOLD(동·호지정 대기) → APPLIED(계약 대기) → CONTRACTED(계약 체결)
  취소는 직전 상태에 따라 AVAILABLE 로 복귀(계약체결 취소는 CANCELLED).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales.units.event_ledger import _ensure, append_event

# 액션 → (허용 from 상태들, 도달 to 상태). NOTE 는 상태 변화 없음.
_TRANSITIONS: dict[str, tuple[set[str], str]] = {
    "HOLD_REQUEST": ({"AVAILABLE"}, "HOLD"),
    "HOLD_CANCEL": ({"HOLD"}, "AVAILABLE"),
    "CONTRACT_WAIT": ({"HOLD", "AVAILABLE"}, "APPLIED"),
    "CONTRACT_CANCEL": ({"APPLIED"}, "AVAILABLE"),
    "CONTRACT_SIGN": ({"APPLIED", "HOLD"}, "CONTRACTED"),
    "CONTRACT_TERMINATE": ({"CONTRACTED"}, "CANCELLED"),  # 계약체결 취소(해지)
}


async def unit_action(db: AsyncSession, site_id, unit_id, action: str,
                      message: str | None = None, by=None) -> dict[str, Any]:
    """세대 1건에 액션 수행 — 상태전이(검증) + 이벤트 원장 + 상태로그. NOTE 는 특이사항만 기록."""
    act = (action or "").upper()
    # 테이블 보장(DDL)은 트랜잭션 작업 전에 1회 끝낸다 — _ensure 의 첫 호출 commit 이
    # 아래 전이 UPDATE 를 조기 커밋해 원자성을 깨는 것을 방지(프로세스당 최초 1회 갭 차단).
    await _ensure(db)
    row = (await db.execute(text(
        "SELECT status FROM sales_unit_inventory WHERE id=:u AND site_id=:s AND deleted_at IS NULL"),
        {"u": str(unit_id), "s": str(site_id)})).first()
    if not row:
        raise ValueError("세대를 찾을 수 없습니다")
    cur = row[0] or "AVAILABLE"

    # 특이사항(NOTE): 상태 변화 없이 메시지만 원장에 기록.
    if act == "NOTE":
        if not (message or "").strip():
            raise ValueError("특이사항 내용을 입력하세요")
        ev = await append_event(db, site_id, unit_id, "NOTE", from_status=cur, to_status=cur,
                                message=message, by=by, do_commit=False)
        await db.commit()  # 원장 INSERT를 호출부에서 한 번만 커밋(append_event 자체 커밋 제거).
        return {"ok": True, "action": "NOTE", "status": cur, "event": ev}

    if act not in _TRANSITIONS:
        raise ValueError(f"알 수 없는 액션: {action}")
    allowed_from, to_status = _TRANSITIONS[act]
    if cur not in allowed_from:
        raise ValueError(f"현재 상태({cur})에서 '{act}' 불가(허용: {sorted(allowed_from)})")

    # 상태 전이(원자 조건부 UPDATE — 동시성 안전: 기대 상태일 때만 갱신).
    upd = (await db.execute(text(
        "UPDATE sales_unit_inventory SET status=:to WHERE id=:u AND status=:from RETURNING id"),
        {"to": to_status, "u": str(unit_id), "from": cur})).first()
    if not upd:
        raise ValueError("상태가 방금 변경되었습니다. 새로고침 후 다시 시도하세요(동시성).")

    # 상태전이 로그(기존 SalesUnitStatusLog 보존) + 이벤트 원장(해시체인).
    # ★원자성: 위 status UPDATE(미커밋) → status_log → event → commit 을 '전부 성공 또는 전부 롤백'으로 묶는다.
    #   status_log INSERT 실패(컬럼차이 등)는 savepoint 로만 격리해 되돌리고, 전이 UPDATE·이벤트는 유지한다.
    #   (과거엔 status_log 실패 시 db.rollback() 으로 전이 UPDATE까지 날린 뒤 append_event 가 자체 commit →
    #    '상태는 안 바뀌었는데 원장엔 거짓 전이' 가 남는 붕괴가 있었음.)
    try:
        async with db.begin_nested():  # savepoint — 이 INSERT만 실패 시 롤백, 본 트랜잭션은 유지.
            await db.execute(text(
                "INSERT INTO sales_unit_status_log (site_id, unit_id, from_status, to_status, by) "
                "VALUES (:s,:u,:fs,:ts,:by)"),
                {"s": str(site_id), "u": str(unit_id), "fs": cur, "ts": to_status, "by": str(by) if by else None})
    except Exception:  # noqa: BLE001 — 상태로그 컬럼차이 등은 원장이 정본이므로 무시(savepoint 롤백됨)
        pass
    ev = await append_event(db, site_id, unit_id, act, from_status=cur, to_status=to_status,
                            message=message, by=by, do_commit=False)
    await db.commit()  # 전이 UPDATE + status_log + 이벤트 원장을 한 번에 커밋(원자성).
    return {"ok": True, "action": act, "from": cur, "status": to_status, "event": ev}
