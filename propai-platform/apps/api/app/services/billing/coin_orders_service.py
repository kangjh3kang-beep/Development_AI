"""코인 충전 주문 — coin_orders 수명주기(pending→paid|canceled|failed).

전자상거래법 시행령 §6(대금결제·계약 기록 5년 보존) 대상인 **결제기록의 정본**이다.
- 금액은 서버가 결정한다(패키지 프리셋 + 자유금액 범위 검증) — 클라이언트 금액 신뢰 금지.
- 구매자 스냅샷(buyer_name/buyer_email)을 주문 행에 내장 — 탈퇴(users 익명화)와 독립적으로
  법정 보존기간 동안 열람 가능(개인정보처리방침 §보존기간 연계).
- 확정(지급)은 `UPDATE … WHERE status='pending'` 원자 전이(멱등 — 중복지급 불가) +
  잔액 증액 + 코인원장 append를 **같은 트랜잭션**으로 묶는다.
- 결제 확정 경로: simulated(설정 플래그 한정 self-confirm) / manual(총괄관리자 수동 지급 —
  계좌이체 대응) / toss(후속 PG 연동점: provider·provider_ref 예약).
"""
from __future__ import annotations

import math
import secrets
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.billing import coin_ledger_service

logger = structlog.get_logger(__name__)

# ── 충전 패키지(서버 정의 — 금액의 유일한 결정 주체) ──
COIN_PACKAGES: dict[str, dict[str, Any]] = {
    "starter": {"amount_krw": 10_000, "label": "스타터 1만원"},
    "basic": {"amount_krw": 50_000, "label": "베이직 5만원"},
    "pro": {"amount_krw": 100_000, "label": "프로 10만원"},
    "max": {"amount_krw": 300_000, "label": "맥스 30만원"},
}
CUSTOM_MIN_KRW = 1_000
CUSTOM_MAX_KRW = 1_000_000
CUSTOM_UNIT_KRW = 100  # 100원 단위
PENDING_ORDER_CAP = 5  # 사용자당 미결제 주문 상한(동시 남발 방지)
DAILY_ORDER_CAP = 50   # 사용자당 일일 주문 생성 상한(생성→취소 churn으로 테이블 팽창 방지)

ORDER_STATUSES = ("pending", "paid", "canceled", "failed")

_DDL = (
    "CREATE TABLE IF NOT EXISTS coin_orders ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  order_no text UNIQUE NOT NULL,"
    "  user_id text NOT NULL,"
    "  tenant_id text,"
    "  package_key text NOT NULL,"
    "  amount_krw numeric(14,2) NOT NULL,"
    "  coin_krw numeric(14,2) NOT NULL,"
    "  status text NOT NULL DEFAULT 'pending',"
    "  provider text,"
    "  provider_ref text,"
    "  buyer_name text,"
    "  buyer_email text,"
    "  fail_reason text,"
    "  paid_at timestamptz,"
    "  canceled_at timestamptz,"
    "  created_at timestamptz DEFAULT now()"
    ")"
)
_IDX = (
    # provider_ref 부분 유니크 — PG 웹훅/재시도 중복 확정 방지(멱등 키).
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_coin_orders_provider_ref "
    "ON coin_orders(provider_ref) WHERE provider_ref IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_coin_orders_user_created ON coin_orders(user_id, created_at)",
)


async def ensure_schema(db: AsyncSession) -> None:
    """coin_orders 테이블·인덱스 멱등 보장(alembic 043과 동일 DDL 병행)."""
    await db.execute(text(_DDL))
    for ix in _IDX:
        await db.execute(text(ix))


