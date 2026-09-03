"""매출 집계 — 관리자 결제관리 화면의 데이터 원천.

## 이 파일이 지키는 규율

1. **매출은 「들어온 것 − 나간 것」이다.** 환불을 빼지 않으면 매출이 부풀려진다.
   ★그래서 `coin_orders.refunded_krw` 를 **항상** 차감한다.
2. **미결제 취소(`canceled`)와 환불(`refunded`)을 뭉치지 않는다.**
   전자는 매출에 들어온 적이 없고, 후자는 들어왔다가 나간 것이다.
3. ★**「돈과 산출물이 어긋난 건」을 매출과 **같은 화면**에 둔다.**
   결제 대시보드가 매출만 보여 주면, 사용자가 돈을 내고 못 받은 건은 **아무도 안 본다.**
   이 저장소가 반복해 데인 형태다 — *"진단 불가는 그 자체로 장애다."*
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.billing import coin_orders_service, payment_receipts, toss_orders_service


async def _ensure(db: AsyncSession) -> None:
    await coin_orders_service.ensure_schema(db)
    await toss_orders_service.ensure_refund_schema(db)
    await payment_receipts.ensure_schema(db)


async def summary(db: AsyncSession, *, days: int = 30) -> dict[str, Any]:
    """기간 매출 요약.

    ★`gross`(총결제) · `refunded`(환불) · `net`(순매출)을 **각각** 낸다.
      순매출만 보여 주면 "환불이 늘어난 것"과 "결제가 준 것"을 구별할 수 없다.
    """
    await _ensure(db)
    row = (
        await db.execute(
            text(
                "SELECT"
                "  COUNT(*) FILTER (WHERE status IN ('paid','refunded'))         AS paid_count,"
                "  COALESCE(SUM(amount_krw) FILTER (WHERE status IN ('paid','refunded')), 0)"
                "                                                                AS gross_krw,"
                "  COALESCE(SUM(COALESCE(refunded_krw,0)), 0)                     AS refunded_krw,"
                "  COUNT(*) FILTER (WHERE COALESCE(refunded_krw,0) > 0)           AS refund_count,"
                "  COUNT(*) FILTER (WHERE status='pending')                       AS pending_count,"
                "  COUNT(*) FILTER (WHERE status='canceled')                      AS canceled_count,"
                "  COUNT(DISTINCT user_id) FILTER (WHERE status IN ('paid','refunded'))"
                "                                                                AS payer_count"
                "  FROM coin_orders"
                " WHERE created_at >= now() - make_interval(days => :d)"
            ),
            {"d": int(days)},
        )
    ).mappings().first()

    gross = float(row["gross_krw"] or 0)
    refunded = float(row["refunded_krw"] or 0)
    paid_count = int(row["paid_count"] or 0)
    return {
        "days": int(days),
        "paid_count": paid_count,
        "gross_krw": round(gross),
        "refunded_krw": round(refunded),
        # ★순매출 = 총결제 − 환불. 이 한 줄이 이 화면의 존재 이유다.
        "net_krw": round(gross - refunded),
        "refund_count": int(row["refund_count"] or 0),
        "refund_rate_pct": round(refunded / gross * 100, 1) if gross > 0 else 0.0,
        "avg_order_krw": round(gross / paid_count) if paid_count else 0,
        "pending_count": int(row["pending_count"] or 0),
        "canceled_count": int(row["canceled_count"] or 0),
        "payer_count": int(row["payer_count"] or 0),
    }


async def daily(db: AsyncSession, *, days: int = 30) -> list[dict[str, Any]]:
    """일별 추이 — ★결제가 **없는 날도 0 으로 채운다**.

    빈 날을 빼면 그래프가 "매출이 꾸준했던 것"처럼 보인다(결측과 0 은 다르다).
    """
    await _ensure(db)
    rows = (
        await db.execute(
            text(
                "WITH d AS ("
                "  SELECT generate_series("
                "    date_trunc('day', now() - make_interval(days => :d)),"
                "    date_trunc('day', now()), interval '1 day') AS day"
                ")"
                "SELECT d.day::date AS day,"
                "       COALESCE(SUM(o.amount_krw) FILTER (WHERE o.status IN ('paid','refunded')), 0)"
                "         AS gross_krw,"
                "       COALESCE(SUM(COALESCE(o.refunded_krw,0)), 0) AS refunded_krw,"
                "       COUNT(o.id) FILTER (WHERE o.status IN ('paid','refunded')) AS paid_count"
                "  FROM d LEFT JOIN coin_orders o"
                "    ON date_trunc('day', COALESCE(o.paid_at, o.created_at)) = d.day"
                " GROUP BY d.day ORDER BY d.day"
            ),
            {"d": int(days)},
        )
    ).mappings().all()
    return [
        {
            "day": r["day"].isoformat(),
            "gross_krw": round(float(r["gross_krw"] or 0)),
            "refunded_krw": round(float(r["refunded_krw"] or 0)),
            "net_krw": round(float(r["gross_krw"] or 0) - float(r["refunded_krw"] or 0)),
            "paid_count": int(r["paid_count"] or 0),
        }
        for r in rows
    ]


async def by_provider(db: AsyncSession, *, days: int = 30) -> list[dict[str, Any]]:
    """결제 경로별 분포 — `toss`/`manual`/`simulated`.

    ★프로덕션에서 `simulated` 가 0 이 아니면 **무료 충전 경로가 열려 있다**는 뜻이다.
      이 표가 그것을 보이게 한다.
    """
    await _ensure(db)
    rows = (
        await db.execute(
            text(
                "SELECT COALESCE(provider,'(미상)') AS provider, COUNT(*) AS cnt,"
                "       COALESCE(SUM(amount_krw),0) AS gross_krw"
                "  FROM coin_orders"
                " WHERE status IN ('paid','refunded')"
                "   AND created_at >= now() - make_interval(days => :d)"
                " GROUP BY 1 ORDER BY gross_krw DESC"
            ),
            {"d": int(days)},
        )
    ).mappings().all()
    return [
        {
            "provider": r["provider"],
            "count": int(r["cnt"]),
            "gross_krw": round(float(r["gross_krw"] or 0)),
        }
        for r in rows
    ]


async def failure_reasons(db: AsyncSession, *, days: int = 30, limit: int = 15) -> list[dict[str, Any]]:
    """실패 사유 상위 — ★**무엇 때문에 결제가 안 되는지**를 운영자가 알아야 고친다.

    영수증 원장에서 파생한다(주문의 `fail_reason` 은 마지막 하나만 남는다).
    """
    await _ensure(db)
    rows = (
        await db.execute(
            text(
                "SELECT COALESCE(toss_code,'(코드없음)') AS code, COUNT(*) AS cnt,"
                "       MAX(toss_message) AS sample"
                "  FROM payment_receipts"
                " WHERE event IN (:rejected, :blocked)"
                "   AND created_at >= now() - make_interval(days => :d)"
                " GROUP BY 1 ORDER BY cnt DESC LIMIT :lim"
            ),
            {
                "rejected": payment_receipts.EVENT_REJECTED,
                "blocked": payment_receipts.EVENT_BLOCKED,
                "d": int(days),
                "lim": int(limit),
            },
        )
    ).mappings().all()
    return [
        {"code": r["code"], "count": int(r["cnt"]), "sample": r["sample"]}
        for r in rows
    ]


async def top_payers(db: AsyncSession, *, days: int = 30, limit: int = 20) -> list[dict[str, Any]]:
    """상위 결제 사용자 — ★이메일은 **마스킹**해서 내보낸다(관리자 화면이라도 원문 불필요)."""
    await _ensure(db)
    rows = (
        await db.execute(
            text(
                "SELECT o.user_id, u.email,"
                "       COUNT(*) AS cnt,"
                "       COALESCE(SUM(o.amount_krw),0) AS gross_krw,"
                "       COALESCE(SUM(COALESCE(o.refunded_krw,0)),0) AS refunded_krw"
                "  FROM coin_orders o LEFT JOIN public.users u ON u.id::text = o.user_id"
                " WHERE o.status IN ('paid','refunded')"
                "   AND o.created_at >= now() - make_interval(days => :d)"
                " GROUP BY o.user_id, u.email ORDER BY gross_krw DESC LIMIT :lim"
            ),
            {"d": int(days), "lim": int(limit)},
        )
    ).mappings().all()
    return [
        {
            "user_id": r["user_id"],
            "email_masked": _mask_email(r["email"]),
            "count": int(r["cnt"]),
            "gross_krw": round(float(r["gross_krw"] or 0)),
            "refunded_krw": round(float(r["refunded_krw"] or 0)),
            "net_krw": round(float(r["gross_krw"] or 0) - float(r["refunded_krw"] or 0)),
        }
        for r in rows
    ]


async def recent_orders(db: AsyncSession, *, days: int = 30, limit: int = 30) -> list[dict[str, Any]]:
    """최근 결제 — ★관리자가 **여기서 환불을 집행**한다.

    ★이 목록이 없으면 관리자 환불 API 는 만들어 놓고 **아무도 못 쓰는** 상태가 된다
      (실제로 라우트 도달률 래칫이 그것을 잡았다 — 2026-08-27).
    """
    await _ensure(db)
    rows = (
        await db.execute(
            text(
                "SELECT o.id, o.order_no, o.user_id, u.email, o.amount_krw,"
                "       COALESCE(o.refunded_krw,0) AS refunded_krw, o.status, o.provider,"
                "       o.paid_at, o.created_at"
                "  FROM coin_orders o LEFT JOIN public.users u ON u.id::text = o.user_id"
                " WHERE o.created_at >= now() - make_interval(days => :d)"
                " ORDER BY COALESCE(o.paid_at, o.created_at) DESC LIMIT :lim"
            ),
            {"d": int(days), "lim": int(limit)},
        )
    ).mappings().all()
    return [
        {
            "id": str(r["id"]),
            "order_no": r["order_no"],
            "email_masked": _mask_email(r["email"]),
            "amount_krw": round(float(r["amount_krw"] or 0)),
            "refunded_krw": round(float(r["refunded_krw"] or 0)),
            # ★환불 가능액을 **서버가 계산해서 준다** — 화면이 계산하면 두 곳이 갈린다.
            "refundable_krw": max(
                0, round(float(r["amount_krw"] or 0)) - round(float(r["refunded_krw"] or 0))
            ),
            "status": r["status"],
            "provider": r["provider"],
            "paid_at": r["paid_at"].isoformat() if r["paid_at"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


def _mask_email(email: str | None) -> str:
    """`ab***@example.com` — 식별은 되되 원문은 남기지 않는다."""
    if not email or "@" not in email:
        return "(미상)"
    local, _, domain = email.partition("@")
    head = local[:2] if len(local) > 2 else local[:1]
    return f"{head}***@{domain}"
