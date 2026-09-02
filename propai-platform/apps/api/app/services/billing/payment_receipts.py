"""결제 영수증 원장 — **성공이든 실패든 벤더 원문을 버리지 않는다**(append-only).

## 왜 필요한가 (§유료·비가역 산출물 규율 — 이 저장소가 네 얼굴로 데인 그 규율)

> **한 번 돈을 주고 얻은 것은 다시 사지도, 잃지도, 이유를 버리지도 않는다.**

결제 승인은 **가장 비가역적인 유료 산출물**이다. 그런데 승인 응답을 요청 트랜잭션 안에서만
다루면 이렇게 된다:

    토스 승인 200 (★돈이 빠져나갔다)
      → confirm_order 중 DB 오류
      → 요청 트랜잭션 **롤백**
      → ★승인 사실의 기록이 **어디에도 없다**

사용자는 카드값을 냈고 코인은 못 받았는데, **우리는 그 사실조차 모른다.** 조사할 근거가
없으므로 복구도 불가능하다. **진단 불가는 그 자체로 장애다.**

## 그래서 두 가지를 구조로 못 박는다

1. **독립 세션**(`AsyncSessionLocal`) — 요청 트랜잭션이 롤백돼도 영수증은 남는다.
   같은 세션에서 쓰면 "롤백이 증거를 지우는" 바로 그 결함이 재발한다.
2. **append-only** — `UPDATE`·`DELETE` 를 하지 않는다. 상태 변화는 **새 행**으로 쌓인다.
   전자상거래법 §6(대금결제 기록 보존)의 대상이기도 하다.

## 이 표가 답하는 질문

- *"이 결제, 토스는 뭐라고 했나?"* → `raw`
- *"승인은 됐는데 코인이 안 들어간 주문이 있나?"* → `approved` 있고 `applied` 없는 것
- *"결과를 모르는 채 끝난 요청이 있나?"* → `unknown` 이고 뒤따르는 확정 이벤트가 없는 것
  ★**이 질의가 정합성 회복(reconciliation)의 입력**이다.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 이벤트 어휘 — ★파생형으로 쓴다(손 목록이 상한이 되지 않게)
# ─────────────────────────────────────────────────────────────────────────────
#: 승인 요청을 **보내기 직전**. 이게 있고 뒤가 없으면 = 우리가 죽은 지점.
EVENT_REQUESTED = "requested"
#: 벤더가 승인했다(★돈이 움직였다). `raw` 에 Payment 객체 원문.
EVENT_APPROVED = "approved"
#: 벤더가 거절했다 — 결과를 **안다**. 돈은 안 움직였다.
EVENT_REJECTED = "rejected"
#: ★**결과를 모른다**(타임아웃·5xx). 돈이 움직였는지 알 수 없다 → 재조회 대상.
EVENT_UNKNOWN = "unknown"
#: 승인 결과를 우리 원장에 반영 완료(코인 지급됨).
EVENT_APPLIED = "applied"
#: 승인은 됐는데 우리 원장 반영이 실패했다 — ★**사용자가 돈만 낸 상태**. 최우선 복구 대상.
EVENT_APPLY_FAILED = "apply_failed"
#: 요청 자체를 우리가 거절했다(금액 불일치·소유자 불일치 등). 벤더 호출 전.
EVENT_BLOCKED = "blocked"
#: 취소·환불.
EVENT_CANCELED = "canceled"
EVENT_CANCEL_REJECTED = "cancel_rejected"
#: 재조회로 상태를 확정했다(미확정 → 확정).
EVENT_RECONCILED = "reconciled"

#: ★전체 어휘 — 테스트가 이 상수에서 파생한다. 새 이벤트를 추가하면 락이 따라온다.
ALL_EVENTS: frozenset[str] = frozenset(
    {
        EVENT_REQUESTED,
        EVENT_APPROVED,
        EVENT_REJECTED,
        EVENT_UNKNOWN,
        EVENT_APPLIED,
        EVENT_APPLY_FAILED,
        EVENT_BLOCKED,
        EVENT_CANCELED,
        EVENT_CANCEL_REJECTED,
        EVENT_RECONCILED,
    }
)

#: ★**사람이 봐야 하는 상태** — 돈과 산출물이 어긋나 있을 수 있는 것.
#:   `unknown` = 승인 여부 미상 / `apply_failed` = 승인됐는데 미지급.
NEEDS_ATTENTION_EVENTS: frozenset[str] = frozenset({EVENT_UNKNOWN, EVENT_APPLY_FAILED})

#: ★이벤트가 **종결**시키는 선행 이벤트(정합성 질의의 축).
#:   예: `approved` 는 `requested` 를 종결한다. 종결되지 않은 선행이 곧 미해결 건이다.
RESOLVES: dict[str, frozenset[str]] = {
    EVENT_APPROVED: frozenset({EVENT_REQUESTED}),
    EVENT_REJECTED: frozenset({EVENT_REQUESTED}),
    EVENT_APPLIED: frozenset({EVENT_APPROVED, EVENT_UNKNOWN}),
    EVENT_RECONCILED: frozenset({EVENT_UNKNOWN, EVENT_APPLY_FAILED}),
}


_DDL = (
    "CREATE TABLE IF NOT EXISTS payment_receipts ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  order_id text,"
    "  order_no text,"
    "  user_id text,"
    "  payment_key text,"
    "  event text NOT NULL,"
    "  amount_krw numeric(14,2),"
    "  toss_code text,"
    "  toss_message text,"
    "  raw jsonb,"
    "  created_at timestamptz DEFAULT now()"
    ")"
)
_IDX = (
    "CREATE INDEX IF NOT EXISTS ix_payment_receipts_payment_key "
    "ON payment_receipts(payment_key)",
    "CREATE INDEX IF NOT EXISTS ix_payment_receipts_order ON payment_receipts(order_id)",
    # 미해결 건 조회(정합성 회복 배치)의 축.
    "CREATE INDEX IF NOT EXISTS ix_payment_receipts_event_created "
    "ON payment_receipts(event, created_at)",
)

#: ★영수증에 벤더 원문을 담되 **카드번호 같은 것이 그대로 쌓이지 않게** 한다.
#:   토스는 이미 마스킹된 번호(`12345678****789*`)를 주지만, 벤더가 형식을 바꿀 수 있고
#:   우리는 그 변화를 모른다. 알려진 민감 키는 우리 쪽에서도 한 번 더 지운다.
_SENSITIVE_KEYS = frozenset({"secret", "customerkey", "billingkey", "cardnumber", "number"})


def _scrub(value: Any, _depth: int = 0) -> Any:
    """벤더 원문에서 민감 키를 지운다(구조 보존 — 값만 대체).

    ★키 이름으로 지운다. 값 패턴(정규식)으로 지우면 **정상 값을 지우는 위양성**이 난다 —
    이 저장소가 성장루프 마스킹에서 겪은 그 결함이다(진단 필드를 지우고 주소는 통과).
    """
    if _depth > 8:  # 방어적 재귀 상한(벤더가 순환/과대 구조를 주는 경우)
        return "…"
    if isinstance(value, dict):
        return {
            k: ("***" if k.lower() in _SENSITIVE_KEYS else _scrub(v, _depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(v, _depth + 1) for v in value[:50]]
    return value


async def ensure_schema(db: Any) -> None:
    """멱등 DDL(이 저장소 관례 — alembic 과 문면 동일 병행)."""
    await db.execute(text(_DDL))
    for ix in _IDX:
        await db.execute(text(ix))


async def record(
    *,
    event: str,
    order_id: str | None = None,
    order_no: str | None = None,
    user_id: str | None = None,
    payment_key: str | None = None,
    amount_krw: float | None = None,
    toss_code: str | None = None,
    toss_message: str | None = None,
    raw: Any = None,
) -> str | None:
    """영수증 한 줄을 **독립 세션**으로 즉시 확정한다.

    ★독립 세션인 이유: 호출자의 트랜잭션이 롤백돼도 이 기록은 남아야 한다.
      같은 세션을 쓰면 "롤백이 증거를 지우는" 결함이 그대로 재발한다.

    ★**절대 예외를 밖으로 던지지 않는다.** 영수증 기록 실패 때문에 결제 처리가
      중단되면 더 나쁜 상태가 된다(돈은 움직였는데 응답이 500). 실패는 로그로 남긴다.
      ★단, 이 관용은 **기록**에만 적용된다 — 금액 검증 같은 판정은 절대 삼키지 않는다.

    Returns:
        영수증 id(문자열). 기록 실패 시 None.
    """
    if event not in ALL_EVENTS:
        # 어휘 밖 이벤트는 **조용히 통과시키지 않는다** — 조회 축이 무너진다.
        logger.error("payment_receipts: 알 수 없는 이벤트 %r — 기록하지 않음", event)
        return None

    from apps.api.database.session import AsyncSessionLocal

    payload = None
    if raw is not None:
        try:
            payload = json.dumps(_scrub(raw), ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            payload = json.dumps({"_unserializable": str(type(raw))})

    try:
        async with AsyncSessionLocal() as db:
            await ensure_schema(db)
            row = (
                await db.execute(
                    text(
                        "INSERT INTO payment_receipts"
                        " (order_id, order_no, user_id, payment_key, event, amount_krw,"
                        "  toss_code, toss_message, raw)"
                        " VALUES (:oid, :ono, :uid, :pk, :ev, :amt, :code, :msg,"
                        "         CAST(:raw AS jsonb))"
                        " RETURNING id"
                    ),
                    {
                        "oid": order_id,
                        "ono": order_no,
                        "uid": user_id,
                        "pk": payment_key,
                        "ev": event,
                        "amt": amount_krw,
                        "code": toss_code,
                        "msg": (toss_message or "")[:500] or None,
                        "raw": payload,
                    },
                )
            ).first()
            await db.commit()
            return str(row[0]) if row else None
    except Exception:  # noqa: BLE001 — 기록 실패가 결제를 막으면 안 된다
        logger.exception(
            "payment_receipts 기록 실패 — event=%s order_no=%s (결제 처리는 계속)",
            event,
            order_no,
        )
        return None


async def list_for_order(db: Any, order_id: str) -> list[dict[str, Any]]:
    """한 주문의 영수증 타임라인(오래된 순)."""
    await ensure_schema(db)
    rows = (
        await db.execute(
            text(
                "SELECT id, event, payment_key, amount_krw, toss_code, toss_message, created_at"
                " FROM payment_receipts WHERE order_id = :oid ORDER BY created_at ASC"
            ),
            {"oid": order_id},
        )
    ).mappings().all()
    return [
        {
            "id": str(r["id"]),
            "event": r["event"],
            "payment_key": r["payment_key"],
            "amount_krw": float(r["amount_krw"]) if r["amount_krw"] is not None else None,
            "toss_code": r["toss_code"],
            "toss_message": r["toss_message"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


async def list_unresolved(db: Any, *, limit: int = 100) -> list[dict[str, Any]]:
    """★**돈과 산출물이 어긋나 있을 수 있는 건** — 정합성 회복의 작업 목록.

    조건: `unknown`(승인 여부 미상) 또는 `apply_failed`(승인됐는데 미지급) 이면서,
    그 뒤에 **같은 payment_key 로 종결 이벤트가 없는** 것.

    ★종결 이벤트를 `RESOLVES` 에서 파생시킨다 — 손으로 나열하면 새 이벤트를 추가할 때
    이 질의가 조용히 낡는다(목록은 곧 상한이 된다).
    """
    await ensure_schema(db)
    resolvers = sorted({e for e, prev in RESOLVES.items() if prev & NEEDS_ATTENTION_EVENTS})
    rows = (
        await db.execute(
            text(
                "SELECT r.id, r.order_id, r.order_no, r.user_id, r.payment_key, r.event,"
                "       r.amount_krw, r.toss_code, r.toss_message, r.created_at"
                "  FROM payment_receipts r"
                " WHERE r.event = ANY(:attention)"
                "   AND NOT EXISTS ("
                "        SELECT 1 FROM payment_receipts d"
                "         WHERE d.event = ANY(:resolvers)"
                "           AND d.created_at >= r.created_at"
                "           AND (d.payment_key IS NOT DISTINCT FROM r.payment_key)"
                "           AND (d.order_no    IS NOT DISTINCT FROM r.order_no)"
                "   )"
                " ORDER BY r.created_at ASC LIMIT :lim"
            ),
            {
                "attention": sorted(NEEDS_ATTENTION_EVENTS),
                "resolvers": resolvers,
                "lim": int(limit),
            },
        )
    ).mappings().all()
    return [
        {
            "receipt_id": str(r["id"]),
            "order_id": r["order_id"],
            "order_no": r["order_no"],
            "user_id": r["user_id"],
            "payment_key": r["payment_key"],
            "event": r["event"],
            "amount_krw": float(r["amount_krw"]) if r["amount_krw"] is not None else None,
            "toss_code": r["toss_code"],
            "toss_message": r["toss_message"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]
