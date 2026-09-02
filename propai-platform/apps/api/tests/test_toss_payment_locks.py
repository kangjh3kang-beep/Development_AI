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
    _LOCAL_REMEDIATION,
    _REMEDIATION,
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


# ═══════════════════════════════════════════════════════════════════════════
# ★★배선 락 — 「함수가 옳다」와 「그 함수를 쓴다」는 **다른 명제**다
#
# 위 `test_full_topup_is_usable` 는 `compute_remaining` 을 **직접** 태운다. 그래서
# 그 함수를 고쳐 놓고 **호출부를 옛 식으로 되돌리면 전부 초록인 채 결함이 부활한다.**
# ★실측: 그 배선 변이를 넣었더니 **56건 전부 통과(SURVIVED)** 했다.
#
# 그래서 여기서는 **소비처를 직접 태운다.** 판정 기준은 두 모집단이다:
#   · A(옛 게이트는 차단, 새 게이트는 통과) → **갈려야 한다**
#   · B(둘 다 차단)                        → **같아야 한다**(과잉 완화 방지)
# B 가 없으면 「아무도 차단하지 않는」 구현도 A 를 통과한다.
# ═══════════════════════════════════════════════════════════════════════════
import app.services.billing.billing_service as _bs  # noqa: E402

_TIER = "power"  # 과금 등급(런타임 실측: TIER_BILLING = power/superpower/master)

#: (billed, budget, monthly_base, topup) — `ensure_cycle` 반환 형태
#: ★A: 월기본 10,000 소진 + 충전 25,000 **남음**.
#:    옛 식 `billed >= budget` = 35,000 >= 35,000 → **차단**(★잘못)
#:    새 식 = 충전이 남았으므로 → **통과**
_ROW_TOPUP_LEFT = (_TIER, 35_000.0, 35_000.0, 10_000.0, 25_000.0)
#: ★B(대조군): 충전 0 · 월기본 소진 → 둘 다 **차단**(동작이 바뀌면 안 되는 자리)
_ROW_ALL_SPENT = (_TIER, 10_000.0, 10_000.0, 10_000.0, 0.0)

#: ★`get_status` 가 **판정 경로까지 갔을 때만** 나오는 키들.
#:   조기 반환은 `{tier, metered, blocked}` 3개뿐이라 이 가드에 걸린다.
_FULL_KEYS = frozenset({"topup_remaining", "monthly_base_remaining", "remaining_krw", "usage_pct"})


class _EmptyResult:
    def first(self):
        return None

    def scalar(self):
        return None

    def mappings(self):
        return self

    def all(self):
        return []


class _NullSession:
    """판정에 쓰이는 값은 **전부 스텁으로 주입**하고, 그 외 조회는 빈 결과를 준다.

    ★`get_status` 는 판정과 무관한 조회(설정 로드 등)도 한다. 그걸 예외로 막으면
      **락이 배선이 아니라 무관한 부수효과를 검사**하게 된다(첫 판이 그랬다).
      이 락이 보는 것은 **`_rem` 이 실제로 소비되는가** 하나다.
    """

    async def execute(self, *a, **k):
        return _EmptyResult()

    async def commit(self):
        pass

    async def rollback(self):
        pass


@pytest.fixture
def _stub_cycle(monkeypatch: pytest.MonkeyPatch):
    """`ensure_cycle`/`team_limit_exceeded` 만 갈아 끼우고 **`is_blocked` 본문은 실제로 태운다**."""

    def _apply(row):
        async def fake_cycle(db, uid):
            return row

        async def fake_team(db, uid):
            return False

        monkeypatch.setattr(_bs, "ensure_cycle", fake_cycle)
        monkeypatch.setattr(_bs, "team_limit_exceeded", fake_team)

    return _apply


@pytest.mark.asyncio
async def test_is_blocked_is_wired_to_compute_remaining(_stub_cycle) -> None:
    """★배선 — `is_blocked` 가 **새 판정**을 실제로 쓰는가.

    되살리는 변이: 본문을 `return billed >= row[2]` 로 되돌리면 A 가 True 가 되어 실패한다.
    (그 변이는 이 락이 없을 때 **SURVIVED** 했다 — 실측)
    """
    _stub_cycle(_ROW_TOPUP_LEFT)
    assert await _bs.is_blocked(_NullSession(), "u1") is False, (
        "★충전이 25,000원 남았는데 차단됐다 — 옛 이중차감 게이트가 살아 있다"
    )


