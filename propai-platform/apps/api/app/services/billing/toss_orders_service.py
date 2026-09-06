"""토스 결제 ↔ 코인 주문 연결 — **돈과 산출물이 어긋나지 않게** 하는 층.

## 이 파일이 지키는 한 문장

> **돈이 움직였는지 모르는 채로 「실패」라고 쓰지 않는다.**

## 왜 별도 층인가

`coin_orders_service.confirm_order()` 는 **우리 원장**만 안다(pending→paid 원자 전이).
`toss_payments` 는 **벤더**만 안다. 그 둘 사이에 **돈이 움직였는데 원장이 안 따라오는
구간**이 있고, 거기가 정확히 사고가 나는 자리다. 이 파일이 그 구간을 담당한다.

## 승인 흐름 — 각 단계가 왜 그 순서인지

    1. 주문 잠금(advisory lock)      ← 두 탭이 동시에 승인 누르는 것을 직렬화
    2. 주문 조회 + 소유자 검증        ← ★IDOR: 남의 주문을 승인/충전할 수 없다
    3. ★금액 검증 (서버 저장값 대조)  ← 클라이언트가 보낸 amount 를 **믿지 않는다**
    4. 이미 처리된 주문인가 판정      ← 같은 결제면 성공(멱등), 다른 결제면 거절
    5. 영수증 requested 기록(★독립 커밋) ← 여기서 죽어도 흔적이 남는다
    6. 토스 승인 호출                 ← ★돈이 움직이는 지점
    7. 결과별 분기:
         승인   → 영수증 approved → 원장 반영 → 영수증 applied
         거절   → 영수증 rejected → 사용자에게 사유+조치
         미확정 → 영수증 unknown  → ★재조회로 확정 시도 → 그래도 모르면 미해결로 남긴다
    8. 원장 반영 실패 → 영수증 apply_failed ← ★사용자가 돈만 낸 상태. 최우선 복구 대상

★**5 번이 6 번보다 먼저**인 이유: 6 번 도중에 프로세스가 죽으면 5 번이 유일한 단서다.
★**7 번의 세 갈래를 뭉치면** 이 파일이 존재할 이유가 없어진다 — 미확정을 실패로 접는 순간
  "돈은 나갔는데 아무도 모르는" 상태가 만들어진다.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.billing import (
    coin_ledger_service,
    coin_orders_service,
    payment_receipts,
    toss_payments,
)
from app.services.billing.toss_payments import (
    TossError,
    TossNotConfiguredError,
    TossOutcomeUnknownError,
)

logger = logging.getLogger(__name__)


class PaymentRejectedError(Exception):
    """벤더 또는 우리 검증이 결제를 **거절**했다 — 돈은 움직이지 않았다.

    `remediation` 은 사용자가 **다음에 무엇을 하면 되는지**다. 이것이 없으면
    사용자는 같은 실패를 반복한다(진단 불가는 그 자체로 장애다).
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        remediation: str,
        retryable: bool = False,
        http_status: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.remediation = remediation
        self.retryable = retryable
        self.http_status = http_status


class PaymentUnresolvedError(Exception):
    """★**결제 결과를 모른다.** 실패가 아니다.

    사용자에게 "실패했습니다"라고 말하면 안 된다 — 카드에서 돈이 빠져나갔을 수 있다.
    `receipt_id` 로 조사·복구가 가능하다는 것을 함께 알린다.
    """

    def __init__(self, message: str, *, receipt_id: str | None, order_no: str | None) -> None:
        super().__init__(message)
        self.receipt_id = receipt_id
        self.order_no = order_no


#: 토스 Payment 객체의 **최종 승인** 상태. 이것만이 「돈이 움직였다」를 뜻한다.
STATUS_DONE = "DONE"

#: ★아직 결정되지 않은 상태 — **실패가 아니다.**
#:   `WAITING_FOR_DEPOSIT` = 가상계좌 발급됨(입금 대기) · `IN_PROGRESS` = 인증 후 승인 전
_PENDING_STATUSES = frozenset({"WAITING_FOR_DEPOSIT", "IN_PROGRESS", "READY"})

_PENDING_MESSAGE: dict[str, str] = {
    "WAITING_FOR_DEPOSIT": (
        "가상계좌가 발급되었습니다. 안내된 계좌로 입금하시면 코인이 자동으로 충전됩니다."
    ),
    "IN_PROGRESS": "결제를 처리하고 있습니다. 잠시 후 충전 내역을 확인해 주세요.",
    "READY": "결제가 아직 완료되지 않았습니다. 결제창에서 결제를 마쳐 주세요.",
}


class PaymentPendingError(Exception):
    """★결제가 **아직 완료되지 않았다** — 실패도, 성공도 아니다.

    가상계좌가 대표적이다: 계좌는 발급됐고 입금은 아직이다. 이걸 실패로 말하면
    사용자가 재결제해서 **이중 결제**가 되고, 성공으로 말하면 **입금 없이 코인**을 준다.
    """

    def __init__(
        self, message: str, *, status: str, order_no: str | None, payment: dict[str, Any]
    ) -> None:
        super().__init__(message)
        self.status = status
        self.order_no = order_no
        # 가상계좌 안내(은행·계좌번호·기한)를 화면에 그대로 보여 줘야 사용자가 입금할 수 있다.
        self.virtual_account = payment.get("virtualAccount")
        self.due_date = (payment.get("virtualAccount") or {}).get("dueDate")


# ─────────────────────────────────────────────────────────────────────────────
# 오류 코드 → 사용자 안내 + **조치**
# ─────────────────────────────────────────────────────────────────────────────
#: 토스 오류코드 → (사용자 문구, 조치). ★코드가 이 표에 없어도 **침묵하지 않는다** —
#:   `_remediation_for()` 가 분류(결정론/일시)에 따른 기본 조치를 준다.
_REMEDIATION: dict[str, tuple[str, str]] = {
    "PAY_PROCESS_CANCELED": (
        "결제를 취소하셨습니다.",
        "다시 결제하시려면 충전 화면에서 결제하기를 눌러 주세요. 금액은 차감되지 않았습니다.",
    ),
    "PAY_PROCESS_ABORTED": (
        "결제 진행 중 오류가 발생했습니다.",
        "잠시 후 다시 시도해 주세요. 반복되면 다른 결제수단을 이용하시거나 고객센터로 문의해 주세요.",
    ),
    "REJECT_CARD_COMPANY": (
        "카드사에서 결제를 거절했습니다.",
        "한도·잔액·비밀번호를 확인하시거나 카드사에 문의해 주세요. 다른 카드로도 결제할 수 있습니다.",
    ),
    "INVALID_STOPPED_CARD": (
        "정지된 카드입니다.",
        "다른 카드로 결제해 주세요.",
    ),
    "EXCEED_MAX_AMOUNT": (
        "카드 한도를 초과했습니다.",
        "충전 금액을 낮추거나 다른 카드로 결제해 주세요.",
    ),
    "EXCEED_MAX_ONE_DAY_AMOUNT": (
        "1일 결제 한도를 초과했습니다.",
        "내일 다시 시도하시거나 다른 결제수단을 이용해 주세요.",
    ),
    "BELOW_MINIMUM_AMOUNT": (
        "최소 결제 금액 미만입니다.",
        "충전 금액을 높여 주세요.",
    ),
    "NOT_FOUND_PAYMENT_SESSION": (
        "결제 유효시간(10분)이 지났습니다.",
        "처음부터 다시 결제해 주세요. 금액은 차감되지 않았습니다.",
    ),
    "ALREADY_PROCESSED_PAYMENT": (
        "이미 처리된 결제입니다.",
        "충전 내역을 확인해 주세요. 코인이 반영되지 않았다면 고객센터로 문의해 주세요.",
    ),
    # ★아래 둘은 **사용자 잘못이 아니다** — 우리 설정 문제다. 그렇게 말해야 한다.
    "UNAUTHORIZED_KEY": (
        "결제 시스템 설정에 문제가 있습니다.",
        "고객센터로 문의해 주세요. (관리자: 결제 API 키를 확인하세요)",
    ),
    "FORBIDDEN_REQUEST": (
        "결제 시스템 설정에 문제가 있습니다.",
        "고객센터로 문의해 주세요. (관리자: 클라이언트키·시크릿키가 같은 환경의 짝인지 확인하세요)",
    ),
}