def resolve_order_amount(package_key: str, amount_krw: float | None = None) -> float:
    """주문 금액을 서버가 결정. 프리셋 키 또는 custom(범위·단위 검증). 위반 시 ValueError."""
    if package_key in COIN_PACKAGES:
        return float(COIN_PACKAGES[package_key]["amount_krw"])
    if package_key == "custom":
        if amount_krw is None:
            raise ValueError("직접입력 금액이 필요합니다.")
        amt = float(amount_krw)
        if not math.isfinite(amt):  # NaN/Infinity 차단(범위검증 이전 명시 가드)
            raise ValueError("충전 금액이 올바르지 않습니다.")
        if not (CUSTOM_MIN_KRW <= amt <= CUSTOM_MAX_KRW):
            raise ValueError(
                f"충전 금액은 {CUSTOM_MIN_KRW:,}원~{CUSTOM_MAX_KRW:,}원 사이여야 합니다."
            )
        if amt != int(amt) or int(amt) % CUSTOM_UNIT_KRW != 0:
            raise ValueError(f"충전 금액은 {CUSTOM_UNIT_KRW}원 단위여야 합니다.")
        return float(int(amt))
    raise ValueError("알 수 없는 충전 상품입니다.")


def _new_order_no() -> str:
    """사람이 읽는 주문번호 — 날짜 + 무작위(추측 불가, 열거 방지)."""
    return f"CO{datetime.now(UTC):%Y%m%d}-{secrets.token_hex(4).upper()}"


def _order_dict(r: Any) -> dict[str, Any]:
    return {
        "id": str(r["id"]),
        "order_no": r["order_no"],
        "package_key": r["package_key"],
        "amount_krw": round(float(r["amount_krw"]), 2),
        "coin_krw": round(float(r["coin_krw"]), 2),
        "status": r["status"],
        "provider": r["provider"],
        "fail_reason": r["fail_reason"],
        "paid_at": r["paid_at"].isoformat() if r["paid_at"] else None,
        "canceled_at": r["canceled_at"].isoformat() if r["canceled_at"] else None,
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    }


async def create_order(
    db: AsyncSession, *, user_id: str, tenant_id: str | None,
    package_key: str, amount_krw: float | None = None,
) -> dict[str, Any]:
    """충전 주문 생성(pending). 금액 서버 결정 + 구매자 법정보존 스냅샷 + 미결제 상한."""
    amount = resolve_order_amount(package_key, amount_krw)  # ValueError → 라우터 400
    await ensure_schema(db)

    # ★상한 검사의 TOCTOU 제거(성장루프 LOW 수렴): 같은 사용자 주문 생성을 advisory lock으로
    #   직렬화 → 동시 다발 요청이 동일 count를 읽고 모두 통과해 상한을 초과 적재하는 경쟁을 차단.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lk)::bigint)"),
        {"lk": f"coin_order_create:{user_id}"},
    )
    pending = (await db.execute(text(
        "SELECT COUNT(*) FROM coin_orders WHERE user_id=:u AND status='pending'"
    ), {"u": user_id})).scalar() or 0
    if int(pending) >= PENDING_ORDER_CAP:
        raise PendingCapExceededError(
            f"결제 대기 주문이 {PENDING_ORDER_CAP}건을 넘었습니다. 기존 주문을 취소하거나 완료해 주세요."
        )
    # 일일 생성 상한 — 생성→취소 반복(churn)으로 coin_orders가 무한 팽창하는 남용 벡터 경계.
    daily = (await db.execute(text(
        "SELECT COUNT(*) FROM coin_orders WHERE user_id=:u AND created_at >= now() - interval '1 day'"
    ), {"u": user_id})).scalar() or 0
    if int(daily) >= DAILY_ORDER_CAP:
        raise PendingCapExceededError(
            f"하루 주문 생성 한도({DAILY_ORDER_CAP}건)를 초과했습니다. 잠시 후 다시 시도해 주세요."
        )

    buyer = (await db.execute(text(
        "SELECT name, email FROM public.users WHERE id=:u"
    ), {"u": user_id})).first()
    order_no = _new_order_no()
    row = (await db.execute(text(
        "INSERT INTO coin_orders"
        "(order_no, user_id, tenant_id, package_key, amount_krw, coin_krw, buyer_name, buyer_email)"
        " VALUES(:no,:u,:t,:pk,:a,:c,:bn,:be)"
        " RETURNING id, order_no, package_key, amount_krw, coin_krw, status, provider,"
        " fail_reason, paid_at, canceled_at, created_at"
    ), {
        "no": order_no, "u": user_id, "t": tenant_id, "pk": package_key,
        "a": amount, "c": amount,  # v1: 1:1 지급(보너스는 billing_config 후속 연동점)
        "bn": (buyer[0] if buyer else None), "be": (buyer[1] if buyer else None),
    })).mappings().first()
    await db.commit()
    return _order_dict(row)