@pytest.mark.asyncio
async def test_is_blocked_still_blocks_when_everything_spent(_stub_cycle) -> None:
    """★대조군 — 진짜 소진이면 여전히 차단한다(무제한 구현이 통과하지 않게)."""
    _stub_cycle(_ROW_ALL_SPENT)
    assert await _bs.is_blocked(_NullSession(), "u1") is True


@pytest.mark.asyncio
async def test_status_blocked_flag_is_wired(monkeypatch: pytest.MonkeyPatch) -> None:
    """★형제 배선 — 화면이 읽는 `blocked`·`topup_remaining` 도 같은 판정을 쓰는가.

    ★게이트만 고치고 표시를 안 고치면 **API 는 허용하는데 화면은 잠긴 것처럼 보인다.**
    """

    # ★`get_status` 는 `ensure_cycle` 의 **반환을 안 쓴다** — `_row` 를 따로 부른다.
    #   첫 판이 `ensure_cycle` 만 갈아 끼웠다가 `_row` 가 None 을 돌려주는 **조기 반환**
    #   경로로 빠졌고, `blocked is False` 가 **공허하게 참**이 됐다(키 3개만 반환).
    #   ★그래서 아래 `_FULL_KEYS` 가드가 있다 — 그 경로를 밟으면 실패한다.
    #   `_row` 반환: (tier, billed, budget, cycle_start, monthly_base, topup)
    async def fake_row(db, uid):
        return (_TIER, 35_000.0, 35_000.0, None, 10_000.0, 25_000.0)

    async def fake_cycle(db, uid):
        return _ROW_TOPUP_LEFT

    async def fake_team(db, uid):
        return False

    async def fake_meta(db, uid):
        return (_TIER, 0, 0.0)

    async def fake_rate():
        return 1350.0

    async def fake_load(db):
        return None

    monkeypatch.setattr(_bs, "_row", fake_row)
    monkeypatch.setattr(_bs, "ensure_cycle", fake_cycle)
    monkeypatch.setattr(_bs, "team_limit_exceeded", fake_team)
    monkeypatch.setattr(_bs, "_meta", fake_meta)
    monkeypatch.setattr(_bs, "get_usd_krw_rate", fake_rate)
    monkeypatch.setattr(_bs, "load_config", fake_load)

    st = await _bs.get_status(_NullSession(), "u1")
    # ★공허한 초록 가드 — 조기 반환 경로({tier,metered,blocked} 3키)를 밟으면 실패한다.
    missing = _FULL_KEYS - set(st)
    assert not missing, f"★판정 경로에 도달하지 못했다(조기 반환) — 없는 키: {sorted(missing)}"
    assert st["blocked"] is False, "★표시가 옛 식을 쓴다 — API 와 화면이 갈린다"
    assert st["topup_remaining"] == 25_000, (
        f"★충전 잔여가 {st['topup_remaining']} — 컬럼 순액에서 또 뺐다(절반 표시 결함)"
    )
    # ★두 모집단: 남은 것과 쓴 것이 **다른 값**이어야 한다(둘 다 0 이면 락이 공허하다).
    assert st["monthly_base_remaining"] == 0
    assert st["topup_remaining"] != st["monthly_base_remaining"]


# ═══════════════════════════════════════════════════════════════════════════
# L2 / L3 / L4 — ★승인 오케스트레이션을 **직접 태운다**
#
# 위 락들은 순수 함수·소스 구조를 본다. 여기서는 `confirm_toss_payment` 를 실제로
# 실행해 **금액 검증 · 소유자 검증 · 미확정 처리**가 배선돼 있는지 잰다.
#
# ★계획서 §5 가 이 셋을 선언했는데 첫 판에는 **없었다**(파일명도 실재하지 않았다).
#   선언과 산출물이 갈리면 리뷰어가 이미 안전하다고 오독한다 — 그래서 채운다.
# ═══════════════════════════════════════════════════════════════════════════
import app.services.billing.payment_receipts as _pr  # noqa: E402
import app.services.billing.toss_orders_service as _tos  # noqa: E402
from app.services.billing.toss_payments import TossOutcomeUnknownError  # noqa: E402


class _Mapped:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _Res:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return _Mapped(self._row)

    def first(self):
        return None

    def scalar(self):
        return None