#: 우리 쪽 검증 실패 코드(벤더 호출 전에 막은 것).
CODE_AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
CODE_REFUND_CONFLICT = "REFUND_CONFLICT"
CODE_REFUND_ACCOUNT_NOT_ALLOWED = "REFUND_ACCOUNT_NOT_ALLOWED"
CODE_REFUND_ACCOUNT_REQUIRED = "REFUND_ACCOUNT_REQUIRED"
CODE_ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
CODE_ORDER_NOT_PENDING = "ORDER_NOT_PENDING"
CODE_PAYMENT_KEY_CONFLICT = "PAYMENT_KEY_CONFLICT"
CODE_NOT_CONFIGURED = "PAYMENT_NOT_CONFIGURED"

_LOCAL_REMEDIATION: dict[str, tuple[str, str]] = {
    CODE_REFUND_ACCOUNT_NOT_ALLOWED: (
        "이 결제는 가상계좌 결제가 아니어서 환불 계좌를 지정할 수 없습니다.",
        "환불금은 결제하신 수단으로 자동 반환됩니다.",
    ),
    CODE_REFUND_ACCOUNT_REQUIRED: (
        "가상계좌 결제는 환불받을 계좌 정보가 필요합니다.",
        "은행·계좌번호·예금주를 입력해 다시 요청해 주세요.",
    ),
    CODE_REFUND_CONFLICT: (
        "다른 환불 요청이 먼저 처리되었습니다.",
        "충전 내역에서 현재 환불 상태를 확인한 뒤 다시 시도해 주세요.",
    ),
    CODE_AMOUNT_MISMATCH: (
        "결제 금액이 주문 금액과 일치하지 않아 결제를 중단했습니다.",
        "충전 화면에서 처음부터 다시 진행해 주세요. 금액은 차감되지 않았습니다.",
    ),
    CODE_ORDER_NOT_FOUND: (
        "주문을 찾을 수 없습니다.",
        "충전 내역을 확인하시고, 문제가 계속되면 고객센터로 문의해 주세요.",
    ),
    CODE_ORDER_NOT_PENDING: (
        "이미 처리되었거나 취소된 주문입니다.",
        "충전 내역에서 상태를 확인해 주세요.",
    ),
    CODE_PAYMENT_KEY_CONFLICT: (
        "이 주문에 다른 결제가 이미 연결되어 있습니다.",
        "충전 내역을 확인하시고, 이중 결제가 의심되면 즉시 고객센터로 문의해 주세요.",
    ),
    CODE_NOT_CONFIGURED: (
        "현재 카드 결제를 사용할 수 없습니다.",
        "관리자에게 문의해 주세요. 계좌이체 등 다른 방법은 고객센터로 문의해 주세요.",
    ),
}


def _remediation_for(code: str, message: str) -> tuple[str, str, bool]:
    """(사용자 문구, 조치, 재시도 가치) — ★표에 없는 코드도 **반드시 무언가를 말한다**.

    이 저장소의 규율: *"실패는 사유를 표면까지 싣는다. 진단 불가는 그 자체로 장애다."*
    """
    if code in _LOCAL_REMEDIATION:
        msg, fix = _LOCAL_REMEDIATION[code]
        return msg, fix, False
    if code in _REMEDIATION:
        msg, fix = _REMEDIATION[code]
        return msg, fix, not toss_payments.is_deterministic_code(code)
    # 모르는 코드 — 벤더 문구를 그대로 보여 주되(사유를 버리지 않는다),
    # 조치는 분류에서 파생한다.
    retryable = not toss_payments.is_deterministic_code(code)
    fix = (
        "잠시 후 다시 시도해 주세요. 반복되면 고객센터로 문의해 주세요."
        if retryable
        else "다른 결제수단으로 시도하시거나 고객센터로 문의해 주세요."
    )
    return (message or "결제에 실패했습니다."), fix, retryable


def _idempotency_key(order_id: str, payment_key: str) -> str:
    """멱등키 — **주문+결제** 쌍에 고정.

    ★주문번호만 쓰면 안 되는 이유: 첫 결제가 카드사 거절로 실패한 뒤 사용자가 **다른 카드로**
      다시 결제하면 `paymentKey` 가 달라지는데, 멱등키가 같으면 토스가 **첫 실패 결과를
      그대로 돌려줄** 수 있다 → 정상 결제가 영구히 막힌다.
    ★`paymentKey` 만 쓰면 다른 주문에 같은 결제를 붙이는 재생공격을 벤더 층에서 못 가른다.
    둘을 합치면 "같은 주문의 같은 결제 재시도"에만 멱등이 걸린다 — 정확히 우리가 원하는 것.
    """
    return f"propai-confirm-{order_id}-{payment_key}"[:200]


