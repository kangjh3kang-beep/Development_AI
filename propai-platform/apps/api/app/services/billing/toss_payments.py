"""토스페이먼츠 v2 클라이언트 — **유료·비가역 호출의 단일 길목**.

## 왜 얇은 래퍼 하나인가

이 저장소가 반복해 데인 형태다(§유료·비가역 산출물 규율):

> 반환 지점이 여럿인 함수에 캐시를 손으로 붙이면 **반드시 하나를 빠뜨리고,
> 그 하나가 곧 재과금 경로**다.

결제 승인은 **돈이 실제로 움직이는 지점**이고 되돌릴 수 없다. 그래서 외부로 나가는
HTTP 는 `_request()` **하나만** 있고, 승인·취소·조회가 전부 그것을 경유한다.
멱등키·인증헤더·타임아웃·오류분류가 한 곳에서만 정의되므로 "한 경로만 빠뜨림"이 불가능하다.

## 세 가지 결과를 **구별**한다 (이것이 이 모듈의 핵심 계약)

| 결과 | 뜻 | 호출자가 해야 할 일 |
|---|---|---|
| 정상 반환 | 승인/취소 확정 | 원장 반영 |
| `TossError(deterministic=True)` | 벤더가 **거절**했다 — 재시도해도 같다 | 사용자에게 사유+조치 안내 |
| `TossOutcomeUnknownError` | **모른다**(타임아웃·네트워크 절단) | ★**실패로 단정 금지.** 재조회로 확정 |

★**세 번째가 이 모듈이 존재하는 이유**다. 결제 승인 요청을 보내고 응답을 못 받았을 때
"실패"로 처리하면 **돈은 빠져나갔는데 사용자는 아무것도 못 받는다.** 모르는 것은
모른다고 말해야 복구가 가능하다.

## 비밀키

`TOSS_SECRET_KEY` 는 **서버에서만** 쓰인다. 이 모듈은 키를 반환하지 않고, 오류 메시지·
로그·예외에 키가 실리지 않게 `_redact()` 를 거친다(Basic 헤더 자체가 base64 라
raw 문자열 검사만으로는 못 잡는다 — 그래서 **헤더를 아예 안 싣는다**).

`TOSS_CLIENT_KEY` 는 **공개키**다(브라우저가 쓴다). 노출돼도 안전하지만, 이 모듈은
**테스트키/라이브키를 구별**해 프로덕션에서 테스트키가 쓰이는 것을 관리자가 알 수 있게 한다.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

#: 토스페이먼츠 코어 API. 문서: https://docs.tosspayments.com/reference
API_BASE = "https://api.tosspayments.com"

#: 결제 승인은 카드사까지 왕복한다 — 짧게 끊으면 **모르는 결과**만 늘어난다.
#: 토스 문서가 승인 유효시간을 10분으로 두므로, 여기서 조급하게 끊을 이유가 없다.
CONFIRM_TIMEOUT_S = 30.0
DEFAULT_TIMEOUT_S = 15.0

_SECRET_ENV = "TOSS_SECRET_KEY"
_CLIENT_ENV = "TOSS_CLIENT_KEY"

#: 토스 테스트키 접두어(문서: 테스트 키와 라이브 키의 차이점).
_TEST_KEY_PREFIXES = ("test_",)


class TossError(RuntimeError):
    """벤더가 **명시적으로 거절**했다 — 결과를 안다.

    `deterministic=True` 면 같은 입력으로 재시도해도 결과가 같다(재시도 금지).
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int = 0,
        deterministic: bool = True,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.http_status = http_status
        self.deterministic = deterministic


class TossOutcomeUnknownError(RuntimeError):
    """★**결과를 모른다** — 돈이 움직였는지 알 수 없다.

    타임아웃·연결 절단·5xx 처럼 "요청은 나갔는데 응답을 못 받은" 상태.
    **절대 실패로 단정하지 마라.** 호출자는 `get_payment()` 로 재조회해 확정해야 한다.
    """

    def __init__(self, message: str, *, payment_key: str | None = None) -> None:
        super().__init__(message)
        self.payment_key = payment_key


class TossNotConfiguredError(RuntimeError):
    """비밀키가 없다 — 연동 자체가 꺼져 있다(장애가 아니라 미설정)."""


# ─────────────────────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────────────────────
def _env(name: str) -> str:
    """환경변수 읽기 — 앞뒤 공백·따옴표 제거.

    ★관리자가 키 금고(`secret_store`)에 붙여넣을 때 따옴표가 섞이는 사고가 이 저장소에
    실재한다(`key_sanitizer` 가 LLM 키에 대해 같은 일을 한다). 같은 위생을 적용한다.
    """
    raw = (os.environ.get(name) or "").strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        raw = raw[1:-1].strip()
    return raw