class _OrderSession:
    """`coin_orders` 조회에만 응답하는 최소 세션 — 나머지는 통과시킨다."""

    def __init__(self, order_row):
        self.order_row = order_row
        self.sql: list[str] = []

    async def execute(self, stmt, params=None):
        s = str(getattr(stmt, "text", stmt))
        self.sql.append(s)
        if "FROM coin_orders WHERE id" in s:
            return _Res(self.order_row)
        return _Res()

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _order(**over):
    base = {
        "id": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
        "user_id": "user-A",
        "tenant_id": None,
        # ★두 모집단을 **가른다**: amount(결제액) ≠ coin(지급액).
        #   둘이 같은 픽스처면 "어느 컬럼을 비교하는가"를 잠글 수 없다 —
        #   실제로 현재 코드는 둘을 항상 같게 넣으므로 손으로 갈라 줘야 한다.
        "amount_krw": 10_000.0,
        "coin_krw": 12_000.0,
        "status": "pending",
        "provider": None,
        "provider_ref": None,
        "order_no": "CO20260827-DEADBEEF",
    }
    base.update(over)
    return base


@pytest.fixture
def _capture(monkeypatch: pytest.MonkeyPatch):
    """토스 호출을 가로채 **무엇을 보냈는지** 잡고, 영수증은 메모리에 모은다."""
    sent: dict[str, object] = {}
    receipts: list[dict] = []

    async def fake_confirm(*, payment_key, order_id, amount, idempotency_key):
        sent.update(
            payment_key=payment_key, order_id=order_id, amount=amount, idem=idempotency_key
        )
        return {"status": "DONE", "totalAmount": amount, "paymentKey": payment_key}

    async def fake_record(**kw):
        receipts.append(kw)
        return "rcpt-1"

    async def fake_confirm_order(db, **kw):
        return {"id": kw["order_id"], "order_no": "CO20260827-DEADBEEF",
                "status": "paid", "coin_krw": 12_000.0}

    monkeypatch.setattr(_tos.toss_payments, "is_configured", lambda: True)
    monkeypatch.setattr(_tos.toss_payments, "confirm", fake_confirm)
    monkeypatch.setattr(_pr, "record", fake_record)
    monkeypatch.setattr(_tos.payment_receipts, "record", fake_record)
    monkeypatch.setattr(_tos.coin_orders_service, "ensure_schema", lambda db: _noop())
    monkeypatch.setattr(_tos.coin_orders_service, "confirm_order", fake_confirm_order)
    return sent, receipts


async def _noop():
    return None


@pytest.mark.asyncio
async def test_confirm_sends_server_amount_not_client_amount(_capture) -> None:
    """★L2 — 토스로 가는 금액은 **서버 저장값**이다(클라이언트 주장이 아니다).

    픽스처가 `amount_krw=10,000` · `coin_krw=12,000` 으로 **갈려 있다** —
    비교 대상을 `coin_krw` 로 바꾸는 변이가 이 단언을 죽인다.
    """
    sent, _ = _capture
    db = _OrderSession(_order())
    r = await _tos.confirm_toss_payment(
        db, order_id=_order()["id"], payment_key="pk_x",
        claimed_amount=10_000, current_user_id="user-A",
    )
    assert r["status"] == "paid"
    assert sent["amount"] == 10_000, f"★토스로 보낸 금액이 {sent['amount']} — 서버 저장값이 아니다"
    assert sent["order_id"] == _order()["id"], "★orderId 가 uuid 가 아니다"


@pytest.mark.asyncio
async def test_confirm_rejects_amount_mismatch_before_calling_vendor(_capture) -> None:
    """★L2 대조군 — 금액이 어긋나면 **벤더를 부르기 전에** 막는다(돈이 안 움직인다)."""
    sent, receipts = _capture
    db = _OrderSession(_order())
    with pytest.raises(_tos.PaymentRejectedError) as e:
        await _tos.confirm_toss_payment(
            db, order_id=_order()["id"], payment_key="pk_x",
            claimed_amount=1, current_user_id="user-A",   # ★조작된 금액
        )
    assert e.value.code == _tos.CODE_AMOUNT_MISMATCH
    assert e.value.remediation.strip(), "★조치가 비었다"
    assert not sent, "★금액이 어긋났는데 벤더를 불렀다(돈이 움직일 수 있다)"
    assert any(r["event"] == _pr.EVENT_BLOCKED for r in receipts), "★차단 기록이 없다"