# ─────────────────────────────────────────────────────────────────────────────
# 승인
# ─────────────────────────────────────────────────────────────────────────────
async def confirm_toss_payment(
    db: AsyncSession,
    *,
    order_id: str,
    payment_key: str,
    claimed_amount: int,
    current_user_id: str,
) -> dict[str, Any]:
    """토스 결제 승인 → 코인 지급.

    Args:
        order_id: ★우리 주문 **uuid**. 이 값을 토스의 `orderId` 로 보낸다.

            **왜 `order_no` 가 아니라 uuid 인가** — 두 적대 렌즈가 반대 결론을 냈고,
            근거를 대조해 판정했다(2026-08-27):
              · 정합성 렌즈: `order_no` 를 보내야 `GET /v1/payments/orders/{orderId}` 로
                paymentKey 없이 복구할 수 있다
              · 보안 렌즈: `order_no` 는 `secrets.token_hex(4)` = **32비트**뿐이고,
                텔레메트리 라우트 정규화가 uuid 는 `{id}` 로 지우지만 `CO…` 형식은
                **원문 그대로** `platform_events` 에 남긴다(무인증 쓰기 엔드포인트)
            ★**복구는 어느 쪽이든 된다** — 그 조회는 *우리가 보낸 값*으로 하면 되기 때문이다.
              따라서 복구 논거는 둘을 가르지 못하고, 엔트로피·누출 논거만 남는다 → **uuid**.
            사람이 읽을 주문번호는 `orderName` 에 실어 토스 대시보드에서 보이게 한다.

        claimed_amount: ★클라이언트(리다이렉트 쿼리)가 주장하는 금액. **믿지 않는다** —
            서버 저장값과 대조만 하고, 토스에는 **서버 저장값**을 보낸다.

    Raises:
        PaymentRejectedError: 결제가 거절됐다(돈 안 움직임) — 사유·조치 포함
        PaymentUnresolvedError: ★결과 미확정 — 실패로 표시하면 안 된다
    """
    if not toss_payments.is_configured():
        raise PaymentRejectedError(
            CODE_NOT_CONFIGURED,
            *_LOCAL_REMEDIATION[CODE_NOT_CONFIGURED][:1],
            remediation=_LOCAL_REMEDIATION[CODE_NOT_CONFIGURED][1],
            http_status=503,
        )

    await coin_orders_service.ensure_schema(db)

    # 1) 같은 주문의 동시 승인을 직렬화. `create_order` 가 쓰는 것과 같은 관례.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lk)::bigint)"),
        {"lk": f"coin_order_confirm:{order_id}"},
    )

    # 2) 주문 조회 + 소유자 검증.
    #    ★소유자 불일치도 「없음」으로 답한다 — 존재 여부가 새면 주문번호 열거의 단서가 된다.
    row = (
        await db.execute(
            text(
                "SELECT id, user_id, tenant_id, amount_krw, coin_krw, status, provider,"
                "       provider_ref, order_no"
                "  FROM coin_orders WHERE id = CAST(:oid AS uuid)"
            ),
            {"oid": order_id},
        )
    ).mappings().first()

    if row is None or str(row["user_id"]) != str(current_user_id):
        await payment_receipts.record(
            event=payment_receipts.EVENT_BLOCKED,
            order_id=order_id,
            user_id=str(current_user_id),
            payment_key=payment_key,
            amount_krw=float(claimed_amount),
            toss_code=CODE_ORDER_NOT_FOUND,
            toss_message="주문 없음 또는 소유자 불일치",
        )
        msg, fix, _ = _remediation_for(CODE_ORDER_NOT_FOUND, "")
        raise PaymentRejectedError(
            CODE_ORDER_NOT_FOUND, msg, remediation=fix, http_status=404
        )

    order_no = str(row["order_no"])
    server_amount = int(round(float(row["amount_krw"])))

    # 3) ★금액 검증 — 문서가 명시한 요구사항. 클라이언트 조작 방어의 핵심.
    #    토스에 보내는 값도 **서버 저장값**이다(claimed 를 통과시키지 않는다).
    if int(claimed_amount) != server_amount:
        await payment_receipts.record(
            event=payment_receipts.EVENT_BLOCKED,
            order_id=order_id,
            order_no=order_no,
            user_id=str(current_user_id),
            payment_key=payment_key,
            amount_krw=float(claimed_amount),
            toss_code=CODE_AMOUNT_MISMATCH,
            toss_message=f"주장 {claimed_amount} ≠ 저장 {server_amount}",
        )
        msg, fix, _ = _remediation_for(CODE_AMOUNT_MISMATCH, "")
        raise PaymentRejectedError(CODE_AMOUNT_MISMATCH, msg, remediation=fix)

    # 4) 이미 처리된 주문 판정.
    if str(row["status"]) == "paid":
        if str(row["provider_ref"] or "") == payment_key:
            # ★같은 결제의 재요청 = 멱등 성공. 새로고침·중복 클릭이 오류로 보이면 안 된다.
            return {
                "id": order_id,
                "order_no": order_no,
                "status": "paid",
                "coin_krw": round(float(row["coin_krw"]), 2),
                "already_applied": True,
            }
        # 다른 결제키가 붙어 있다 — ★이중 결제 의심. 조용히 넘기지 않는다.
        await payment_receipts.record(
            event=payment_receipts.EVENT_BLOCKED,
            order_id=order_id,
            order_no=order_no,
            user_id=str(current_user_id),
            payment_key=payment_key,
            amount_krw=float(server_amount),
            toss_code=CODE_PAYMENT_KEY_CONFLICT,
            toss_message=f"기존 provider_ref={row['provider_ref']}",
        )
        msg, fix, _ = _remediation_for(CODE_PAYMENT_KEY_CONFLICT, "")
        raise PaymentRejectedError(
            CODE_PAYMENT_KEY_CONFLICT, msg, remediation=fix, http_status=409
        )

    if str(row["status"]) != "pending":
        await payment_receipts.record(
            event=payment_receipts.EVENT_BLOCKED,
            order_id=order_id,
            order_no=order_no,
            user_id=str(current_user_id),
            payment_key=payment_key,
            toss_code=CODE_ORDER_NOT_PENDING,
            toss_message=f"status={row['status']}",
        )
        msg, fix, _ = _remediation_for(CODE_ORDER_NOT_PENDING, "")
        raise PaymentRejectedError(
            CODE_ORDER_NOT_PENDING, msg, remediation=fix, http_status=409
        )

    # 5) ★벤더 호출 **전에** 흔적을 남긴다(독립 커밋). 6 번에서 죽으면 이게 유일한 단서다.
    requested_receipt = await payment_receipts.record(
        event=payment_receipts.EVENT_REQUESTED,
        order_id=order_id,
        order_no=order_no,
        user_id=str(current_user_id),
        payment_key=payment_key,
        amount_krw=float(server_amount),
    )

    # 6) ★돈이 움직이는 지점.
    try:
        payment = await toss_payments.confirm(
            payment_key=payment_key,
            order_id=order_id,
            amount=server_amount,
            idempotency_key=_idempotency_key(order_id, payment_key),
        )
    except TossNotConfiguredError as e:
        msg, fix, _ = _remediation_for(CODE_NOT_CONFIGURED, "")
        raise PaymentRejectedError(
            CODE_NOT_CONFIGURED, msg, remediation=fix, http_status=503
        ) from e
    except TossError as e:
        await payment_receipts.record(
            event=payment_receipts.EVENT_REJECTED,
            order_id=order_id,
            order_no=order_no,
            user_id=str(current_user_id),
            payment_key=payment_key,
            amount_krw=float(server_amount),
            toss_code=e.code,
            toss_message=e.message,
        )
        # 주문은 pending 으로 둔다 — 사용자가 **다른 카드로 다시** 결제할 수 있어야 한다.
        # ★여기서 주문을 failed 로 닫으면 재시도가 불가능해진다.
        await _note_fail_reason(db, order_id, f"{e.code}: {e.message}"[:500])
        msg, fix, retryable = _remediation_for(e.code, e.message)
        raise PaymentRejectedError(
            e.code, msg, remediation=fix, retryable=retryable
        ) from e
    except TossOutcomeUnknownError as e:
        # 7-c) ★모른다. **재조회로 확정을 시도**한다 — 이것이 복구의 1차 방어선.
        unknown_receipt = await payment_receipts.record(
            event=payment_receipts.EVENT_UNKNOWN,
            order_id=order_id,
            order_no=order_no,
            user_id=str(current_user_id),
            payment_key=payment_key,
            amount_krw=float(server_amount),
            toss_message=str(e),
        )
        payment = await _try_resolve(payment_key=payment_key, order_id=order_id)
        if payment is None:
            raise PaymentUnresolvedError(
                "결제 결과를 확인하지 못했습니다. 카드에서 결제되었을 수 있으니"
                " 중복 결제하지 마시고 충전 내역을 확인해 주세요.",
                receipt_id=unknown_receipt or requested_receipt,
                order_no=order_no,
            ) from e
        # ★재조회로 살아 돌아온 결제도 **금액을 대조한다**(형제 `reconcile_order` 와 같은 문장).
        #   이 줄이 없으면 다른 주문의 소액 결제 `paymentKey` 로 고액 주문이 지급될 수 있다.
        if not vendor_amount_matches(payment, server_amount):
            await payment_receipts.record(
                event=payment_receipts.EVENT_BLOCKED,
                order_id=order_id, order_no=order_no, user_id=str(current_user_id),
                payment_key=payment_key, amount_krw=float(server_amount),
                toss_code=CODE_AMOUNT_MISMATCH,
                toss_message=f"재조회 {payment.get('totalAmount')} ≠ 저장 {server_amount}",
                raw=payment,
            )
            msg, fix, _ = _remediation_for(CODE_AMOUNT_MISMATCH, "")
            raise PaymentRejectedError(CODE_AMOUNT_MISMATCH, msg, remediation=fix) from e
        await payment_receipts.record(
            event=payment_receipts.EVENT_RECONCILED,
            order_id=order_id,
            order_no=order_no,
            user_id=str(current_user_id),
            payment_key=payment_key,
            amount_krw=float(server_amount),
            toss_code=str(payment.get("status") or ""),
            raw=payment,
            toss_message="미확정 → 재조회로 확정",
        )

    # ── ★7-0) HTTP 200 은 「승인됨」이 아니다 ────────────────────────────────
    # 보안 렌즈가 실측으로 잡은 CRITICAL(2026-08-27):
    #   **가상계좌**를 고르면 `POST /v1/payments/confirm` 이 **200 을 주면서**
    #   `status: "WAITING_FOR_DEPOSIT"` 와 계좌번호를 돌려준다 — **돈은 한 푼도 안 움직였다.**
    #   HTTP 코드로 판정하면 사용자는 **입금하지 않고 코인을 받는다**(무한 무료 충전).
    # ★그래서 **상태 필드**로 판정한다. `DONE` 이 아니면 지급하지 않는다.
    #   입금이 실제로 들어오면 웹훅(`deposit_callback`)이 다시 우리를 깨우고,
    #   그때 **재조회로 확정**해 지급한다.
    status_str = str(payment.get("status") or "").upper()
    if status_str != STATUS_DONE:
        await payment_receipts.record(
            event=payment_receipts.EVENT_UNKNOWN if status_str in _PENDING_STATUSES
            else payment_receipts.EVENT_REJECTED,
            order_id=order_id,
            order_no=order_no,
            user_id=str(current_user_id),
            payment_key=payment_key,
            amount_krw=float(server_amount),
            toss_code=status_str or "NO_STATUS",
            toss_message="승인 응답이 DONE 이 아니다 — 지급하지 않는다",
            raw=payment,
        )
        if status_str in _PENDING_STATUSES:
            # 실패가 아니다 — **아직 돈이 안 들어왔을 뿐**이다. 그렇게 말한다.
            raise PaymentPendingError(
                _PENDING_MESSAGE.get(
                    status_str, "결제가 완료되지 않았습니다. 잠시 후 충전 내역을 확인해 주세요."
                ),
                status=status_str,
                order_no=order_no,
                payment=payment,
            )
        msg, fix, retryable = _remediation_for(status_str, "")
        raise PaymentRejectedError(status_str or "NOT_DONE", msg, remediation=fix, retryable=retryable)

    # 7-a) 승인됨 — ★돈이 움직였다. 원문을 먼저 보관한다.
    await payment_receipts.record(
        event=payment_receipts.EVENT_APPROVED,
        order_id=order_id,
        order_no=order_no,
        user_id=str(current_user_id),
        payment_key=payment_key,
        amount_krw=float(server_amount),
        toss_code=str(payment.get("status") or ""),
        raw=payment,
    )

    # 8) 우리 원장 반영.
    try:
        result = await coin_orders_service.confirm_order(
            db,
            order_id=order_id,
            owner_user_id=str(row["user_id"]),
            provider="toss",
            provider_ref=payment_key,
            actor_id=str(current_user_id),
        )
    except IntegrityError as e:
        # ★`ux_coin_orders_provider_ref` 위반 = **이 paymentKey 가 다른 주문에 이미 묶여 있다.**
        #   「미확정」이 아니라 **충돌**이다 — 뭉치면 조사자가 엉뚱한 곳을 판다.
        #   (옛 코드는 이것도 Exception 으로 삼켜 500 이 나갔다 — 정합성 렌즈 D5)
        await db.rollback()
        await payment_receipts.record(
            event=payment_receipts.EVENT_BLOCKED,
            order_id=order_id,
            order_no=order_no,
            user_id=str(current_user_id),
            payment_key=payment_key,
            amount_krw=float(server_amount),
            toss_code=CODE_PAYMENT_KEY_CONFLICT,
            toss_message="provider_ref 유니크 위반 — 이 결제는 다른 주문에 이미 연결됨",
            raw=payment,
        )
        logger.error(
            "★결제키 재사용 — order_id=%s payment_key=%s… (승인은 이미 성립)",
            order_id, payment_key[:8],
        )
        msg, fix, _ = _remediation_for(CODE_PAYMENT_KEY_CONFLICT, "")
        raise PaymentRejectedError(
            CODE_PAYMENT_KEY_CONFLICT, msg, remediation=fix, http_status=409
        ) from e
    except Exception as e:  # noqa: BLE001 — 어떤 실패든 「돈만 낸 상태」다
        await payment_receipts.record(
            event=payment_receipts.EVENT_APPLY_FAILED,
            order_id=order_id,
            order_no=order_no,
            user_id=str(current_user_id),
            payment_key=payment_key,
            amount_krw=float(server_amount),
            toss_message=f"{type(e).__name__}: {e}"[:500],
            raw=payment,
        )
        logger.exception(
            "★승인됐으나 원장 반영 실패 — order_no=%s payment_key=%s (복구 필요)",
            order_no,
            payment_key,
        )
        raise PaymentUnresolvedError(
            "결제는 완료되었으나 코인 반영이 지연되고 있습니다."
            " 잠시 후 충전 내역을 확인해 주세요. 반영되지 않으면 고객센터로 문의해 주세요.",
            receipt_id=requested_receipt,
            order_no=order_no,
        ) from e

    await payment_receipts.record(
        event=payment_receipts.EVENT_APPLIED,
        order_id=order_id,
        order_no=order_no,
        user_id=str(current_user_id),
        payment_key=payment_key,
        amount_krw=float(server_amount),
    )
    result["already_applied"] = False
    return result