def secret_key() -> str:
    """서버 전용 비밀키. **이 함수의 반환값을 응답·로그에 싣지 마라.**"""
    return _env(_SECRET_ENV)


def client_key() -> str:
    """브라우저가 쓰는 **공개** 클라이언트 키(노출 안전)."""
    return _env(_CLIENT_ENV)


def is_configured() -> bool:
    """결제창을 띄울 수 있는가 — **공개키와 비밀키가 둘 다** 있어야 한다.

    ★한쪽만 있으면 더 나쁘다: 결제창은 뜨는데 승인이 안 되거나(비밀키 없음),
    승인 준비는 됐는데 결제창을 못 띄운다(공개키 없음). 둘 다일 때만 켠다.
    """
    return bool(secret_key()) and bool(client_key())


def is_test_mode() -> bool:
    """테스트 키를 쓰고 있는가(실제 결제가 일어나지 않는다).

    ★프로덕션에서 참이면 **매출이 0인데 아무도 모른다.** 관리자 화면이 이 값을 표시한다.
    """
    return secret_key().startswith(_TEST_KEY_PREFIXES)


def key_pairing_ok() -> bool:
    """공개키와 비밀키가 **같은 환경**의 짝인가(테스트↔라이브 혼용 탐지).

    ★혼용하면 토스가 `FORBIDDEN_REQUEST`/`UNAUTHORIZED_KEY` 로 거절한다 —
    문서가 명시한 실패 원인이다. 호출 전에 알 수 있는 것을 호출 후에 알 이유가 없다.
    """
    if not is_configured():
        return False
    return secret_key().startswith(_TEST_KEY_PREFIXES) == client_key().startswith(
        _TEST_KEY_PREFIXES
    )


def config_status() -> dict[str, Any]:
    """관리자 진단용 — **키 값은 절대 포함하지 않는다**(존재·길이·환경만)."""
    sk, ck = secret_key(), client_key()
    return {
        "configured": is_configured(),
        "secret_key_present": bool(sk),
        "secret_key_len": len(sk),
        "client_key_present": bool(ck),
        "client_key_len": len(ck),
        "test_mode": is_test_mode() if sk else None,
        "key_pairing_ok": key_pairing_ok(),
    }


def _basic_auth() -> httpx.BasicAuth:
    """Basic base64("{SECRET_KEY}:") — ★콜론을 빠뜨리면 인증이 실패한다(문서 명시).

    ★**왜 헤더 문자열이 아니라 `httpx.BasicAuth` 인가** (보안 렌즈 실측 2026-08-27):
      Sentry 의 `include_local_variables` 는 **기본이 True** 이고, 스크러버는
      **정확일치·비재귀**다(`sentry_sdk/scrubber.py:65,115`). 그래서
      `sk = secret_key()` 같은 **지역변수 이름이 denylist 에 없으면 값이 그대로 전송**된다.
      `headers = {"Authorization": "Basic …"}` 라는 지역 dict 도 마찬가지다.

      `auth=` 로 넘기면 비밀키는 **호출 프레임의 지역변수가 되지 않고**, 남는 것은
      `<httpx.BasicAuth object at 0x…>` 라는 repr 뿐이다.

    ★이 함수 안의 `_env` 지역변수는 예외를 던지지 않는 경로라 트레이스백에 안 들어간다 —
      그래도 값을 **변수에 담지 않고** 바로 넘긴다(2중).
    """
    if not secret_key():
        raise TossNotConfiguredError("TOSS_SECRET_KEY 가 설정되지 않았습니다.")
    return httpx.BasicAuth(secret_key(), "")


def _redact(text: str) -> str:
    """오류 문자열에 키가 섞이는 것을 막는다(방어적 2중 가드).

    ★1차 가드는 "헤더를 예외에 안 싣는다"이고, 이건 2차다. 벤더가 우리 요청을
    에코하는 경우가 실재하므로 값 기준으로도 한 번 더 지운다.
    """
    out = text
    for v in (secret_key(), client_key()):
        if v and len(v) >= 8:
            out = out.replace(v, "***")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 단일 길목
