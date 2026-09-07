"""무통장입금 충전의 **잠금** — 계획서 `PLAN_bank_transfer_topup_2026-09-06.md` §5.

## 이 파일이 지키는 것

무통장입금은 **거절해 줄 상대가 없다.** 토스는 우리가 틀리면 `INVALID_API_KEY` 로 막아 주지만,
계좌를 한 자리 틀리게 안내하면 사용자는 **남의 계좌로 송금**하고 그것은 되돌릴 수 없다.
그래서 잠금의 절반이 *"불완전하면 **안내하지 않는다**"* 에 걸려 있다.

★그리고 이 변경은 `#1005` 가 세운 **무료충전 방어를 되살리지 못하게** 해야 한다 —
  결제수단을 목록으로 바꾸는 순간 `simulated` 가 후보로 새어 들어올 자리가 생긴다.
  같은 PR 안에서 자기가 고친 결함을 재발시키는 형태를 B3·B4 가 막는다.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from app.services.billing import bank_transfer, coin_orders_service

_API = pathlib.Path(__file__).resolve().parents[1]


class _FakeSettings:
    def __init__(self, simulated: bool):
        self.billing_simulated_payments = simulated


def _set(monkeypatch, *, sk="", ck="", bank="", acct="", holder=""):
    for name, val in (
        ("TOSS_SECRET_KEY", sk), ("TOSS_CLIENT_KEY", ck),
        (bank_transfer.ENV_BANK_NAME, bank),
        (bank_transfer.ENV_ACCOUNT_NO, acct),
        (bank_transfer.ENV_HOLDER, holder),
    ):
        if val:
            monkeypatch.setenv(name, val)
        else:
            monkeypatch.delenv(name, raising=False)


_GOOD_TOSS = {"sk": "test_gsk_x1234567", "ck": "test_gck_y1234567"}
_BAD_TOSS = {"sk": "test_sk_x1234567", "ck": "test_ck_y1234567"}  # 계열 불일치(#1005)
_GOOD_BANK = {"bank": "새마을금고", "acct": "9002148908909", "holder": "예금주"}


# ═══════════════════════════════════════════════════════════════════════════
# B1·B2 — ★`payment_mode` 는 목록에서 **파생**된다(두 출처 금지 · 하위호환)
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    ("kw", "simulated", "methods", "mode"),
    [
        # ── 종전 상태 4종 — `payment_mode` 값이 **바뀌면 안 된다**(회귀 방어) ──
        ({**_GOOD_TOSS}, False, ["toss"], "toss"),
        ({}, True, ["simulated"], "simulated"),
        ({}, False, [], "manual_only"),
        # ★#1005: 키가 있는데 짝이 틀리면 `manual_only` — **`simulated` 아님**
        ({**_BAD_TOSS}, True, [], "manual_only"),
        # ── 신규 상태 ──
        ({**_GOOD_BANK}, False, ["bank_transfer"], "bank_transfer"),
        ({**_GOOD_TOSS, **_GOOD_BANK}, False, ["toss", "bank_transfer"], "toss"),
        ({**_BAD_TOSS, **_GOOD_BANK}, True, ["bank_transfer"], "bank_transfer"),
    ],
)
def test_mode_is_derived_from_methods_and_legacy_values_are_unchanged(
    monkeypatch: pytest.MonkeyPatch, kw, simulated, methods, mode
) -> None:
    """★목록이 유일한 계산처이고, 종전 4상태의 `payment_mode` 는 **불변**이다.

    두 곳에서 따로 계산하면 반드시 갈리고, 갈린 쪽이 화면이면 사용자가 **못 쓰는
    버튼**을 누른다.
    """
    import routers.billing as _b

    _set(monkeypatch, **kw)
    st = _FakeSettings(simulated)
    assert _b.resolve_payment_methods(st) == methods
    assert _b.resolve_payment_mode(st) == mode
    # ★파생 일치 — 이 단언이 두 함수가 갈라지는 것을 원천 차단한다.
    m = _b.resolve_payment_methods(st)
    assert _b.resolve_payment_mode(st) == (m[0] if m else "manual_only")


# ═══════════════════════════════════════════════════════════════════════════
# B3·B4 — ★무료충전 경로가 목록화로 되살아나지 않는다
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "kw",
    [
        {**_BAD_TOSS},                       # 키가 있는데 못 씀
        {**_BAD_TOSS, **_GOOD_BANK},         # 그 위에 계좌까지
        {**_GOOD_TOSS},                      # 정상 토스
        {**_GOOD_BANK},                      # 계좌만
        {**_GOOD_TOSS, **_GOOD_BANK},        # 둘 다
    ],
)
def test_simulated_never_appears_when_a_real_method_exists_or_was_intended(
    monkeypatch: pytest.MonkeyPatch, kw
) -> None:
    """`simulated` 는 `POST /orders/{id}/confirm` 한 번으로 **결제 없이 코인을 만든다.**

    두 겹으로 닫는다: 실수단이 있으면 제외 · **토스 키가 존재하면**(짝이 틀려도) 제외.
    ★후자가 핵심이다 — 설정 오류가 **무료 충전으로 강등**되어서는 안 된다.
    """
    import routers.billing as _b

    _set(monkeypatch, **kw)
    assert "simulated" not in _b.resolve_payment_methods(_FakeSettings(True))


def test_simulated_still_works_when_nothing_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★반대 방향 — 아무것도 없으면 데모는 **여전히 동작해야** 한다.

    이쪽을 함께 걸지 않으면 "항상 제외"가 만점을 받고 개발 환경이 죽는다.
    """
    import routers.billing as _b

    _set(monkeypatch)
    assert _b.resolve_payment_methods(_FakeSettings(True)) == ["simulated"]