def vendor_amount_matches(payment: dict[str, Any], server_amount_krw: float) -> bool:
    """벤더가 말하는 결제금액이 **우리 서버 저장액**과 같은가.

    ## 왜 공용 함수인가 (§29 형제 불일치 — 2026-09-06 실측)

    이 대조는 `reconcile_order` 에는 **있었고** `confirm_toss_payment` 에는 **없었다**
    (`totalAmount` 가 파일 전체에서 `reconcile_order` 안에만 3회 등장 · confirm 경로 **0회**).
    한쪽만 있는 검증은 **없는 것과 같다** — 결함은 검증이 없는 쪽으로 흐른다.

    ★특히 위험한 자리는 `_try_resolve()` 다. 그 함수는 **사용자가 보낸 `paymentKey`** 로
      조회한 Payment 객체를 그대로 돌려주는데, 그것이 **어느 주문의 것인지·얼마인지**
      아무도 묻지 않은 채 지급으로 흘렀다. 승인 요청(`confirm`)은 서버 금액을 실어 보내
      벤더가 대신 걸러 주지만, **재조회(`get_payment`)에는 그 방어가 없다** —
      벤더에게 금액을 말하지 않고 그냥 묻기 때문이다.

    ★금액을 인덱스에 위임하지 않는다. 종전에 이 자리를 막던 유일한 것은
      `ux_coin_orders_provider_ref` 부분 유니크 인덱스였는데, 그것은 **무결성 장치이지
      금액 검증 장치가 아니다**(어느 주문에도 안 묶인 `DONE` 결제가 있으면 뚫린다).
    """
    return int(payment.get("totalAmount") or 0) == int(round(float(server_amount_krw)))


async def _try_resolve(*, payment_key: str, order_id: str) -> dict[str, Any] | None:
    """미확정 결제를 **재조회**로 확정한다. 승인돼 있으면 Payment 객체, 아니면 None.

    ★`paymentKey` 조회가 실패해도 우리 `orderId` 로 한 번 더 묻는다 — 두 경로 다 실패해야
      진짜 「모름」이다. 한 경로만 보고 포기하면 복구 가능한 건을 미해결로 남긴다.
    """
    for probe in (
        lambda: toss_payments.get_payment(payment_key),
        lambda: toss_payments.get_payment_by_order_id(order_id),
    ):
        try:
            payment = await probe()
        except (TossError, TossOutcomeUnknownError, TossNotConfiguredError):
            continue
        if str(payment.get("status") or "").upper() == "DONE":
            return payment
    return None


async def _note_fail_reason(db: AsyncSession, order_id: str, reason: str) -> None:
    """실패 사유를 주문에 남긴다 — ★상태는 바꾸지 않는다(재시도 가능해야 한다)."""
    try:
        await db.execute(
            text("UPDATE coin_orders SET fail_reason = :r WHERE id = :id AND status='pending'"),
            {"r": reason, "id": order_id},
        )
        await db.commit()
    except Exception:  # noqa: BLE001 — 사유 기록 실패가 결제 응답을 막으면 안 된다
        logger.exception("fail_reason 기록 실패 order_id=%s", order_id)


# ─────────────────────────────────────────────────────────────────────────────
# 취소 · 환불
# ─────────────────────────────────────────────────────────────────────────────
#: 결제 완료분을 환불했을 때의 주문 상태.
#: ★`canceled`(미결제 주문 취소)와 **뭉치면 안 된다** — 매출 집계가 틀린다.
#:   미결제 취소는 매출에 들어온 적이 없고, 환불은 **들어왔다가 나간 것**이다.
STATUS_REFUNDED = "refunded"

#: 부분 환불 누계를 담을 컬럼(멱등 ALTER — 이 저장소의 lazy DDL 관례).
_REFUND_DDL = (
    "ALTER TABLE coin_orders ADD COLUMN IF NOT EXISTS refunded_krw numeric(14,2) DEFAULT 0",
    "ALTER TABLE coin_orders ADD COLUMN IF NOT EXISTS refunded_at timestamptz",
    "ALTER TABLE coin_orders ADD COLUMN IF NOT EXISTS refund_reason text",
)


async def ensure_refund_schema(db: AsyncSession) -> None:
    """환불 컬럼 멱등 보장."""
    for stmt in _REFUND_DDL:
        await db.execute(text(stmt))


CODE_NOT_REFUNDABLE = "NOT_REFUNDABLE"
CODE_INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE_FOR_REFUND"
CODE_REFUND_AMOUNT_INVALID = "REFUND_AMOUNT_INVALID"

_LOCAL_REMEDIATION.update(
    {
        CODE_NOT_REFUNDABLE: (
            "이 주문은 환불할 수 없습니다.",
            "결제 완료된 주문만 환불할 수 있습니다. 충전 내역에서 상태를 확인해 주세요.",
        ),
        CODE_INSUFFICIENT_BALANCE: (
            "이미 사용하신 코인은 환불되지 않습니다(미사용분만 환불).",
            "남아 있는 미사용 코인만큼만 환불할 수 있습니다. 금액을 비워 두고 요청하시면"
            " 미사용분 전액이 환불됩니다. 그 외는 고객센터로 문의해 주세요.",
        ),
        CODE_REFUND_AMOUNT_INVALID: (
            "환불 금액이 올바르지 않습니다.",
            "0원보다 크고 남은 결제금액 이하여야 합니다.",
        ),
    }
)


async def _available_balance(db: AsyncSession, user_id: str) -> float:
    """지금 환불 가능한 코인 잔액(원).

    ★`topup_krw`(충전분)만 본다 — 월 기본 제공분(`monthly_base_krw`)은 **우리가 준 것**이라
      환불 대상이 아니다. 이걸 뭉치면 **주지도 않은 돈을 환불**하게 된다.
    """
    v = (
        await db.execute(
            text("SELECT COALESCE(topup_krw, 0) FROM public.users WHERE id = :u"),
            {"u": user_id},
        )
    ).scalar()
    return float(v or 0.0)


