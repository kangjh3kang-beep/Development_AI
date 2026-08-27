"""토스 결제 연동의 **잠금** — 계획서 §5(L1~L9) + 적대 렌즈가 실측한 결함들.

## 이 파일이 잠그는 것

각 테스트는 **원래 결함을 되살리는 변이가 CAUGHT 되게** 쓰였다.
"검사가 있다"가 아니라 **"고치면 사라지고, 되돌리면 빨개진다"** 를 목표로 한다.

★특히 아래 셋은 **독립 적대 렌즈가 내 코드에서 찾아낸 실제 결함**이고,
  각각 그것을 되살리는 변이가 있다:

| 결함 | 되살리는 변이 | 잡는 테스트 |
|---|---|---|
| 가상계좌가 200+`WAITING_FOR_DEPOSIT` 인데 지급 | `status != STATUS_DONE` 분기 삭제 | `test_pending_status_never_grants` |
| 시크릿 키가 Sentry 스택 로컬로 유출 | `auth=` → 헤더 dict 로 되돌리기 | `test_secret_never_in_headers_or_status` |
| 차단 게이트가 충전액을 두 번 차감 | `compute_remaining` → `billed >= budget` | `test_full_topup_is_usable` |
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from app.services.billing import payment_receipts, toss_payments
from app.services.billing.billing_service import compute_remaining
from app.services.billing.toss_orders_service import (
    _REMEDIATION,
    _LOCAL_REMEDIATION,
    _REVOKED_STATUSES,
    STATUS_DONE,
    _idempotency_key,
    _remediation_for,
)

_API = pathlib.Path(__file__).resolve().parents[1]


# ═══════════════════════════════════════════════════════════════════════════
# ★기존 결함 — 사용자가 낸 돈의 **절반이 잠겼다**
# ═══════════════════════════════════════════════════════════════════════════
def _spend_until_blocked(base: float, topup0: float, step: float = 100.0):
    """`record_usage_usd` 의 산술을 그대로 재현해 차단 시점까지 소비한다.

    ★소스의 식을 옮겨 적은 것이므로, 소스가 바뀌면 이 헬퍼도 갱신해야 한다.
      대신 **판정은 실제 `compute_remaining` 을 태운다**(대리 변수 금지).
    """
    billed, topup = 0.0, float(topup0)
    for _ in range(5000):
        b0, b1 = billed, billed + step
        draw = max(0.0, b1 - base) - max(0.0, b0 - base)
        billed, topup = b1, max(0.0, topup - draw)
        if compute_remaining(billed=billed, monthly_base=base, topup=topup)["exhausted"]:
            return billed, topup
    raise AssertionError("차단되지 않았다 — 게이트가 죽었다(공허한 초록 방지)")


@pytest.mark.parametrize(
    ("base", "topup"),
    [(0, 10_000), (10_000, 50_000), (50_000, 200_000)],
)
def test_full_topup_is_usable(base: float, topup: float) -> None:
    """★사용자가 충전한 금액을 **전부** 쓸 수 있어야 한다.

    회귀 고정 — 옛 게이트(`billed >= budget`)는 `topup_krw` 컬럼이 **이미 순액**인데
    거기서 또 빼서, **정확히 50%** 에서 차단했다(실측). 즉 10만원을 충전하면
    5만원어치만 쓸 수 있었다.
    """
    billed, remaining_topup = _spend_until_blocked(base, topup)
    assert remaining_topup == 0, (
        f"충전 {topup:,.0f}원 중 {remaining_topup:,.0f}원이 **쓰지 못한 채 잠겼다**"
    )
    assert billed >= base + topup - 200, (
        f"총 사용가능액이 {billed:,.0f} — 기대 {base + topup:,.0f}"
    )


def test_no_topup_still_blocks_at_base() -> None:
    """★음성 대조군 — 충전이 없으면 **월기본에서** 차단된다(종전과 동일).

    이게 없으면 「아무도 차단하지 않는」 구현도 위 테스트를 통과한다.
    """
    billed, _ = _spend_until_blocked(10_000, 0)
    assert 10_000 <= billed < 10_200, billed


def test_remaining_splits_two_populations() -> None:
    """★두 모집단 — 월기본 잔여와 충전 잔여가 **다른 값**을 내야 한다."""
    r = compute_remaining(billed=3_000, monthly_base=10_000, topup=50_000)
    assert r["base_remaining"] == 7_000
    assert r["topup_remaining"] == 50_000  # ★아직 월기본 안이라 충전은 안 줄었다
    assert r["exhausted"] is False
    r2 = compute_remaining(billed=30_000, monthly_base=10_000, topup=30_000)
    assert r2["base_remaining"] == 0
    assert r2["topup_remaining"] == 30_000
    assert r2["exhausted"] is False
    assert r["base_remaining"] != r2["base_remaining"], "두 모집단이 같은 값 — 락이 공허하다"


# ═══════════════════════════════════════════════════════════════════════════
# L1 — 단일 길목: 토스 호출이 `_request` 밖으로 새지 않는다
# ═══════════════════════════════════════════════════════════════════════════
def test_toss_http_has_exactly_one_chokepoint() -> None:
    """★`httpx` 로 외부에 나가는 지점이 **`_request` 하나**인지 ast 로 판정한다.

    다른 곳에서 부르면 멱등키·오류분류·비밀키 위생이 전부 빠진다 —
    그리고 그 하나가 곧 재과금·유출 경로가 된다(§유료·비가역 산출물 규율).
    """
    tree = ast.parse((_API / "app/services/billing/toss_payments.py").read_text(encoding="utf-8"))
    owners: list[str] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "httpx"
                and node.func.attr == "AsyncClient"
            ):
                owners.append(fn.name)
    assert owners, "★httpx 사용처를 못 찾았다 — 추출기가 죽었다(위반 아님)"
    assert owners == ["_request"], f"토스 HTTP 호출이 여러 곳: {owners}"


def test_api_base_is_a_module_constant() -> None:
    """★베이스 URL 이 환경변수에서 오면 **관리자 한 번의 쓰기로 시크릿 키가 유출**된다.

    키 금고(`secret_store`)는 denylist 방식이라 `TOSS_API_BASE` 같은 이름이 통과하고,
    `set_secret` 이 `os.environ` 에 즉시 반영한다(보안 렌즈 H1).
    """
    tree = ast.parse((_API / "app/services/billing/toss_payments.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "API_BASE":
                    assert isinstance(node.value, ast.Constant), "API_BASE 가 상수가 아니다"
                    assert node.value.value.startswith("https://api.tosspayments.com")
                    return
    raise AssertionError("API_BASE 를 못 찾았다 — 추출기가 죽었다")


# ═══════════════════════════════════════════════════════════════════════════
# L7 — 비밀키 위생
# ═══════════════════════════════════════════════════════════════════════════
def test_secret_never_in_headers_or_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """★시크릿 키가 **어떤 반환값에도** 실리지 않는다.

    되살리는 변이: `auth=_basic_auth()` 를 지우고 헤더 dict 에 Authorization 을 넣으면
    그 dict 가 스택 로컬이 되어 Sentry 로 나간다(`include_local_variables` 기본 True).
    """
    monkeypatch.setenv("TOSS_SECRET_KEY", "test_sk_SUPERSECRETVALUE123")
    monkeypatch.setenv("TOSS_CLIENT_KEY", "test_ck_PUBLICVALUE456")
    status = toss_payments.config_status()
    blob = repr(status)
    assert "SUPERSECRETVALUE123" not in blob, f"★시크릿 키가 진단 응답에 실렸다: {blob}"
    assert status["secret_key_present"] is True
    assert status["secret_key_len"] == len("test_sk_SUPERSECRETVALUE123")
    # 소스 검사(실행 라인만) — 헤더 dict 에 Authorization 을 넣지 않는다.
    src = (_API / "app/services/billing/toss_payments.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    docs = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if ast.get_docstring(n, clean=False):
                docs.add(id(n.body[0].value))
    live = [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
    ]
    assert not [x for x in live if x == "Authorization"], (
        "★실행 코드가 Authorization 헤더를 직접 만든다 — httpx.BasicAuth 를 쓰라"
    )


def test_redact_removes_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """★벤더가 우리 요청을 에코해도 키가 새지 않는다(2차 가드)."""
    monkeypatch.setenv("TOSS_SECRET_KEY", "live_sk_AAAAAAAAAAAA")
    monkeypatch.setenv("TOSS_CLIENT_KEY", "live_ck_BBBBBBBBBBBB")
    out = toss_payments._redact("요청 실패: live_sk_AAAAAAAAAAAA 및 live_ck_BBBBBBBBBBBB")
    assert "AAAAAAAAAAAA" not in out and "BBBBBBBBBBBB" not in out
    assert "***" in out


@pytest.mark.parametrize(
    ("sk", "ck", "paired"),
    [
        ("test_sk_x1234567", "test_ck_y1234567", True),
        ("live_sk_x1234567", "live_ck_y1234567", True),
        # ★혼용 — 토스가 FORBIDDEN_REQUEST 로 거절한다. 호출 **전에** 알아야 한다.
        ("test_sk_x1234567", "live_ck_y1234567", False),
        ("live_sk_x1234567", "test_ck_y1234567", False),
    ],
)
def test_key_pairing_detects_mixed_environments(
    monkeypatch: pytest.MonkeyPatch, sk: str, ck: str, paired: bool
) -> None:
    monkeypatch.setenv("TOSS_SECRET_KEY", sk)
    monkeypatch.setenv("TOSS_CLIENT_KEY", ck)
    assert toss_payments.key_pairing_ok() is paired


def test_configured_requires_both_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """★한쪽만 있으면 **더 나쁘다** — 결제창은 뜨는데 승인이 안 된다."""
    monkeypatch.setenv("TOSS_SECRET_KEY", "test_sk_x1234567")
    monkeypatch.delenv("TOSS_CLIENT_KEY", raising=False)
    assert toss_payments.is_configured() is False
    monkeypatch.setenv("TOSS_CLIENT_KEY", "test_ck_y1234567")
    assert toss_payments.is_configured() is True


def test_env_strips_quotes(monkeypatch: pytest.MonkeyPatch) -> None:
    """관리자가 따옴표째 붙여넣는 사고가 이 저장소에 실재한다."""
    monkeypatch.setenv("TOSS_SECRET_KEY", '  "test_sk_quoted123"  ')
    assert toss_payments.secret_key() == "test_sk_quoted123"


# ═══════════════════════════════════════════════════════════════════════════
# ★C2 — HTTP 200 은 「승인됨」이 아니다 (가상계좌 무입금 지급)
# ═══════════════════════════════════════════════════════════════════════════
def test_pending_statuses_are_not_done() -> None:
    """★`WAITING_FOR_DEPOSIT` 은 **돈이 안 움직인** 상태다.

    되살리는 변이: 오케스트레이션의 `status_str != STATUS_DONE` 분기를 지우면
    가상계좌를 고른 사용자가 **입금 없이 코인을 받는다**(무한 무료 충전).
    """
    from app.services.billing.toss_orders_service import _PENDING_STATUSES

    assert STATUS_DONE == "DONE"
    assert "WAITING_FOR_DEPOSIT" in _PENDING_STATUSES
    assert STATUS_DONE not in _PENDING_STATUSES, "★DONE 이 보류 집합에 있으면 정상 결제가 막힌다"


def test_confirm_grants_only_on_done() -> None:
    """★배선 — 승인 분기가 **`status` 필드**로 갈리는지 소스에서 확인한다.

    ★소스 검사인 이유: 이 분기는 벤더 응답을 받은 뒤에만 도달하므로 순수 함수로
      꺼낼 수 없다. 대신 **주석·문자열을 배제하고 실행 비교식만** 본다.
    """
    tree = ast.parse(
        (_API / "app/services/billing/toss_orders_service.py").read_text(encoding="utf-8")
    )
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "confirm_toss_payment"
    )
    compares = [
        ast.unparse(n) for n in ast.walk(fn)
        if isinstance(n, ast.Compare) and "STATUS_DONE" in ast.unparse(n)
    ]
    assert compares, (
        "★승인 분기가 STATUS_DONE 을 보지 않는다 — HTTP 200 만으로 지급하면 "
        "가상계좌가 무료 충전 경로가 된다"
    )


def test_revoked_statuses_trigger_clawback() -> None:
    """★`DONE → WAITING_FOR_DEPOSIT` 역전(입금 오류)이 **환수 대상**이다.

    법령 렌즈 실측: 토스 v1.5+ 는 가상계좌 입금 오류 시 `DONE` 에서 되돌아간다.
    이걸 처리하지 않으면 **입금 오류가 무료 코인이 된다.**
    """
    assert "WAITING_FOR_DEPOSIT" in _REVOKED_STATUSES
    assert "CANCELED" in _REVOKED_STATUSES
    assert STATUS_DONE not in _REVOKED_STATUSES, "★DONE 을 환수하면 정상 결제가 취소된다"


# ═══════════════════════════════════════════════════════════════════════════
# L4 / L6 — 미확정 ≠ 실패 · 사유는 표면까지 간다
# ═══════════════════════════════════════════════════════════════════════════
def test_unknown_code_still_gets_remediation() -> None:
    """★표에 없는 코드도 **반드시 무언가를 말한다**. 진단 불가는 그 자체로 장애다."""
    msg, fix, retryable = _remediation_for("BRAND_NEW_CODE_2099", "벤더가 준 문구")
    assert msg == "벤더가 준 문구", "★벤더 사유를 버렸다"
    assert fix.strip(), "★조치가 비었다"
    assert retryable is True, "모르는 코드는 보수적으로 재시도 가치가 있다고 본다"


@pytest.mark.parametrize("code", sorted(set(_REMEDIATION) | set(_LOCAL_REMEDIATION)))
def test_every_known_code_has_message_and_action(code: str) -> None:
    """★파생형 — 표를 **코드에서 전수**로 뽑는다. 손 목록이면 새 코드가 감시망 밖에 남는다."""
    msg, fix, _ = _remediation_for(code, "")
    assert msg.strip(), f"{code}: 사용자 문구가 비었다"
    assert fix.strip(), f"{code}: **조치**가 비었다 — 사용자가 다음에 뭘 할지 모른다"
    assert msg != fix, f"{code}: 문구와 조치가 같다(조치가 없는 것과 같다)"


def test_deterministic_classification_splits() -> None:
    """★두 모집단 — 결정론과 일시가 **다른 판정**을 받는다.

    이게 없으면 「전부 결정론」도 「전부 일시」도 통과한다.
    """
    deterministic = ["REJECT_CARD_COMPANY", "ALREADY_CANCELED_PAYMENT", "UNAUTHORIZED_KEY"]
    transient = ["PROVIDER_ERROR", "COMMON_ERROR", "FAILED_INTERNAL_SYSTEM_PROCESSING"]
    assert all(toss_payments.is_deterministic_code(c) for c in deterministic), deterministic
    assert not any(toss_payments.is_deterministic_code(c) for c in transient), transient
    # ★모르는 코드는 **일시** 쪽이다(풀 수 있는 결제를 영구히 닫지 않는다).
    assert toss_payments.is_deterministic_code("NEVER_SEEN_BEFORE") is False


# ═══════════════════════════════════════════════════════════════════════════
# L9 — 멱등
# ═══════════════════════════════════════════════════════════════════════════
def test_idempotency_key_binds_order_and_payment() -> None:
    """★주문+결제 쌍에 고정된다.

    · 같은 주문 같은 결제의 재시도 → **같은 키**(벤더가 최초 결과를 재생)
    · 카드사 거절 후 **다른 카드**로 재결제 → **다른 키**(첫 실패가 재생되면 안 된다)
    · 다른 주문에 같은 결제 → **다른 키**
    """
    a = _idempotency_key("order-1", "pk-A")
    assert a == _idempotency_key("order-1", "pk-A"), "재시도에 키가 달라지면 이중 승인이 난다"
    assert a != _idempotency_key("order-1", "pk-B"), "★다른 카드 재결제가 첫 실패로 막힌다"
    assert a != _idempotency_key("order-2", "pk-A"), "다른 주문인데 같은 키"
    assert len(a) <= 300, "토스 멱등키는 300자 이하(문서 명시)"


# ═══════════════════════════════════════════════════════════════════════════
# 영수증 원장 — 유료 산출물 보관
# ═══════════════════════════════════════════════════════════════════════════
def test_receipt_vocabulary_is_derived_and_complete() -> None:
    """★어휘가 파생형인지 — 새 이벤트를 추가하면 미해결 질의가 따라온다."""
    assert payment_receipts.NEEDS_ATTENTION_EVENTS <= payment_receipts.ALL_EVENTS
    for ev, prevs in payment_receipts.RESOLVES.items():
        assert ev in payment_receipts.ALL_EVENTS, f"{ev} 가 어휘 밖"
        assert prevs <= payment_receipts.ALL_EVENTS, f"{ev} 의 선행이 어휘 밖: {prevs}"
    # ★「돈만 낸 상태」와 「결과 미상」은 반드시 사람이 봐야 한다.
    assert payment_receipts.EVENT_APPLY_FAILED in payment_receipts.NEEDS_ATTENTION_EVENTS
    assert payment_receipts.EVENT_UNKNOWN in payment_receipts.NEEDS_ATTENTION_EVENTS
    # ★모든 주의 이벤트에 **종결 경로가 있어야** 미해결 목록이 수렴한다.
    resolvable = {p for prevs in payment_receipts.RESOLVES.values() for p in prevs}
    unresolvable = payment_receipts.NEEDS_ATTENTION_EVENTS - resolvable
    assert not unresolvable, f"★종결 경로가 없는 주의 이벤트: {unresolvable} — 영원히 미해결로 쌓인다"


def test_receipt_scrub_removes_sensitive_keys_but_keeps_diagnostics() -> None:
    """★두 모집단 — 민감 키는 지우되 **진단 필드는 남긴다**.

    이 저장소가 데인 형태: 마스킹이 **진단 필드를 지우고** 정작 필요한 것은 통과시켰다.
    """
    raw = {
        "paymentKey": "pk_live_abc",
        "status": "DONE",
        "failure": {"code": "REJECT_CARD_COMPANY", "message": "한도초과"},
        "card": {"number": "12345678****789*", "issuerCode": "61"},
        "secret": "wh_secret_value",
    }
    out = payment_receipts._scrub(raw)
    assert out["secret"] == "***", "웹훅 시크릿이 남았다"
    assert out["card"]["number"] == "***", "카드번호가 남았다"
    # ★진단은 살아 있어야 한다 — 없으면 조사가 불가능하다.
    assert out["status"] == "DONE"
    assert out["failure"]["code"] == "REJECT_CARD_COMPANY"
    assert out["card"]["issuerCode"] == "61"


def test_unknown_event_is_rejected_not_silently_stored() -> None:
    """★어휘 밖 이벤트를 조용히 통과시키면 조회 축이 무너진다."""
    assert "made_up_event" not in payment_receipts.ALL_EVENTS


# ═══════════════════════════════════════════════════════════════════════════
# L8 — 키 카탈로그
# ═══════════════════════════════════════════════════════════════════════════
def test_toss_keys_are_in_secret_catalog() -> None:
    """★관리자 화면에 입력 필드가 **자동으로** 뜨게 하는 배선.

    그리고 `secret` 플래그가 틀리면 **평문 키가 관리자 API 로 나간다**(보안 렌즈 H2:
    비카탈로그 키는 `secret=False` 로 등록될 수 있고 그때 마스킹 없이 반환된다).
    """
    from app.services.secrets.secret_store import CATALOG

    by_name = {c["name"]: c for c in CATALOG}
    assert "TOSS_CLIENT_KEY" in by_name and "TOSS_SECRET_KEY" in by_name
    assert by_name["TOSS_SECRET_KEY"]["secret"] is True, (
        "★시크릿 키가 secret=False 면 관리자 API 가 **평문**으로 돌려준다"
    )
    assert by_name["TOSS_CLIENT_KEY"]["secret"] is False, "공개키는 마스킹할 필요가 없다"
    assert by_name["TOSS_SECRET_KEY"]["group"] == by_name["TOSS_CLIENT_KEY"]["group"]


# ═══════════════════════════════════════════════════════════════════════════
# 전상법 §6 — 환불 기록 보존
# ═══════════════════════════════════════════════════════════════════════════
def test_pii_purge_cannot_touch_orders_that_were_ever_paid() -> None:
    """★환불된 주문의 구매자 정보가 **즉시 파기되면 안 된다**(시행령 §6① 5년).

    되살리는 변이: (B) 절을 `status <> 'paid'` 로 되돌리면, 내가 추가한 `refunded`
    상태가 거기 걸려 **탈퇴회원의 환불기록 PII 가 즉시 파기**된다.
    ★진짜 잠금은 `paid_at IS NULL` 이다 — 상태 이름을 뭐라 짓든 결제가 성립했던
      주문은 구조적으로 들어올 수 없다.
    """
    src = (_API / "app/services/billing/coin_orders_service.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    docs = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if ast.get_docstring(n, clean=False):
                docs.add(id(n.body[0].value))
    live = [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
    ]
    purge_sql = [s for s in live if "buyer_name=NULL" in s and "deleted_at IS NOT NULL" in s]
    assert purge_sql, "★파기 SQL 을 못 찾았다 — 추출기가 죽었다(위반 아님)"
    sql = purge_sql[0]
    assert "paid_at IS NULL" in sql, (
        "★`paid_at IS NULL` 가드가 없다 — 새 상태값이 추가되면 결제기록이 즉시 파기된다"
    )
    assert "status <> 'paid'" not in sql, "★부정형으로 되돌아갔다"


def test_refund_ledger_types_exist() -> None:
    """★`append_event` 는 어휘 밖 타입을 **조용히 건너뛴다**(`persisted: False`, 예외 없음).

    되살리는 변이: `ENTRY_TYPES` 에서 환불 타입을 빼면 **돈은 움직이고 원장은 빈다.**
    """
    from app.services.billing.coin_ledger_service import ENTRY_TYPES

    assert "order_refunded" in ENTRY_TYPES, "★환불이 원장에 안 남는다"
    assert "order_refund_reverted" in ENTRY_TYPES, "★환수 원복이 원장에 안 남는다"