# ═══════════════════════════════════════════════════════════════════════════
# B5·B6 — ★불완전하면 **안내하지 않는다**(부분 정보 = 엉뚱한 곳으로 송금)
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    ("kw", "ok", "why"),
    [
        (_GOOD_BANK, True, "세 항목 모두 정상"),
        ({**_GOOD_BANK, "bank": ""}, False, "은행명 없음"),
        ({**_GOOD_BANK, "acct": ""}, False, "계좌번호 없음"),
        ({**_GOOD_BANK, "holder": ""}, False, "예금주 없음"),
        ({**_GOOD_BANK, "acct": "900-214-890890"}, True, "하이픈 표기도 정상"),
        ({**_GOOD_BANK, "acct": "9002 148908909"}, False, "공백은 불가"),
        ({**_GOOD_BANK, "acct": "abc12345678"}, False, "문자는 불가"),
        # ★전각 숫자 — 파이썬 `\\d` 는 유니코드 십진수를 포함해서 그냥 두면 통과한다.
        #   전각으로 안내하면 은행 앱이 거부하거나 **다른 계좌**가 된다.
        ({**_GOOD_BANK, "acct": "９００２１４８９０８９０９"}, False, "전각 숫자는 불가"),
        ({**_GOOD_BANK, "acct": "123"}, False, "너무 짧음"),
        ({**_GOOD_BANK, "holder": "강" * 41}, False, "예금주 길이 초과"),
    ],
)
def test_account_is_shown_only_when_completely_valid(
    monkeypatch: pytest.MonkeyPatch, kw, ok, why
) -> None:
    _set(monkeypatch, **kw)
    assert bank_transfer.is_configured() is ok, why
    # ★두 모집단이 **같은 실행에서** 갈린다: 못 쓰면 값이 **아예 없다**(부분 안내 금지).
    assert (bank_transfer.account_info() is not None) is ok, why


def test_diagnosis_names_the_missing_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """★`false` 만으로는 관리자가 못 고친다 — **무엇이** 비었는지 말해야 한다."""
    _set(monkeypatch, **{**_GOOD_BANK, "acct": ""})
    d = bank_transfer.diagnosis()
    assert d["ok"] is False
    assert d["code"] == "incomplete"
    assert d["severity"] == "error", "부분 설정은 상태가 아니라 **장애**다"
    assert any("계좌번호" in p for p in d["problems"])
    assert d["action"]

    # 아무것도 없으면 **장애가 아니라 상태**다(미설정 ≠ 오설정).
    _set(monkeypatch)
    d0 = bank_transfer.diagnosis()
    assert d0["code"] == "not_configured" and d0["severity"] == "info"


def test_account_info_carries_only_the_three_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """★금고의 **다른 항목**이 이 응답으로 새지 않는다."""
    _set(monkeypatch, **_GOOD_BANK)
    monkeypatch.setenv("TOSS_SECRET_KEY", "test_gsk_SUPERSECRET")
    info = bank_transfer.account_info()
    assert info is not None
    assert set(info) == {"bank_name", "account_no", "holder"}
    assert "SUPERSECRET" not in str(info)


# ═══════════════════════════════════════════════════════════════════════════
# B7·B8 — 입금자명: **두 모집단**(주면 그 값 · 안 주면 가입자명) + 위생
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("홍길동", "홍길동"),
        ("  홍길동  ", "홍길동"),
        # 공백 정규화 — 눈에 같아 보이는데 안 맞는 값이 생기지 않게.
        ("홍  길동\t", "홍 길동"),
        ("(주)사통팔땅", "(주)사통팔땅"),
        ("가" * 30, "가" * 20),  # 상한 절단
    ],
)
def test_depositor_name_sanitization(raw, expected) -> None:
    assert coin_orders_service.sanitize_depositor_name(raw) == expected