async def refund_toss_payment(
    db: AsyncSession,
    *,
    order_no: str,
    reason: str,
    amount: int | None,
    actor_id: str,
    is_admin: bool,
    refund_receive_account: dict[str, str] | None = None,
) -> dict[str, Any]:
    """결제 환불(전액 또는 부분) — 벤더 취소 + 코인 환수를 **같은 순서로** 처리한다.

    순서가 왜 이런가:
      1. **먼저 코인을 환수**한다(우리가 되돌릴 수 있는 쪽).
      2. 그 다음 벤더 취소를 부른다(되돌릴 수 없는 쪽).
      3. 벤더 취소가 실패하면 **환수를 되돌린다**.

    ★반대로 하면(벤더 먼저) 취소는 됐는데 코인 환수가 실패해서 **사용자가 돈도 받고 코인도
      가진** 상태가 된다. 우리가 손해를 보는 쪽이므로 조용히 지나간다 — 더 나쁘다.
      이쪽 순서는 실패 시 **사용자에게 유리한 상태**(코인 유지)로 남고, 그건 눈에 띈다.

    Args:
        amount: None 이면 남은 전액. 부분 환불은 남은 결제금액 이내.
        is_admin: 관리자는 소유자 검증을 건너뛴다(대리 처리).
    """
    if not toss_payments.is_configured():
        msg, fix = _LOCAL_REMEDIATION[CODE_NOT_CONFIGURED]
        raise PaymentRejectedError(CODE_NOT_CONFIGURED, msg, remediation=fix, http_status=503)

    await coin_orders_service.ensure_schema(db)
    await ensure_refund_schema(db)

    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lk)::bigint)"),
        {"lk": f"coin_order_refund:{order_no}"},
    )

    row = (
        await db.execute(
            text(
                "SELECT id, user_id, amount_krw, coin_krw, status, provider, provider_ref,"
                "       COALESCE(refunded_krw, 0) AS refunded_krw"
                "  FROM coin_orders WHERE order_no = :ono"
            ),
            {"ono": order_no},
        )
    ).mappings().first()

    if row is None or (not is_admin and str(row["user_id"]) != str(actor_id)):
        msg, fix = _LOCAL_REMEDIATION[CODE_ORDER_NOT_FOUND]
        raise PaymentRejectedError(CODE_ORDER_NOT_FOUND, msg, remediation=fix, http_status=404)

    order_id = str(row["id"])
    owner_id = str(row["user_id"])
    payment_key = str(row["provider_ref"] or "")

    if str(row["status"]) != "paid" or str(row["provider"] or "") != "toss" or not payment_key:
        msg, fix = _LOCAL_REMEDIATION[CODE_NOT_REFUNDABLE]
        raise PaymentRejectedError(CODE_NOT_REFUNDABLE, msg, remediation=fix, http_status=409)

    paid = int(round(float(row["amount_krw"])))
    already = int(round(float(row["refunded_krw"])))
    order_remaining = paid - already

    # ── ★환불 정책: **미사용분만** (소유자 확정 2026-08-27) ───────────────────
    #
    # 법적 근거(법령 렌즈 조사): 충전(코인 구매)과 소비(AI 분석 실행)는 **별개 거래**다.
    # 전자상거래법 §17②5(*"용역 또는 디지털콘텐츠의 제공이 개시된 경우"*)는 **소비한
    # 부분에만** 걸린다. 미사용 잔액은 제공이 개시되지 않았으므로 청약철회 대상이고,
    # 그래서 **부분 취소**가 법적으로도 정확한 구조이며 토스 `cancelAmount` 와 그대로 맞는다.
    #
    # ★종전 구현은 「잔액이 모자라면 **전부 거절**」이었다 — 그건 다른 규칙이다.
    #   미사용분이 3,000원 남았는데 10,000원 주문을 환불하려 하면 옛 코드는 0원을 돌려줬다.
    #   지금은 **3,000원을 돌려주고, 7,000원은 왜 못 돌려주는지 말한다.**
    #
    # ★한계(정직): `coin_ledger_events` 에 **주문→소비 귀속(lot)이 없다.** 그래서
    #   "이 주문에서 온 코인이 얼마나 남았나"를 정확히는 모른다. 계정 전체 충전잔액을
    #   상한으로 쓰는 **보수적 근사**다 — 실제 미사용분보다 **적게** 환불될 수는 있어도
    #   **더 많이** 환불되지는 않는다(음수 잔액이 구조적으로 불가능하다).
    balance = int(await _available_balance(db, owner_id))
    refundable = max(0, min(order_remaining, balance))

    if refundable <= 0:
        msg, fix = _LOCAL_REMEDIATION[CODE_INSUFFICIENT_BALANCE]
        raise PaymentRejectedError(
            CODE_INSUFFICIENT_BALANCE,
            f"{msg}(이 주문의 미환불 잔액 {order_remaining:,}원 · 계정 충전잔액 {balance:,}원)",
            remediation=fix,
            http_status=409,
        )

    if amount is None:
        # 금액을 안 주면 **미사용분 전액**. 이미 쓴 만큼은 못 돌려준다.
        want = refundable
    else:
        want = int(amount)
        if want <= 0 or want > order_remaining:
            msg, fix = _LOCAL_REMEDIATION[CODE_REFUND_AMOUNT_INVALID]
            raise PaymentRejectedError(
                CODE_REFUND_AMOUNT_INVALID,
                f"{msg}(요청 {want:,}원 · 이 주문의 미환불 잔액 {order_remaining:,}원)",
                remediation=fix,
            )
        if want > refundable:
            # ★명시 금액이 미사용분을 넘으면 **조용히 줄이지 않는다** — 사용자가 모른다.
            msg, fix = _LOCAL_REMEDIATION[CODE_INSUFFICIENT_BALANCE]
            raise PaymentRejectedError(
                CODE_INSUFFICIENT_BALANCE,
                f"{msg}(요청 {want:,}원 · 환불 가능한 미사용분 {refundable:,}원)",
                remediation=(
                    f"{refundable:,}원까지 환불할 수 있습니다. 금액을 비워 두고 다시 요청하시면"
                    " 미사용분 전액이 환불됩니다."
                ),
                http_status=409,
            )

    # ★부분 취소가 **벤더에서 가능한지** 먼저 묻는다(무과금 GET).
    #   가능하지 않은데 부분 취소를 보내면 토스가 거절하고, 그 사이 우리는 이미 코인을
    #   환수한 상태가 된다. 되돌릴 수는 있지만 **묻는 편이 싸다**.
    partial = want < order_remaining or already > 0
    # ★한 번만 묻고 두 판정에 쓴다(무과금 GET). 부분취소 가능성 + **결제수단**.
    probe = None
    if partial or refund_receive_account is not None:
        probe = await _fetch_payment(payment_key=payment_key, order_id=order_id)

    # ── ★수령계좌는 **가상계좌 결제일 때만** 허용한다 ─────────────────────────
    #
    # 카드 환불은 **원 결제수단으로 되돌아가므로** 계좌를 지정할 이유가 없다.
    # 그런데 종전에는 어떤 결제든 임의 계좌를 실어 보낼 수 있었다 —
    # 계정을 탈취한 사람이 **피해자 결제분을 자기 계좌로 빼내는 통로**다.
    # 형식 검증(라우터의 `RefundReceiveAccount`)만으로는 이 경로가 닫히지 않는다.
    #
    # ★두 모집단을 **같은 자리에서** 가른다: VA 가 아닌데 계좌를 주면 거절하고,
    #   VA 인데 계좌가 없으면 벤더가 어차피 거절하므로 **미리** 사유를 말한다.
    method = str((probe or {}).get("method") or "")
    is_va = bool((probe or {}).get("virtualAccount")) or "가상계좌" in method
    if refund_receive_account is not None and probe is not None and not is_va:
        raise PaymentRejectedError(
            CODE_REFUND_ACCOUNT_NOT_ALLOWED,
            "이 결제는 가상계좌 결제가 아니어서 환불 계좌를 지정할 수 없습니다.",
            remediation="환불금은 결제하신 수단으로 자동 반환됩니다. 계좌 정보를 빼고 다시 요청해 주세요.",
            http_status=400,
        )
    if refund_receive_account is None and is_va:
        raise PaymentRejectedError(
            CODE_REFUND_ACCOUNT_REQUIRED,
            "가상계좌 결제는 환불받을 계좌 정보가 필요합니다.",
            remediation="은행·계좌번호·예금주를 입력해 다시 요청해 주세요.",
            http_status=400,
        )

    if partial:
        if probe is not None and probe.get("isPartialCancelable") is False:
            raise PaymentRejectedError(
                "NOT_ALLOWED_PARTIAL_REFUND",
                "이 결제수단은 부분 환불이 되지 않습니다(전액 취소만 가능).",
                remediation=(
                    "이미 사용하신 코인이 있어 전액 취소는 자동으로 처리할 수 없습니다."
                    " 고객센터로 문의해 주시면 확인 후 처리해 드리겠습니다."
                ),
                http_status=409,
            )

    # 1) 먼저 코인 환수(되돌릴 수 있는 쪽).
    #    ★조건부 UPDATE — 잔액이 그 사이 줄었으면 성립하지 않는다(TOCTOU 방어).
    clawed = (
        await db.execute(
            text(
                "UPDATE public.users"
                "   SET topup_krw = COALESCE(topup_krw,0) - :a,"
                "       billing_budget_krw = COALESCE(monthly_base_krw,0)"
                "                          + COALESCE(topup_krw,0) - :a"
                " WHERE id = :u AND COALESCE(topup_krw,0) >= :a"
                " RETURNING id"
            ),
            {"a": float(want), "u": owner_id},
        )
    ).first()
    if clawed is None:
        msg, fix = _LOCAL_REMEDIATION[CODE_INSUFFICIENT_BALANCE]
        raise PaymentRejectedError(
            CODE_INSUFFICIENT_BALANCE, msg, remediation=fix, http_status=409
        )

    await coin_ledger_service.append_event(
        db=db,
        user_id=owner_id,
        entry_type="order_refunded",
        amount_krw=-float(want),
        description=f"환불(주문 {order_no}, {reason[:80]})",
        ref_type="coin_order",
        ref_id=order_id,
        created_by=str(actor_id),
    )
    new_refunded = already + want
    # ★**CAS(compare-and-set)** — `refunded_krw` 가 우리가 읽은 값 그대로일 때만 쓴다.
    #
    #   자문락은 `pg_advisory_xact_lock` 이라 **아래 `commit()` 에서 풀린다.** 그런데
    #   벤더 취소는 그 **뒤에** 돌고 최대 30초 걸린다(되돌릴 수 없는 쪽이므로 트랜잭션을
    #   쥔 채 부를 수 없다). 그 창에 두 번째 환불이 들어와 커밋할 수 있다.
    #   조건 없이 쓰면 그 사람의 기록을 **조용히 덮는다** — 실측 시나리오:
    #
    #     R1 읽음(already=0) → R2 읽음(already=5000) → R2 커밋(refunded=10000)
    #     → R1 의 벤더 취소 실패 → R1 이 refunded 를 **0 으로 되돌림**
    #     → 사용자는 카드로 10,000 환불받고 코인 5,000 을 그대로 보유(순이득)
    #
    #   잔액 차감은 이미 조건부(`AND topup_krw >= :a`)였는데 **주문 행만 무방비**였다.
    applied = (
        await db.execute(
            text(
                "UPDATE coin_orders"
                "   SET refunded_krw = :r, refunded_at = now(), refund_reason = :why,"
                "       status = CASE WHEN :r >= amount_krw THEN :refunded ELSE status END"
                " WHERE id = :id AND COALESCE(refunded_krw, 0) = :expected"
                " RETURNING id"
            ),
            {
                "r": float(new_refunded), "why": reason[:500], "id": order_id,
                "refunded": STATUS_REFUNDED, "expected": float(already),
            },
        )
    ).first()
    if applied is None:
        # 그 사이 다른 환불이 성립했다. **코인을 이미 뺐으므로 되돌리고** 거절한다 —
        # 벤더에는 아직 아무것도 보내지 않았으므로 여기서 멈추는 것이 가장 싸다.
        await db.rollback()
        raise PaymentRejectedError(
            CODE_REFUND_CONFLICT,
            "다른 환불 요청이 먼저 처리되어 이 요청을 중단했습니다.",
            remediation="충전 내역에서 현재 환불 상태를 확인한 뒤 다시 시도해 주세요.",
            http_status=409,
        )
    await db.commit()

    # 2) 벤더 취소(되돌릴 수 없는 쪽).
    try:
        cancel_result = await toss_payments.cancel(
            payment_key=payment_key,
            cancel_reason=reason[:200],
            # ★전액 취소는 **처음이자 전부**일 때만(`cancelAmount` 생략 = 전액).
            #   미사용분만 환불하는 경우는 언제나 부분 취소다.
            cancel_amount=None if (want == order_remaining and already == 0) else want,
            idempotency_key=f"propai-cancel-{order_no}-{new_refunded}"[:200],
            refund_receive_account=refund_receive_account,
        )
    except (TossError, TossOutcomeUnknownError, TossNotConfiguredError) as e:
        # 3) 벤더가 거절/미확정 → 환수를 **되돌린다**.
        #    ★미확정도 되돌린다: 취소가 성립했을 수도 있지만, 여기서 코인을 뺏은 채 두면
        #      "환불도 안 되고 코인도 없는" 최악이 된다. 사용자에게 유리한 쪽으로 남기고
        #      미해결 영수증으로 사람이 보게 만든다.
        # ★`expected_now` = 내가 방금 쓴 값. 그 사이 남이 바꿨으면 되돌리지 않는다(CAS).
        await _revert_clawback(db, owner_id=owner_id, order_id=order_id, amount=want,
                               previous_refunded=already, actor_id=str(actor_id),
                               expected_now=new_refunded)
        code = getattr(e, "code", "CANCEL_UNRESOLVED")
        await payment_receipts.record(
            event=payment_receipts.EVENT_CANCEL_REJECTED,
            order_id=order_id, order_no=order_no, user_id=owner_id,
            payment_key=payment_key, amount_krw=float(want),
            toss_code=code, toss_message=str(e)[:500],
        )
        if isinstance(e, TossOutcomeUnknownError):
            raise PaymentUnresolvedError(
                "환불 처리 결과를 확인하지 못했습니다. 코인은 그대로 두었습니다."
                " 고객센터로 문의해 주시면 확인해 드리겠습니다.",
                receipt_id=None, order_no=order_no,
            ) from e
        msg, fix, retryable = _remediation_for(code, getattr(e, "message", str(e)))
        raise PaymentRejectedError(code, msg, remediation=fix, retryable=retryable) from e

    await payment_receipts.record(
        event=payment_receipts.EVENT_CANCELED,
        order_id=order_id, order_no=order_no, user_id=owner_id,
        payment_key=payment_key, amount_krw=float(want),
        toss_code=str(cancel_result.get("status") or ""), raw=cancel_result,
    )
    # ★요청과 실제가 다르면 **그 사실과 이유를 응답에 싣는다.** 조용히 적게 돌려주면
    #   사용자는 나머지가 어디 갔는지 모른다(진단 불가는 그 자체로 장애다).
    consumed = max(0, order_remaining - refundable)
    return {
        "order_no": order_no,
        "refunded_krw": want,
        "refunded_total_krw": new_refunded,
        "remaining_krw": paid - new_refunded,
        "status": STATUS_REFUNDED if new_refunded >= paid else "paid",
        # 아래 셋이 「미사용분만」 정책을 화면에 설명하게 한다.
        "order_remaining_before_krw": order_remaining,
        "unrefundable_consumed_krw": consumed,
        "partial": want < order_remaining,
        "policy": "unused_only",
    }