class PendingCapExceededError(Exception):
    """미결제 주문 상한 초과(라우터 409 매핑)."""


class OrderNotConfirmableError(Exception):
    """확정 불가 — 주문 부재/타인 소유/이미 처리됨(라우터 409/404 매핑)."""


async def list_orders(
    db: AsyncSession, user_id: str, *, limit: int = 20, offset: int = 0,
) -> list[dict[str, Any]]:
    """내 결제내역(주문 목록, 최신순). user_id 스코프."""
    await ensure_schema(db)
    limit = max(1, min(int(limit or 20), 100))
    offset = max(0, int(offset or 0))
    rows = (await db.execute(text(
        "SELECT id, order_no, package_key, amount_krw, coin_krw, status, provider,"
        " fail_reason, paid_at, canceled_at, created_at"
        " FROM coin_orders WHERE user_id=:u ORDER BY created_at DESC LIMIT :l OFFSET :o"
    ), {"u": user_id, "l": limit, "o": offset})).mappings().all()
    return [_order_dict(r) for r in rows]


async def confirm_order(
    db: AsyncSession, *, order_id: str, owner_user_id: str,
    provider: str, provider_ref: str | None = None, actor_id: str | None = None,
) -> dict[str, Any]:
    """주문 확정(지급) — pending 원자 전이 + 잔액 증액 + 원장 append(단일 트랜잭션·멱등).

    호출 전 권한 검증은 라우터 책임: self-confirm은 설정 플래그+소유자, 관리자는 super_admin.
    owner_user_id는 지급 대상(주문 소유자) — 관리자 경로도 소유자 id를 조회해 넘긴다.
    """
    await ensure_schema(db)
    # ★멱등의 핵심: status='pending'일 때만 전이(경쟁·중복 호출 시 한 번만 성립).
    # ★탈퇴 소유자 확정 차단(성장루프 LOW 수렴): 탈퇴 회원의 미결제 주문은 purge 배치가 buyer PII를
    #   이미 파기했을 수 있어, 이를 paid로 확정하면 §6 5년 보존 대상 결제기록에 구매자 식별정보가
    #   없는 상태가 된다. 활성(deleted_at IS NULL) 소유자만 확정 가능하게 원자 조건에 통합한다.
    row = (await db.execute(text(
        "UPDATE coin_orders SET status='paid', provider=:pv, provider_ref=:pref, paid_at=now()"
        " WHERE id=:id AND user_id=:u AND status='pending'"
        " AND user_id IN (SELECT id::text FROM public.users WHERE deleted_at IS NULL)"
        " RETURNING id, order_no, coin_krw, tenant_id"
    ), {"id": order_id, "u": owner_user_id, "pv": provider, "pref": provider_ref})).mappings().first()
    if row is None:
        raise OrderNotConfirmableError(
            "확정할 수 없는 주문입니다(이미 처리되었거나, 존재하지 않거나, 탈퇴한 계정의 주문)."
        )
    coin = round(float(row["coin_krw"]), 2)

    # 잔액 증액 — 원자 컬럼식(lost-update 방지) + 하위호환 budget 동기(in-row 재계산).
    await db.execute(text(
        "UPDATE public.users SET topup_krw = COALESCE(topup_krw,0) + :a,"
        " billing_budget_krw = COALESCE(monthly_base_krw,0) + COALESCE(topup_krw,0) + :a"
        " WHERE id=:u"
    ), {"a": coin, "u": owner_user_id})

    # 코인원장 append — 같은 트랜잭션(지급-이력 원자성). 실패 시 예외 전파 → 전체 롤백.
    await coin_ledger_service.append_event(
        db=db,
        user_id=owner_user_id,
        entry_type="order_paid",
        amount_krw=coin,
        tenant_id=str(row["tenant_id"]) if row["tenant_id"] else None,
        description=f"코인 충전(주문 {row['order_no']}, {provider})",
        ref_type="coin_order",
        ref_id=str(row["id"]),
        created_by=actor_id or owner_user_id,
    )
    await db.commit()
    return {"id": str(row["id"]), "order_no": row["order_no"], "status": "paid", "coin_krw": coin}