def test_depositor_name_strips_control_characters() -> None:
    """제어문자가 섞이면 통장 내역과 **눈으로는 같아 보이는데** 안 맞는다."""
    assert coin_orders_service.sanitize_depositor_name("홍\x00길\x07동") == "홍길동"


def test_create_order_falls_back_to_member_name_when_depositor_is_empty() -> None:
    """★**두 모집단** — 비우면 종전대로 가입자명(회귀 0), 주면 그 값.

    소스에서 그 분기를 확인한다(런타임 경로는 DB 를 태워야 하므로 계약을 잠근다).
    """
    src = (_API / "app/services/billing/coin_orders_service.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    # 실행되는 줄에서 `sanitize_depositor_name(...) or (가입자명)` 형태를 확인한다.
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            seg = ast.get_source_segment(src, node) or ""
            if "sanitize_depositor_name" in seg and "buyer" in seg:
                found = True
    assert found, "★입금자명이 비었을 때 가입자명으로 되돌아가는 분기가 없다"


# ═══════════════════════════════════════════════════════════════════════════
# B9 — 관리자 목록이 **실제로** 대사 키를 조회한다(스텁이 우회하지 못하게)
# ═══════════════════════════════════════════════════════════════════════════
def test_admin_queries_actually_select_the_reconciliation_key() -> None:
    """★`buyer_name` 을 SELECT 하지 않으면 화면이 그 값을 **볼 수 없다**.

    관리자에게 「승인」 버튼만 있고 무엇을 승인하는지 모르는 상태가 된다.
    """
    src = (_API / "app/services/billing/revenue_service.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    # ★주석·독스트링을 배제하고 **실행되는 문자열 리터럴**만 본다.
    sql = " ".join(
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and "SELECT" in n.value
    )
    assert "buyer_name" in sql, "대사 키가 관리자 쿼리에 없다"
    # ★대조군 — 리터럴 수집이 죽지 않았다.
    assert "coin_orders" in sql, "SQL 리터럴 수집이 죽었다 — 위 판정을 신뢰하지 마라"


def test_awaiting_deposit_is_a_separate_queue_not_a_filtered_view() -> None:
    """★입금 대기를 혼재 목록에서 파생시키면 **유료 주문에 밀려 사라진다**.

    그리고 그 절단은 조용하다 — `total`/`truncated` 로 **잘렸음을 말해야** 한다.
    """
    src = (_API / "app/services/billing/revenue_service.py").read_text(encoding="utf-8")
    assert "async def awaiting_deposit(" in src
    tree = ast.parse(src)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "awaiting_deposit"
    )
    body = ast.get_source_segment(src, fn) or ""
    assert "status='pending'" in body, "대기 큐가 상태로 좁히지 않는다"
    assert '"truncated"' in body and '"total"' in body, "절단을 드러내지 않는다"


# ═══════════════════════════════════════════════════════════════════════════
# B10·B11 — 승인의 **원자성**(이 PR 이 의존하는 기존 불변식의 회귀 락)
# ═══════════════════════════════════════════════════════════════════════════
def test_confirm_sql_still_guards_on_pending_status() -> None:
    """★두 관리자가 동시에 「입금 확인」을 눌러도 **한 번만** 성립해야 한다.

    이 PR 이 새로 만든 것이 아니라 **의존하는** 불변식이다. 무통장입금은 사람이 누르는
    경로라 중복 클릭이 실제로 일어나므로, 여기서 회귀 락을 건다.
    """
    src = (_API / "app/services/billing/coin_orders_service.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    sql = " ".join(
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    )
    assert "UPDATE coin_orders SET status='paid'" in sql
    assert "status='pending'" in sql, "★상태 가드가 사라지면 중복 지급이 가능해진다"
    assert "RETURNING" in sql, "성립 여부를 알 수 없으면 두 번째 호출을 막을 수 없다"


def test_catalog_declares_all_three_bank_fields() -> None:
    """★금고 카탈로그에 없으면 관리자 화면에 **입력칸이 안 뜬다**(등록 불가)."""
    from app.services.secrets.secret_store import CATALOG

    names = {c["name"] for c in CATALOG}
    for n in bank_transfer.REQUIRED_FIELDS:
        assert n in names, f"{n} 이 카탈로그에 없다 — 관리자가 등록할 방법이 없다"
    bank_entries = [c for c in CATALOG if c["name"] in bank_transfer.REQUIRED_FIELDS]
    # ★계좌 안내는 **사용자에게 보여 줘야** 하므로 비밀이 아니다(마스킹되면 못 쓴다).
    assert all(c["secret"] is False for c in bank_entries)
    assert len({c["group"] for c in bank_entries}) == 1, "세 항목이 한 그룹에 모여야 한다"


# ═══════════════════════════════════════════════════════════════════════════
# ★사용자에게 **그대로 찍히는** 문자열에 마크다운을 쓰지 않는다 (2026-09-06 라이브 실측)
#
# 배포 후 실제 화면을 태워 보니 이렇게 나왔다:
#
#     입금자명은 주문에 적은 이름과 **같아야** 확인이 빠릅니다.
#                                  ↑ 별표가 그대로 찍힌다
#
# 이 문구들은 **평문 `<p>` 로 렌더**된다(관리자 `warnings` 도 문자열 배열이다).
# 개발자용 독스트링·주석에서 쓰던 `**강조**` 습관이 **응답 문자열로 새어 나온 것**이다.
# 이 저장소의 평문 강조 관용구는 `「」` 다(`관리자 > API 키 > 「결제(PG)」`).
#
# ★독스트링은 대상이 아니다 — 개발자가 읽는 것이고 렌더되지 않는다.
#   범위를 넓히면 정당한 사용이 위양성이 된다(처방 범위 = 결함 범위).
# ═══════════════════════════════════════════════════════════════════════════
_MD_EMPHASIS = "**"


def _md_hits(text: str) -> bool:
    return _MD_EMPHASIS in (text or "")


def test_toss_diagnosis_copy_is_plain_text() -> None:
    """★파생형 — 표 전체를 훑는다. 새 코드가 추가돼도 자동으로 감시망에 들어온다."""
    from app.services.billing.toss_payments import KEY_DIAGNOSIS_COPY

    assert len(KEY_DIAGNOSIS_COPY) >= 8, "모집단이 비었다 — 공허한 초록 방지"
    bad = [
        (code, part)
        for code, (_sev, msg, act) in KEY_DIAGNOSIS_COPY.items()
        for part in (msg, act)
        if _md_hits(part)
    ]
    assert not bad, f"관리자 화면에 별표가 그대로 찍힌다: {bad}"
    # ★대조군 — 이 검사기가 별표를 실제로 잡는가(빈 표라서 통과한 것이 아니다).
    assert _md_hits("이것은 **강조** 다"), "검사기가 죽었다 — 위 「0건」을 신뢰하지 마라"


@pytest.mark.parametrize(
    "kw",
    [
        {},                                   # 미설정
        {**_GOOD_BANK, "acct": ""},           # 부분 설정
        {**_GOOD_BANK, "acct": "abc12345678"},  # 형식 불량
        _GOOD_BANK,                           # 정상
    ],
)
def test_bank_diagnosis_is_plain_text_in_every_state(
    monkeypatch: pytest.MonkeyPatch, kw
) -> None:
    """★**모든 상태**에서 본다 — 정상일 때만 검사하면 오류 문구가 새어 나간다."""
    _set(monkeypatch, **kw)
    d = bank_transfer.diagnosis()
    parts = [d["message"], d["action"], *d.get("problems", [])]
    assert parts, "판정 문구가 비었다"
    assert not [p for p in parts if _md_hits(p)], f"별표가 남았다: {parts}"


def test_bank_transfer_config_endpoint_copy_is_plain_text() -> None:
    """화면 직행 문구(`guide`·`notice`)에 마크다운이 없다.

    ★AST 로 **그 함수의 실행 리터럴만** 본다 — 파일 전체를 grep 하면 독스트링·주석의
      정당한 `**` 가 전부 위양성이 된다(실측: 그렇게 세면 billing.py 만 11건이 잡힌다).
    """
    src = (_API / "routers/billing.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "bank_transfer_config"
    )
    body = fn.body[1:] if (fn.body and isinstance(fn.body[0], ast.Expr)) else fn.body  # 독스트링 제외
    lits = [
        n.value for b in body for n in ast.walk(b)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    assert len(lits) >= 4, "리터럴 수집이 비었다 — 검사기가 죽었다"
    assert not [s for s in lits if _md_hits(s)], "화면 직행 문구에 별표가 있다"
    # ★대조군 — 실제로 그 함수의 문구를 집었는가(엉뚱한 함수를 본 것이 아니다).
    assert any("입금자명" in s for s in lits), "수집 대상이 틀렸다"