async def _revert_clawback(
    db: AsyncSession, *, owner_id: str, order_id: str, amount: int,
    previous_refunded: int, actor_id: str, expected_now: int,
) -> None:
    """환수를 되돌린다 — 벤더 취소가 성립하지 않았을 때.

    ★원장에도 **되돌림을 기록**한다. 조용히 되돌리면 잔액과 원장이 어긋난다.
    """
    try:
        await db.execute(
            text(
                "UPDATE public.users"
                "   SET topup_krw = COALESCE(topup_krw,0) + :a,"
                "       billing_budget_krw = COALESCE(monthly_base_krw,0)"
                "                          + COALESCE(topup_krw,0) + :a"
                " WHERE id = :u"
            ),
            {"a": float(amount), "u": owner_id},
        )
        await coin_ledger_service.append_event(
            db=db, user_id=owner_id, entry_type="order_refund_reverted",
            amount_krw=float(amount),
            description=f"환불 실패로 코인 원복(주문 {order_id})",
            ref_type="coin_order", ref_id=order_id, created_by=actor_id,
        )
        # ★**CAS** — 내가 쓴 값(`expected_now`)이 그대로일 때만 되돌린다.
        #   그 사이 다른 환불이 성립했다면 **되돌리지 않는다** — 되돌리면 그 사람의
        #   기록이 사라지고, 사용자는 환불받고도 코인을 보유하게 된다.
        reverted = (
            await db.execute(
                text(
                    "UPDATE coin_orders"
                    "   SET refunded_krw = :r, status = CASE WHEN :r <= 0 THEN 'paid' ELSE status END"
                    " WHERE id = :id AND COALESCE(refunded_krw, 0) = :expected_now"
                    " RETURNING id"
                ),
                {
                    "r": float(previous_refunded), "id": order_id,
                    "expected_now": float(expected_now),
                },
            )
        ).first()
        await db.commit()
        if reverted is None:
            # ★조용히 넘기지 않는다 — 원장과 주문 행이 어긋난 채로 남는다.
            #   미해결 영수증으로 남겨 **관리자 화면에 뜨게** 한다(진단 불가는 그 자체로 장애).
            await payment_receipts.record(
                event=payment_receipts.EVENT_APPLY_FAILED,
                order_id=order_id, user_id=owner_id, amount_krw=float(amount),
                toss_code=CODE_REFUND_CONFLICT,
                toss_message=(
                    "환불 되돌리기를 적용하지 못했습니다(그 사이 다른 환불이 성립). "
                    "코인 잔액은 복원했으나 주문의 환불액 기록은 사람이 확인해야 합니다."
                ),
            )
    except Exception:  # noqa: BLE001
        logger.exception(
            "★환수 되돌리기 실패 — order_id=%s amount=%s (수동 복구 필요)", order_id, amount
        )