@pytest.mark.asyncio
async def test_confirm_blocks_other_users_order(_capture) -> None:
    """★L3(IDOR) — 남의 주문은 승인할 수 없다. **소유자가 갈리면 결과도 갈린다.**"""
    sent, _ = _capture
    db = _OrderSession(_order())
    with pytest.raises(_tos.PaymentRejectedError) as e:
        await _tos.confirm_toss_payment(
            db, order_id=_order()["id"], payment_key="pk_x",
            claimed_amount=10_000, current_user_id="user-B",   # ★남의 계정
        )
    # ★존재 여부를 흘리지 않는다 — 404 로 정규화(주문 열거 방지).
    assert e.value.http_status == 404
    assert not sent, "★남의 주문인데 벤더를 불렀다"


@pytest.mark.asyncio
async def test_unknown_outcome_is_not_a_failure(_capture, monkeypatch) -> None:
    """★L4 — 타임아웃은 **실패가 아니다.** 재조회도 실패하면 `PaymentUnresolvedError`.

    되살리는 변이: `except TossOutcomeUnknownError` 를 `PaymentRejectedError` 로 접으면
    사용자가 "실패"를 보고 **다시 결제한다**(이중 결제).
    """
    sent, receipts = _capture

    async def timeout(**kw):
        raise TossOutcomeUnknownError("타임아웃", payment_key=kw.get("payment_key"))

    async def no_resolve(*a, **k):
        raise TossOutcomeUnknownError("재조회도 실패")

    monkeypatch.setattr(_tos.toss_payments, "confirm", timeout)
    monkeypatch.setattr(_tos.toss_payments, "get_payment", no_resolve)
    monkeypatch.setattr(_tos.toss_payments, "get_payment_by_order_id", no_resolve)

    db = _OrderSession(_order())
    with pytest.raises(_tos.PaymentUnresolvedError) as e:
        await _tos.confirm_toss_payment(
            db, order_id=_order()["id"], payment_key="pk_x",
            claimed_amount=10_000, current_user_id="user-A",
        )
    # ★"실패"라고 말하지 않는다 — 중복 결제를 유도하면 안 된다.
    assert "중복 결제하지 마시고" in str(e.value)
    assert any(r["event"] == _pr.EVENT_UNKNOWN for r in receipts), "★미확정 기록이 없다"
    # ★두 모집단: 거절(위 테스트)은 PaymentRejectedError, 미확정은 PaymentUnresolvedError.
    assert not isinstance(e.value, _tos.PaymentRejectedError)


@pytest.mark.asyncio
async def test_same_payment_key_twice_is_idempotent_success(_capture) -> None:
    """★L9 — 같은 결제로 다시 오면 **성공**(새로고침이 오류로 보이면 안 된다)."""
    sent, _ = _capture
    paid = _order(status="paid", provider="toss", provider_ref="pk_x")
    r = await _tos.confirm_toss_payment(
        _OrderSession(paid), order_id=paid["id"], payment_key="pk_x",
        claimed_amount=10_000, current_user_id="user-A",
    )
    assert r["already_applied"] is True
    assert not sent, "★이미 지급된 주문인데 벤더를 다시 불렀다(재과금 경로)"


@pytest.mark.asyncio
async def test_different_payment_key_on_paid_order_is_conflict(_capture) -> None:
    """★L9 대조군 — **다른** 결제키가 붙은 주문은 409(이중 결제 의심)."""
    sent, _ = _capture
    paid = _order(status="paid", provider="toss", provider_ref="pk_OTHER")
    with pytest.raises(_tos.PaymentRejectedError) as e:
        await _tos.confirm_toss_payment(
            _OrderSession(paid), order_id=paid["id"], payment_key="pk_x",
            claimed_amount=10_000, current_user_id="user-A",
        )
    assert e.value.http_status == 409
    assert e.value.code == _tos.CODE_PAYMENT_KEY_CONFLICT
    assert not sent