# ─────────────────────────────────────────────────────────────────────────────
async def _request(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    payment_key: str | None = None,
) -> dict[str, Any]:
    """★모든 토스 호출이 지나는 **유일한** 지점.

    여기 말고 다른 곳에서 `httpx` 로 토스를 부르면 멱등키·오류분류·비밀키 위생이
    전부 빠진다. `tests/test_toss_single_chokepoint.py` 가 그것을 금지한다.
    """
    # ★비밀 없는 헤더만 지역변수로 둔다(H3).
    headers = {"Content-Type": "application/json"}
    if idempotency_key:
        # 멱등키 — 같은 키로 재요청하면 토스가 **최초 결과를 그대로** 돌려준다.
        # 네트워크 재시도가 이중 승인/이중 취소가 되지 않게 하는 벤더측 방어.
        headers["Idempotency-Key"] = idempotency_key

    # ★`API_BASE` 는 **모듈 상수**다 — 환경변수로 바뀌지 않는다.
    #   키 금고(`secret_store`)는 denylist 방식이라 `TOSS_API_BASE` 같은 이름이 통과하고,
    #   `set_secret` 이 `os.environ` 에 즉시 반영한다 → 베이스 URL 이 설정 가능하면
    #   **관리자 한 번의 쓰기로 시크릿 키가 공격자 호스트로 나간다**(보안 렌즈 H1).
    url = f"{API_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout_s, auth=_basic_auth()) as cli:
            resp = await cli.request(method, url, json=json_body, headers=headers)
    except (httpx.TimeoutException, httpx.TransportError) as e:
        # ★요청은 나갔다. 도달했는지, 처리됐는지 **모른다.**
        raise TossOutcomeUnknownError(
            f"토스페이먼츠 응답을 받지 못했습니다({type(e).__name__}). 결과 미확정.",
            payment_key=payment_key,
        ) from e

    if resp.status_code == 200:
        try:
            return dict(resp.json())
        except ValueError as e:
            # 200 인데 본문이 JSON 이 아니다 — 승인은 됐을 수 있다. 모른다고 말한다.
            raise TossOutcomeUnknownError(
                "토스페이먼츠 응답을 해석하지 못했습니다. 결과 미확정.",
                payment_key=payment_key,
            ) from e

    # 오류 봉투: {"code": "...", "message": "..."}
    code, message = "UNKNOWN", ""
    try:
        payload = resp.json()
        code = str(payload.get("code") or "UNKNOWN")
        message = str(payload.get("message") or "")
    except ValueError:
        message = resp.text[:300]

    if resp.status_code >= 500:
        # ★벤더 내부 오류 — 승인이 **성립했을 수도** 있다. 실패로 단정하지 않는다.
        raise TossOutcomeUnknownError(
            _redact(f"토스페이먼츠 서버 오류({resp.status_code} {code}). 결과 미확정."),
            payment_key=payment_key,
        )

    raise TossError(
        code,
        _redact(message),
        http_status=resp.status_code,
        deterministic=is_deterministic_code(code),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 오류 분류 — **재시도해도 같은가**
# ─────────────────────────────────────────────────────────────────────────────
#: 재시도해도 결과가 같은 코드(사용자·가맹점이 무언가를 바꿔야 풀린다).
#: 출처: https://docs.tosspayments.com/reference/error-codes
_DETERMINISTIC_CODES = frozenset(
    {
        # 인증·키 문제 — 코드나 설정을 고쳐야 한다
        "UNAUTHORIZED_KEY",
        "FORBIDDEN_REQUEST",
        "INCORRECT_BASIC_AUTH_FORMAT",
        "NOT_SUPPORTED_METHOD",
        # 요청 자체가 틀렸다
        "INVALID_REQUEST",
        "INVALID_API_KEY",
        "INVALID_ORDER_ID",
        "INVALID_PAYMENT_KEY",
        "INVALID_REJECT_CARD",
        "INVALID_STOPPED_CARD",
        "INVALID_CARD_EXPIRATION",
        "INVALID_CARD_NUMBER",
        "NOT_MATCHES_CARD_NUMBER",
        # 상태가 이미 종결됐다
        "ALREADY_PROCESSED_PAYMENT",
        "ALREADY_CANCELED_PAYMENT",
        "NOT_CANCELABLE_PAYMENT",
        "NOT_CANCELABLE_AMOUNT",
        "NOT_FOUND_PAYMENT",
        "NOT_FOUND_PAYMENT_SESSION",
        # 카드사 거절 — 재시도해도 같은 카드면 같다
        "REJECT_CARD_COMPANY",
        "EXCEED_MAX_CARD_INSTALLMENT_PLAN",
        "EXCEED_MAX_AMOUNT",
        "EXCEED_MAX_ONE_DAY_AMOUNT",
        "EXCEED_MAX_PAYMENT_AMOUNT",
        "BELOW_MINIMUM_AMOUNT",
        "CARD_NOT_SUPPORTED",
        "NOT_AVAILABLE_PAYMENT",
        "PAY_PROCESS_CANCELED",
        "PAY_PROCESS_ABORTED",
        "REJECT_ACCOUNT_PAYMENT",
    }
)

#: 잠시 뒤 다시 하면 될 수 있는 코드.
_TRANSIENT_CODES = frozenset(
    {
        "PROVIDER_ERROR",
        "FAILED_INTERNAL_SYSTEM_PROCESSING",
        "FAILED_PAYMENT_INTERNAL_SYSTEM_PROCESSING",
        "COMMON_ERROR",
        "TIMEOUT_ERROR",
    }
)


def is_deterministic_code(code: str) -> bool:
    """재시도가 무의미한가.

    ★**모르는 코드는 일시로 본다**(보수적). 알려진 결정론만 결정론으로 부른다 —
    이 방향이 안전한 이유: 결정론을 일시로 오분류하면 헛된 재시도 1회지만,
    반대로 오분류하면 **풀 수 있는 결제를 영구 실패로 닫는다.**
    """
    c = (code or "").strip().upper()
    if c in _TRANSIENT_CODES:
        return False
    return c in _DETERMINISTIC_CODES


# ─────────────────────────────────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────────────────────────────────
async def confirm(
    *, payment_key: str, order_id: str, amount: int, idempotency_key: str
) -> dict[str, Any]:
    """결제 승인 — **돈이 실제로 움직이는 지점**.

    Args:
        payment_key: 결제창 인증 후 리다이렉트로 받은 값
        order_id: 최초 결제 요청에 쓴 주문번호(우리 `order_no`)
        amount: ★**서버가 저장해 둔 금액**. 리다이렉트 쿼리값을 그대로 넘기면 안 된다
            (금액 위변조 방어의 핵심 — 검증은 호출자 책임이고, 이 인자는 검증 통과분이다)
        idempotency_key: 재시도가 이중 승인이 되지 않게 하는 키

    Raises:
        TossError: 벤더가 거절(결과를 안다)
        TossOutcomeUnknownError: ★결과 미확정 — `get_payment()` 로 확정해야 한다
    """
    return await _request(
        "POST",
        "/v1/payments/confirm",
        json_body={"paymentKey": payment_key, "orderId": order_id, "amount": int(amount)},
        idempotency_key=idempotency_key,
        timeout_s=CONFIRM_TIMEOUT_S,
        payment_key=payment_key,
    )


async def cancel(
    *,
    payment_key: str,
    cancel_reason: str,
    cancel_amount: int | None = None,
    idempotency_key: str,
    refund_receive_account: dict[str, str] | None = None,
    tax_free_amount: int | None = None,
) -> dict[str, Any]:
    """결제 취소(전액 또는 부분).

    Args:
        cancel_amount: None 이면 **전액 취소**. 부분 취소는 잔액(`balanceAmount`) 이내.
        refund_receive_account: 가상계좌 결제 환불에 필수(`bank`·`accountNumber`·`holderName`).
        idempotency_key: ★취소는 승인만큼 위험하다 — 재시도가 이중 취소가 되지 않게 한다.
    """
    body: dict[str, Any] = {"cancelReason": cancel_reason}
    if cancel_amount is not None:
        body["cancelAmount"] = int(cancel_amount)
    if refund_receive_account:
        body["refundReceiveAccount"] = refund_receive_account
    if tax_free_amount is not None:
        body["taxFreeAmount"] = int(tax_free_amount)
    return await _request(
        "POST",
        f"/v1/payments/{payment_key}/cancel",
        json_body=body,
        idempotency_key=idempotency_key,
        payment_key=payment_key,
    )


async def get_payment(payment_key: str) -> dict[str, Any]:
    """결제 **재조회** — 미확정 결과를 확정하는 유일한 방법.

    ★웹훅 본문을 믿지 않는 이유도 이것이다: 토스 v2 웹훅에는 서명이 없다.
    누구든 우리 웹훅 URL 에 그럴듯한 본문을 던질 수 있다. 그래서 웹훅은
    **"뭔가 바뀌었다"는 신호로만** 쓰고, 진실은 항상 이 함수로 다시 묻는다.
    """
    return await _request("GET", f"/v1/payments/{payment_key}", payment_key=payment_key)


async def get_payment_by_order_id(order_id: str) -> dict[str, Any]:
    """주문번호로 결제 조회 — `paymentKey` 를 잃었을 때의 복구 경로.

    ★리다이렉트를 놓치면(사용자가 창을 닫음) `paymentKey` 가 우리에게 오지 않는다.
    그때도 `order_no` 는 우리가 만든 값이므로 **여기로 되찾을 수 있다.**
    이것이 없으면 "인증은 됐는데 승인 못 한 결제"를 영원히 못 찾는다.
    """
    return await _request("GET", f"/v1/payments/orders/{order_id}", payment_key=None)