# ─────────────────────────────────────────────────────────────────────────────
# 정합성 회복 (reconciliation)
#
# ★이 절이 없으면 `payment_receipts` 는 **읽히지 않는 원장**이 된다.
#   기록만 하고 그것으로 아무것도 고치지 않으면, 이 저장소가 반복해 데인
#   *"수집은 되는데 조회되지 않는다"* 가 그대로 재발한다.
# ─────────────────────────────────────────────────────────────────────────────
async def reconcile_order(
    db: AsyncSession, *, order_id: str, actor_id: str
) -> dict[str, Any]:
    """한 주문을 **토스에 다시 물어** 우리 원장과 맞춘다.

    네 가지 결과를 **구별**한다(뭉치면 조사가 불가능해진다):

    | 토스 | 우리 | 처리 |
    |---|---|---|
    | `DONE` | pending | ★**지급한다** — 「돈만 낸 상태」의 복구 |
    | `DONE` | paid | 이미 맞다(변경 없음) |
    | `WAITING_FOR_DEPOSIT`/`CANCELED` | paid | ★**환수한다** — 입금오류·취소가 무료 코인이 되는 것을 막는다 |
    | 결제 없음 | pending | 사용자가 결제를 안 마쳤다(정상) |
    """
    await coin_orders_service.ensure_schema(db)
    await ensure_refund_schema(db)
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lk)::bigint)"),
        {"lk": f"coin_order_confirm:{order_id}"},
    )
    row = (
        await db.execute(
            text(
                # ★`refunded_krw` 를 반드시 읽는다 — 이것을 안 읽으면 **정당한 부분환불 뒤에
                #   전액을 한 번 더 환수**한다(2026-09-06 실측 결함).
                "SELECT id, user_id, order_no, amount_krw, status, provider, provider_ref,"
                "       COALESCE(refunded_krw, 0) AS refunded_krw, paid_at"
                "  FROM coin_orders WHERE id = CAST(:oid AS uuid)"
            ),
            {"oid": order_id},
        )
    ).mappings().first()
    if row is None:
        return {"order_id": order_id, "action": "not_found"}

    order_no = str(row["order_no"])
    owner = str(row["user_id"])
    our_status = str(row["status"])
    payment_key = str(row["provider_ref"] or "")

    payment = await _fetch_payment(payment_key=payment_key or None, order_id=order_id)
    if payment is None:
        return {
            "order_id": order_id, "order_no": order_no, "our_status": our_status,
            "action": "no_payment_at_vendor",
            "note": "토스에 이 주문의 결제가 없습니다(사용자가 결제를 마치지 않았을 수 있습니다).",
        }

    vendor_status = str(payment.get("status") or "").upper()
    vendor_key = str(payment.get("paymentKey") or payment_key or "")

    # ── ① 벤더는 승인, 우리는 미지급 → 지급한다 ────────────────────────────
    if vendor_status == STATUS_DONE and our_status == "pending":
        await payment_receipts.record(
            event=payment_receipts.EVENT_APPROVED, order_id=order_id, order_no=order_no,
            user_id=owner, payment_key=vendor_key,
            amount_krw=float(payment.get("totalAmount") or row["amount_krw"]),
            toss_code=vendor_status, raw=payment,
        )
        # ★금액 대조 — 재조회 결과라도 **서버 저장액과 다르면 지급하지 않는다.**
        if not vendor_amount_matches(payment, float(row["amount_krw"])):
            await payment_receipts.record(
                event=payment_receipts.EVENT_BLOCKED, order_id=order_id, order_no=order_no,
                user_id=owner, payment_key=vendor_key, toss_code=CODE_AMOUNT_MISMATCH,
                toss_message=f"벤더 {payment.get('totalAmount')} ≠ 저장 {row['amount_krw']}",
            )
            return {"order_id": order_id, "order_no": order_no, "action": "amount_mismatch"}
        try:
            result = await coin_orders_service.confirm_order(
                db, order_id=order_id, owner_user_id=owner,
                provider="toss", provider_ref=vendor_key, actor_id=actor_id,
            )
        except (IntegrityError, coin_orders_service.OrderNotConfirmableError) as e:
            await db.rollback()
            return {"order_id": order_id, "order_no": order_no, "action": "apply_conflict",
                    "note": str(e)[:200]}
        await payment_receipts.record(
            event=payment_receipts.EVENT_APPLIED, order_id=order_id, order_no=order_no,
            user_id=owner, payment_key=vendor_key, amount_krw=float(row["amount_krw"]),
            toss_message="정합성 회복으로 지급",
        )
        return {"order_id": order_id, "order_no": order_no, "action": "granted", **result}

    # ── ② 벤더가 승인을 거둬들였는데 우리는 지급 상태 → 환수한다 ────────────
    #     ★법령 렌즈 실측: 가상계좌 **입금 오류**는 `DONE → WAITING_FOR_DEPOSIT` 로
    #       되돌아간다(v1.5+). 이걸 처리하지 않으면 **입금 오류가 무료 코인이 된다.**
    if our_status == "paid" and vendor_status in _ALL_REVOKING_STATUSES:
        # ── 환수액은 **상태 이름이 아니라 금액에서 파생**한다 ──────────────────
        #
        # ## 왜 (2026-09-06 실측 · 원문 4줄로 확증한 결함)
        #
        # 종전 코드는 `_REVOKED_STATUSES` 라는 **상태 목록**에 걸리면 `row["amount_krw"]`
        # (=주문 **전액**)를 환수했고, `refunded_krw` 를 **한 번도 읽지 않았다.**
        # 그런데 부분환불은 `status` 를 `paid` 로 **남긴다**(`:832` 의 CASE 가 전액일 때만
        # 전환한다). 그리고 `PARTIAL_CANCELED` 가 그 목록에 들어 있었다. 그래서:
        #
        #     10,000원 결제 → 3,000원 부분환불(정상) → 토스가 취소 웹훅을 보낸다
        #     → `our_status=='paid'` ∧ `PARTIAL_CANCELED ∈ 목록` → **10,000원 전액 환수**
        #
        # 사용자는 3,000원만 돌려받고 **10,000원어치 코인을 잃는다.** 공격자가 필요 없다 —
        # **정상 흐름이 스스로 발화**하고, 관리자의 「바로잡기」 버튼도 같은 경로를 탄다.
        #
        # ## 처방 — 목록형을 버리고 **벤더 잔액과 우리 잔액의 차**로 판정한다
        #
        #     우리가 유효하다고 보는 액   = amount_krw - refunded_krw
        #     벤더가 유효하다고 보는 액   = balanceAmount (부분취소) / 0 (전면 철회)
        #     환수액                      = 그 차이 (음수면 환수 없음)
        #
        # ★이렇게 하면 새 상태값이 생겨도 **금액이 판정한다** — 목록이 상한이 되지 않는다.
        expected_remaining = float(row["amount_krw"]) - float(row["refunded_krw"] or 0)
        vendor_remaining = _vendor_remaining_krw(payment, vendor_status)

        if vendor_remaining is None:
            # ★**모르는 것은 0이 아니다.** 부분취소인데 `balanceAmount` 가 없으면 환수액을
            #   계산할 수 없다 — 그때 전액을 빼는 것이 바로 위 결함이었다. 사람에게 넘긴다.
            await payment_receipts.record(
                event=payment_receipts.EVENT_BLOCKED, order_id=order_id, order_no=order_no,
                user_id=owner, payment_key=vendor_key, toss_code=vendor_status, raw=payment,
                toss_message="부분취소 잔액(balanceAmount)을 알 수 없어 환수액을 계산할 수 없습니다.",
            )
            return {
                "order_id": order_id, "order_no": order_no, "action": "clawback_undetermined",
                "vendor_status": vendor_status, "our_status": our_status,
                "note": "벤더 잔액 미상 — 관리자 확인이 필요합니다.",
            }

        claw = expected_remaining - vendor_remaining
        if claw <= 0:
            # 이미 맞다 — 부분환불이 정확히 반영된 정상 상태다(환수할 것이 없다).
            return {
                "order_id": order_id, "order_no": order_no, "action": "already_consistent",
                "our_status": our_status, "vendor_status": vendor_status,
                "expected_remaining_krw": expected_remaining,
                "vendor_remaining_krw": vendor_remaining,
            }

        # ★**실제로 빠진 액수**를 받아 그것으로 원장을 쓴다. 종전엔 차감이 `GREATEST(0, …)`
        #   로 잘리는데 원장에는 **무조건 전액**을 적어 `coin_ledger_events` 합 ≠ `topup_krw`
        #   가 됐다(같은 결함의 두 번째 얼굴).
        clawed = (
            await db.execute(
                text(
                    "WITH prev AS (SELECT COALESCE(topup_krw,0) AS b FROM public.users WHERE id = :u),"
                    "     upd AS ("
                    "       UPDATE public.users"
                    "          SET topup_krw = GREATEST(0, COALESCE(topup_krw,0) - :a),"
                    "              billing_budget_krw = COALESCE(monthly_base_krw,0)"
                    "                                 + GREATEST(0, COALESCE(topup_krw,0) - :a)"
                    "        WHERE id = :u RETURNING COALESCE(topup_krw,0) AS after_krw)"
                    " SELECT upd.after_krw, prev.b - upd.after_krw AS applied_krw FROM upd, prev"
                ),
                {"a": float(claw), "u": owner},
            )
        ).first()
        applied = float(clawed[1]) if clawed else 0.0
        await coin_ledger_service.append_event(
            db=db, user_id=owner, entry_type="order_refund_reverted",
            amount_krw=-applied,
            description=(
                f"벤더 승인 철회로 환수(주문 {order_no}, {vendor_status};"
                f" 대상 {claw:.0f}원 중 실제 {applied:.0f}원)"
            ),
            ref_type="coin_order", ref_id=order_id, created_by=actor_id,
        )
        # ★**`paid_at` 을 지우지 않는다.** 형제(`coin_orders_service.py:317-319`)가
        #   *"진짜 잠금은 `paid_at IS NULL` 이다 — 한 번이라도 결제가 성립한 주문은
        #   구조적으로 이 절에 들어올 수 없다"* 고 **선언**하는데, 종전 이 줄이 그
        #   전제를 지워 전자상거래법 시행령 §6①(청약철회 기록 **5년 보존**)의 대상 주문을
        #   즉시 파기 대상으로 재분류했다. 선언이 참이 되려면 형제가 그것을 안 건드려야 한다.
        await db.execute(
            text("UPDATE coin_orders SET status='pending' WHERE id=CAST(:oid AS uuid)"),
            {"oid": order_id},
        )
        await db.commit()
        await payment_receipts.record(
            event=payment_receipts.EVENT_RECONCILED, order_id=order_id, order_no=order_no,
            user_id=owner, payment_key=vendor_key, amount_krw=applied,
            toss_code=vendor_status, raw=payment,
            toss_message="★벤더가 승인을 철회 — 코인 환수",
        )
        return {
            "order_id": order_id, "order_no": order_no, "action": "clawed_back",
            "vendor_status": vendor_status,
            "clawed_back_krw": applied,
            "expected_remaining_krw": expected_remaining,
            "vendor_remaining_krw": vendor_remaining,
            "remaining_topup_krw": float(clawed[0]) if clawed else None,
        }

    return {
        "order_id": order_id, "order_no": order_no, "action": "already_consistent",
        "our_status": our_status, "vendor_status": vendor_status,
    }