# ═══════════════════════════════════════════════════════════════════════════
# ★환불 정책: **미사용분만** (소유자 확정 2026-08-27)
#
# 법적 근거: 충전과 소비는 별개 거래이고, 전자상거래법 §17②5(*"디지털콘텐츠의 제공이
# 개시된 경우"*)는 **소비한 부분에만** 걸린다 → 미사용 잔액은 청약철회 대상이다.
#
# ★종전 구현은 「잔액이 모자라면 **전부 거절**」이었다 — **다른 규칙**이다.
#   그래서 이 절의 핵심은 **세 모집단이 서로 다른 결과를 내는지**다:
#     ① 전혀 안 씀   → 전액 환불
#     ② 일부 씀      → **미사용분만** 부분 환불 + 못 돌려주는 이유를 응답에 싣는다
#     ③ 전부 씀      → 거절(사유 포함)
#   ①만 잠그면 "언제나 전액 환불" 구현이 통과하고, ③만 잠그면 옛 구현이 통과한다.
# ═══════════════════════════════════════════════════════════════════════════
class _RefundSession:
    """환불 경로가 실제로 만지는 SQL 에만 응답한다."""

    def __init__(self, order_row, topup_balance: float):
        self.order_row = order_row
        self.topup = topup_balance
        self.clawed: list[float] = []

    async def execute(self, stmt, params=None):
        s = str(getattr(stmt, "text", stmt))
        p = params or {}
        if "FROM coin_orders WHERE order_no" in s:
            return _Res(self.order_row)
        if "COALESCE(topup_krw, 0) FROM public.users" in s:
            return _ScalarRes(self.topup)
        if "UPDATE public.users" in s and "topup_krw" in s and "RETURNING" in s:
            # ★조건부 UPDATE 를 재현한다 — 잔액이 모자라면 **성립하지 않는다**.
            amt = float(p.get("a", 0))
            if self.topup >= amt:
                self.topup -= amt
                self.clawed.append(amt)
                return _RowRes(("u",))
            return _RowRes(None)
        return _Res()

    async def commit(self):
        pass

    async def rollback(self):
        pass


class _ScalarRes:
    def __init__(self, v):
        self._v = v

    def scalar(self):
        return self._v

    def mappings(self):
        return _Mapped(None)

    def first(self):
        return None


class _RowRes:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row

    def mappings(self):
        return _Mapped(None)

    def scalar(self):
        return None


def _paid_order(**over):
    o = _order(status="paid", provider="toss", provider_ref="pk_x")
    o["refunded_krw"] = 0.0
    o.update(over)
    return o


@pytest.fixture
def _refund_env(monkeypatch: pytest.MonkeyPatch):
    """벤더 취소를 가로채고, 영수증·원장은 메모리로."""
    sent: dict = {}

    async def fake_cancel(**kw):
        sent.update(kw)
        return {"status": "CANCELED"}

    async def fake_record(**kw):
        return "r"

    async def fake_append(**kw):
        return {"persisted": True}

    async def fake_fetch(**kw):
        # 부분 취소 가능(대부분의 카드 결제)
        return {"status": "DONE", "isPartialCancelable": True}

    monkeypatch.setattr(_tos.toss_payments, "is_configured", lambda: True)
    monkeypatch.setattr(_tos.toss_payments, "cancel", fake_cancel)
    monkeypatch.setattr(_tos.payment_receipts, "record", fake_record)
    monkeypatch.setattr(_tos.coin_ledger_service, "append_event", fake_append)
    monkeypatch.setattr(_tos.coin_orders_service, "ensure_schema", lambda db: _noop())
    monkeypatch.setattr(_tos, "_fetch_payment", fake_fetch)
    return sent


@pytest.mark.asyncio
async def test_refund_full_when_nothing_consumed(_refund_env) -> None:
    """① 전혀 안 썼으면 **전액** 환불되고, 벤더에는 전액취소(`cancelAmount` 생략)로 간다."""
    sent = _refund_env
    db = _RefundSession(_paid_order(), topup_balance=10_000)
    r = await _tos.refund_toss_payment(
        db, order_no="CO20260827-DEADBEEF", reason="단순변심",
        amount=None, actor_id="user-A", is_admin=False,
    )
    assert r["refunded_krw"] == 10_000
    assert r["partial"] is False
    assert r["unrefundable_consumed_krw"] == 0
    assert sent["cancel_amount"] is None, "★전액인데 부분취소로 보냈다"