async def cancel_order(db: AsyncSession, *, order_id: str, user_id: str) -> dict[str, Any]:
    """pending 주문 취소(소유자). 이미 처리된 주문은 불가(멱등 전이)."""
    await ensure_schema(db)
    row = (await db.execute(text(
        "UPDATE coin_orders SET status='canceled', canceled_at=now()"
        " WHERE id=:id AND user_id=:u AND status='pending'"
        " RETURNING id, order_no"
    ), {"id": order_id, "u": user_id})).mappings().first()
    if row is None:
        raise OrderNotConfirmableError("취소할 수 없는 주문입니다(이미 처리되었거나 존재하지 않음).")
    await db.commit()
    return {"id": str(row["id"]), "order_no": row["order_no"], "status": "canceled"}


async def get_order_owner(db: AsyncSession, order_id: str) -> str | None:
    """주문 소유자 user_id 조회(관리자 확정 경로용). 부재 시 None."""
    await ensure_schema(db)
    r = (await db.execute(text(
        "SELECT user_id FROM coin_orders WHERE id=:id"
    ), {"id": order_id})).first()
    return str(r[0]) if r else None


# 전자상거래법 시행령 §6 대금결제·계약 기록 보존기간(5년) — 경과 후 구매자 PII 파기.
LEGAL_RETENTION_DAYS = 5 * 365 + 1  # 5년(윤년 여유 1일)


async def purge_expired_buyer_pii(db: AsyncSession | None = None) -> dict[str, Any]:
    """주문 구매자 PII(성명·이메일)를 근거 소멸 시 파기(NULL화). 2단계:

    (A) **결제완료(paid)** 주문: 전상법 §6 대금결제 기록 보존기간(5년) 경과 시 파기.
        기준 시점=paid_at(없으면 created_at).
    (B) **미결제(pending/canceled/failed)** 주문 중 **탈퇴 회원 소유**: 대금결제가 성립하지
        않아 §6 보존 근거가 없으므로, 회원 익명화 시 함께 즉시 파기 — 탈퇴 익명화가 미결제
        주문 PII로 부분 무력화되던 문제 해소(성장루프 MEDIUM 수렴, 개인정보보호법 §21).

    거래 사실(금액·주문번호·상태·일시)은 감사·통계 목적으로 보존하고 식별정보만 지운다. 멱등.
    """
    own = db is None
    session = None
    try:
        if own:
            from app.core.database import async_session_factory

            session = async_session_factory()
            db = await session.__aenter__()
        await ensure_schema(db)
        # (A) 결제완료 5년 경과
        res_paid = await db.execute(text(
            "UPDATE coin_orders SET buyer_name=NULL, buyer_email=NULL "
            "WHERE status='paid' AND (buyer_name IS NOT NULL OR buyer_email IS NOT NULL) "
            "AND COALESCE(paid_at, created_at) < now() - make_interval(days => :d)"
        ), {"d": int(LEGAL_RETENTION_DAYS)})
        # (B) 미결제 + 탈퇴회원 소유 → 보존근거 없음, 즉시 파기(익명화 정합)
        res_unpaid = await db.execute(text(
            "UPDATE coin_orders SET buyer_name=NULL, buyer_email=NULL "
            "WHERE status <> 'paid' AND (buyer_name IS NOT NULL OR buyer_email IS NOT NULL) "
            "AND user_id IN (SELECT id::text FROM public.users WHERE deleted_at IS NOT NULL)"
        ))
        await db.commit()
        return {
            "purged": int(res_paid.rowcount or 0) + int(res_unpaid.rowcount or 0),
            "purged_paid_expired": int(res_paid.rowcount or 0),
            "purged_unpaid_withdrawn": int(res_unpaid.rowcount or 0),
        }
    except Exception as e:  # noqa: BLE001 — 배치 실패는 다음 주기 재시도(비치명)
        logger.warning("coin_orders_pii_purge_skip", error=str(e)[:160])
        return {"purged": 0, "reason": str(e)[:160]}
    finally:
        if own and session is not None:
            await session.__aexit__(None, None, None)