#: ★벤더가 승인을 **통째로** 거둬들인 상태 — 벤더 쪽 유효 잔액이 **0** 이다.
#:  `PARTIAL_CANCELED` 는 **여기 없다**: 부분취소는 잔액이 남으므로 전면 철회가 아니다.
#:  (2026-09-06 — 이 집합에 그것이 들어 있어서 정당한 부분환불 뒤 전액이 재환수됐다)
_REVOKED_STATUSES = frozenset({"CANCELED", "WAITING_FOR_DEPOSIT", "ABORTED", "EXPIRED"})

#: 일부만 취소된 상태 — 잔액은 벤더의 `balanceAmount` 가 말한다.
_PARTIALLY_REVOKED_STATUSES = frozenset({"PARTIAL_CANCELED"})

#: 환수 여부를 **검토해야 하는** 상태 전체(둘의 합집합 — 파생형이라 한쪽만 늘려도 따라온다).
_ALL_REVOKING_STATUSES = _REVOKED_STATUSES | _PARTIALLY_REVOKED_STATUSES


def _vendor_remaining_krw(payment: dict[str, Any], vendor_status: str) -> float | None:
    """벤더가 **아직 유효하다고 보는 금액**. 알 수 없으면 `None`(★0이 아니다).

    · 전면 철회(`CANCELED`·`EXPIRED`·`ABORTED`·`WAITING_FOR_DEPOSIT`) → **0**
    · 부분취소(`PARTIAL_CANCELED`) → `balanceAmount`. 그 값이 없거나 숫자가 아니면
      **미상**이다 — 미상을 0으로 취급하면 전액을 빼게 되고, 그것이 바로 이 봉합의 대상이다.
    """
    if vendor_status in _REVOKED_STATUSES:
        return 0.0
    raw = payment.get("balanceAmount")
    # ★**이중 가드다**(전수 변이 실측 2026-09-06 · `[72/163] 조건무력화 ★생존`).
    #   이 줄을 지워도 아래 `float(None)` 이 `TypeError` 로 같은 `except` 에 걸려
    #   **결과가 같다.** 그래도 남겨 두는 이유는 「없음」과 「형식 불량」이 **다른 사실**임을
    #   읽는 사람에게 보이기 위해서다. 생존이 곧 구멍은 아니므로 여기 적어 둔다
    #   (변이 점수를 부풀리려고 공허한 단언을 추가하지 않는다).
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


async def _fetch_payment(*, payment_key: str | None, order_id: str) -> dict[str, Any] | None:
    """결제 재조회 — paymentKey 우선, 없거나 실패하면 우리 orderId 로.

    ★한 경로 실패로 포기하지 않는다. 두 경로 다 실패해야 「없음」이다.
    """
    probes = []
    if payment_key:
        probes.append(lambda: toss_payments.get_payment(payment_key))
    probes.append(lambda: toss_payments.get_payment_by_order_id(order_id))
    for probe in probes:
        try:
            return await probe()
        except (TossError, TossOutcomeUnknownError, TossNotConfiguredError):
            continue
    return None


async def reconcile_from_webhook(
    db: AsyncSession, *, payment_key: str | None, order_id: str | None
) -> dict[str, Any]:
    """웹훅이 알려 준 결제를 **재조회로 확정**하고 원장을 맞춘다.

    ★웹훅 본문의 상태·금액을 **쓰지 않는다.** 서명이 없으므로 누구나 보낼 수 있고,
      그대로 믿으면 무한 무료 충전 경로가 된다. 여기서 하는 일은 딱 하나 —
      **우리 주문을 특정한 뒤 `reconcile_order` 를 부르는 것**이다.
    """
    resolved_order_id = order_id
    if not resolved_order_id and payment_key:
        # 우리 주문을 모르면 `provider_ref` 로 역인덱스 조회(유니크 인덱스가 받쳐 준다).
        r = (
            await db.execute(
                text("SELECT id FROM coin_orders WHERE provider_ref = :pk"),
                {"pk": payment_key},
            )
        ).first()
        resolved_order_id = str(r[0]) if r else None
    if not resolved_order_id:
        return {"action": "unknown_order", "note": "웹훅이 가리키는 주문을 찾지 못했습니다."}
    try:
        # 웹훅의 orderId 는 우리가 보낸 uuid 여야 한다 — 아니면 조작이다.
        import uuid as _u

        _u.UUID(str(resolved_order_id))
    except (ValueError, AttributeError, TypeError):
        return {"action": "invalid_order_id"}
    return await reconcile_order(db, order_id=str(resolved_order_id), actor_id="toss_webhook")