@pytest.mark.asyncio
async def test_refund_only_unused_when_partially_consumed(_refund_env) -> None:
    """★② 일부 썼으면 **미사용분만** 환불하고, 못 돌려주는 금액을 응답에 **싣는다**.

    되살리는 변이: `refundable = min(order_remaining, balance)` 를 `order_remaining` 으로
    되돌리면 **이미 쓴 코인까지 환불**해 잔액이 음수가 되거나 조건부 UPDATE 가 실패한다.
    """
    sent = _refund_env
    # 10,000 결제 · 7,000 소진 → 미사용 3,000
    db = _RefundSession(_paid_order(), topup_balance=3_000)
    r = await _tos.refund_toss_payment(
        db, order_no="CO20260827-DEADBEEF", reason="단순변심",
        amount=None, actor_id="user-A", is_admin=False,
    )
    assert r["refunded_krw"] == 3_000, "★미사용분(3,000)만 환불해야 한다"
    assert r["partial"] is True
    # ★못 돌려주는 이유를 응답이 말한다 — 조용히 적게 주면 사용자가 모른다.
    assert r["unrefundable_consumed_krw"] == 7_000
    assert r["order_remaining_before_krw"] == 10_000
    assert sent["cancel_amount"] == 3_000, "★벤더에 부분취소 금액이 안 갔다"
    assert db.topup == 0, "★환수 후 충전잔액이 0 이어야 한다"


@pytest.mark.asyncio
async def test_refund_rejected_when_fully_consumed(_refund_env) -> None:
    """★③ 전부 썼으면 **거절** — 그리고 사유가 있다(없는 것을 돌려줄 수는 없다)."""
    sent = _refund_env
    db = _RefundSession(_paid_order(), topup_balance=0)
    with pytest.raises(_tos.PaymentRejectedError) as e:
        await _tos.refund_toss_payment(
            db, order_no="CO20260827-DEADBEEF", reason="단순변심",
            amount=None, actor_id="user-A", is_admin=False,
        )
    assert e.value.code == _tos.CODE_INSUFFICIENT_BALANCE
    assert "미사용분만" in e.value.message
    assert e.value.remediation.strip()
    assert not sent, "★환불 불가인데 벤더를 불렀다"


@pytest.mark.asyncio
async def test_explicit_amount_over_unused_is_rejected_not_silently_reduced(_refund_env) -> None:
    """★명시 금액이 미사용분을 넘으면 **조용히 줄이지 않는다** — 그러면 사용자가 모른다."""
    sent = _refund_env
    db = _RefundSession(_paid_order(), topup_balance=3_000)
    with pytest.raises(_tos.PaymentRejectedError) as e:
        await _tos.refund_toss_payment(
            db, order_no="CO20260827-DEADBEEF", reason="x",
            amount=10_000, actor_id="user-A", is_admin=False,
        )
    assert e.value.code == _tos.CODE_INSUFFICIENT_BALANCE
    assert "3,000" in e.value.message, f"★환불 가능액을 안 알려 준다: {e.value.message}"
    assert not sent


@pytest.mark.asyncio
async def test_partial_refund_blocked_when_vendor_forbids(_refund_env, monkeypatch) -> None:
    """★부분 취소가 **벤더에서 불가**하면 코인을 건드리기 **전에** 막는다.

    (그러지 않으면 환수해 놓고 벤더가 거절해 되돌리는 왕복이 생긴다)
    """
    sent = _refund_env

    async def no_partial(**kw):
        return {"status": "DONE", "isPartialCancelable": False}

    monkeypatch.setattr(_tos, "_fetch_payment", no_partial)
    db = _RefundSession(_paid_order(), topup_balance=3_000)
    with pytest.raises(_tos.PaymentRejectedError) as e:
        await _tos.refund_toss_payment(
            db, order_no="CO20260827-DEADBEEF", reason="x",
            amount=None, actor_id="user-A", is_admin=False,
        )
    assert e.value.code == "NOT_ALLOWED_PARTIAL_REFUND"
    assert not db.clawed, "★벤더가 못 한다는데 코인을 먼저 뺏었다"
    assert not sent


@pytest.mark.asyncio
async def test_refund_blocks_other_users_order(_refund_env) -> None:
    """★IDOR — 남의 주문은 환불할 수 없다(관리자는 예외)."""
    sent = _refund_env
    db = _RefundSession(_paid_order(), topup_balance=10_000)
    with pytest.raises(_tos.PaymentRejectedError) as e:
        await _tos.refund_toss_payment(
            db, order_no="CO20260827-DEADBEEF", reason="x",
            amount=None, actor_id="user-B", is_admin=False,
        )
    assert e.value.http_status == 404
    assert not sent
