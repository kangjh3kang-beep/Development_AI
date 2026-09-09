"""★**승인이 곧 인증이다** — 비번 미설정 현장에서 멤버가 진입할 수 있는가.

## 왜 (2026-09-09 · 라이브 실측)

읽기 전용 프로브로 쟀다 — **14현장 중 11현장이 2차비번 미설정**이고, 그 현장들은
`enter_site` 가 *"현장 2차비밀번호가 아직 설정되지 않았습니다"* **409** 로 답했다.
즉 **멤버여도 워크스페이스에 못 들어갔다.** 그 뒤에 세대 배치도·계약·수수료가 있고,
이 저장소가 방금 만든 **등록신청 승인 화면**도 거기 있다.

## 근거 둘

1. **사용자 결정**: *"관리자 및 상위레벨이 **승인할경우 비번없이 접속가능**하도록"*
2. **볼트 R5(채택 · Zoom 벤치마킹)**: *"passcode(공유 설계) ↔ password(공유 금지) 구분 —
   우리는 **공유되도록 설계된 값을 비밀번호로 저장 중**"*.
   현장 2차비번은 그 현장 사람 모두가 아는 **공유 비밀**이고 회전되지 않는다.
   「관리자가 개인에게 부여한 멤버십」보다 **약한 인증을 그 위에 강제**하고 있었다.

## 축 — 두 모집단을 **같은 실행에서** 가른다

| 현장 | 기대 |
|---|---|
| 비번 **미설정** | 멤버십으로 진입 · `auth="membership"` |
| 비번 **설정됨** | 여전히 검증 · 틀리면 401 · `auth="password"` |

★후자가 없으면 이 변경이 «비번을 통째로 걷어냈다» 와 구별되지 않는다.
★그리고 **멤버가 아니면** 어느 쪽이든 403 이다 — 그 가드는 이 변경이 건드리지 않는다.
"""

from __future__ import annotations

import sys
import uuid

import bcrypt
import pytest

_NEEDS_311 = pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason=(
        # ★사유는 **둘**이고 둘 다 실측했다(2026-09-09) — 하나만 적으면 다음 사람이
        #   `datetime.UTC` 만 고치고 «이제 로컬에서 돈다» 고 오독한다.
        #   ① `datetime.UTC` (3.11+) — `site_auth.py:21`
        #   ② PEP 695 제네릭 `class CRUDBase[M]:` — `app/crud/base.py` 는 3.10 에서
        #      **파싱조차 안 된다**(`py_compile` 실패). 라우터가 그 사슬을 끌고 온다.
        "라우터가 3.11+ 문법·API 두 가지에 의존한다(datetime.UTC · PEP 695) — CI(3.12)에서 실행된다. "
        "★같은 축을 임포트 없이 보는 AST 락이 아래에 있어 이 스킵이 무잠금을 뜻하지 않는다. "
        "★그래도 **AST 가 원리적으로 못 보는 것**이 있다: `if False:` 로 무력화해도 호출 노드는 "
        "AST 에 남는다. 그래서 아래 CI 전용 왕복 테스트가 **세 모집단**(멤버십·틀린비번·맞는비번)을 태운다. "
        "★★그리고 이 스킵은 **로컬에서 없앨 수 있다**(2026-09-10 실측 — GDAL 불필요): "
        "  /usr/bin/python3.12 -m venv ~/.venvs/propai312 && ~/.venvs/propai312/bin/pip install "
        "fastapi 'sqlalchemy[asyncio]' pydantic pydantic-settings bcrypt 'python-jose[cryptography]' "
        "pytest pytest-asyncio asyncpg httpx python-multipart email-validator geoalchemy2 structlog "
        "  → ~/.venvs/propai312/bin/python -m pytest tests/test_site_enter_membership_auth.py "
        "★변이 도구는 `sys.executable` 을 쓰므로 **도구 자체를 그 파이썬으로** 불러라. "
        "★이 스킵을 방치하면 락이 **CI 에서 처음 실행**된다 — 실제로 CI 가 내 스텁 결함을 두 번 잡았다."
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# A. AST — 임포트 없이 어디서나 돈다
# ─────────────────────────────────────────────────────────────────────────────

def _tree():
    import ast
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "app/api/endpoints/sales/site_auth.py"
    return ast.parse(p.read_text(encoding="utf-8"))


def _enter_fn():
    import ast
    for n in ast.walk(_tree()):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "enter_site":
            return n
    raise AssertionError("`enter_site` 를 찾지 못했다 — 축이 죽었다")


def test_membership_gate_still_runs_first() -> None:
    """★★멤버십 가드는 **그대로다** — 이 변경이 걷어낸 것은 비번이지 멤버십이 아니다.

    이것이 없으면 «비번을 없앴다» 가 «아무나 들어온다» 와 구별되지 않는다.
    """
    import ast
    fn = _enter_fn()
    src = ast.unparse(fn)
    assert "_resolve_role" in src, "멤버십 해석을 안 한다"
    assert "이 현장의 멤버가 아닙니다" in src, "멤버 아님을 거부하지 않는다"
    # 403 이 실제로 던져지는가(존재가 아니라 값).
    codes = {
        c.args[0].value
        for c in ast.walk(fn)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        and c.func.id == "HTTPException" and c.args and isinstance(c.args[0], ast.Constant)
    }
    assert 403 in codes, f"멤버 아님을 403 으로 막지 않는다: {codes}"


def test_no_password_no_longer_blocks_entry() -> None:
    """★★비번 미설정이 **409 로 막지 않는다** — 라이브 11/14 현장의 차단 요인.

    ★축은 «409 문자열이 사라졌나» 가 아니라 **«비번이 없는 분기가 토큰을 발급하나»** 다.
    """
    import ast
    fn = _enter_fn()

    # `if not pw:` 분기를 찾아 그 안을 본다.
    branch = None
    for n in ast.walk(fn):
        if isinstance(n, ast.If) and "not pw" in ast.unparse(n.test):
            branch = n
            break
    assert branch is not None, "비번 부재 분기를 못 찾았다 — 축이 죽었다"

    body = ast.unparse(branch)
    assert "issue_site_token" in body, (
        "비번이 없는 현장에서 토큰을 발급하지 않는다 — 멤버여도 진입이 막힌다"
    )
    assert "raise" not in body, f"비번 부재를 여전히 예외로 막는다: {body[:160]}"
    # ★표기가 아니라 **값**을 본다 — `ast.unparse` 는 따옴표를 정규화한다.
    consts = {c.value for c in ast.walk(branch)
              if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    assert "membership" in consts, "어떤 인증으로 들어왔는지 말하지 않는다(진단 불가)"


def test_both_auth_paths_are_distinguishable() -> None:
    """★두 진입 경로가 **응답에서 구별**된다 — 같은 모양이면 감사도 진단도 불가능하다."""
    import ast
    fn = _enter_fn()
    auth_values = {
        v.value
        for d in ast.walk(fn) if isinstance(d, ast.Dict)
        for k, v in zip(d.keys, d.values, strict=False)
        if isinstance(k, ast.Constant) and k.value == "auth"
        and isinstance(v, ast.Constant)
    }
    assert auth_values == {"membership", "password"}, f"실측: {auth_values}"


def test_password_is_optional_in_the_request_schema() -> None:
    """★`password` 가 **선택**인가 — 필수면 비번 없는 현장의 클라이언트가 보낼 값이 없다."""
    import ast
    for n in ast.walk(_tree()):
        if isinstance(n, ast.ClassDef) and n.name == "EnterRequest":
            fields = {
                t.target.id: ast.unparse(t.annotation)
                for t in n.body if isinstance(t, ast.AnnAssign) and isinstance(t.target, ast.Name)
            }
            assert "password" in fields
            assert "None" in fields["password"], f"password 가 여전히 필수다: {fields}"
            return
    raise AssertionError("`EnterRequest` 를 찾지 못했다")


# ─────────────────────────────────────────────────────────────────────────────
# B. 판정 — **서비스 층이라 로컬에서 돈다**(핵심 행위 락)
# ─────────────────────────────────────────────────────────────────────────────
#
# ★★2026-09-09: 앞 판은 이 판정이 라우터 안에 있어 행위 락이 전부 `skipif`(CI 전용)였고,
#   **CI 에서 처음 실행돼 빨개졌다** — 내 스텁이 SQLAlchemy Row 를 튜플로 흉내 냈기 때문
#   (`AttributeError: 'tuple' object has no attribute 'password_hash'`).
#   **skip 된 락은 「통과」가 아니라 「아직 모른다」다.**
#   ⇒ 판정을 의존 없는 `app/services/sales/site_entry.py` 로 내렸다.


def test_no_secret_means_membership_is_enough() -> None:
    """★★비번이 **설정돼 있지 않으면** 멤버십으로 진입한다 — 라이브 11/14 현장의 차단 요인."""
    from app.services.sales.site_entry import verify_site_secret

    assert verify_site_secret(None, None) == "membership"
    assert verify_site_secret("", "아무거나") == "membership"


def test_correct_secret_is_accepted_and_wrong_is_rejected() -> None:
    """★★**반대편 모집단** — 설정돼 있으면 **여전히 검증**한다(맞으면 통과·틀리면 거부).

    이것이 없으면 위 단언이 «비번을 통째로 걷어냈다» 와 구별되지 않는다.
    """
    from app.services.sales.site_entry import verify_site_secret

    h = bcrypt.hashpw(b"correct-horse", bcrypt.gensalt()).decode()
    assert verify_site_secret(h, "correct-horse") == "password"
    assert verify_site_secret(h, "wrong") == "reject"
    assert verify_site_secret(h, None) == "reject"
    assert verify_site_secret(h, "") == "reject"


def test_broken_hash_is_rejected_not_waved_through() -> None:
    """★깨진 해시는 **거부**한다(fail-closed) — «파싱 못 하니 통과» 는 그 자체가 우회로다."""
    from app.services.sales.site_entry import verify_site_secret

    for broken in ("not-a-hash", "$2b$xx$짧음", "x" * 5):
        assert verify_site_secret(broken, "무엇이든") == "reject", broken


def test_three_outcomes_are_distinct() -> None:
    """★세 결과가 **서로 다른 값**이다 — 뭉치면 호출부가 401 과 진입을 못 가른다."""
    from app.services.sales.site_entry import verify_site_secret

    h = bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode()
    outs = {verify_site_secret(None, None),
            verify_site_secret(h, "pw"),
            verify_site_secret(h, "no")}
    assert outs == {"membership", "password", "reject"}, f"실측: {outs}"


def test_router_delegates_the_decision() -> None:
    """★배선 — 라우터가 그 판정을 **부르고**, 자기 손으로 bcrypt 를 비교하지 않는가."""
    import ast
    fn = _enter_fn()
    # ★★축은 «`resolve_entry` 라는 이름이 호출부 **집합**에 있는가» 가 **아니다**.
    #   실측(2026-09-09 변이 ③): `outcome = verify_site_secret(...)` 로 되돌려도
    #   멤버십 거부 줄의 `resolve_entry(role, None, None)` 이 그 집합을 만족시켜 **SURVIVED**.
    #   존재를 잠그면 행위는 안 잠긴다 — 그래서 **«`outcome` 을 누가 만드는가»** 를 본다.
    producer = None
    for a in ast.walk(fn):
        if (isinstance(a, ast.Assign) and len(a.targets) == 1
                and isinstance(a.targets[0], ast.Name) and a.targets[0].id == "outcome"):
            assert isinstance(a.value, ast.Call) and isinstance(a.value.func, ast.Name), (
                "`outcome` 이 호출이 아닌 것으로 만들어진다 — 판정이 라우터 안으로 돌아왔다"
            )
            producer = a.value.func.id
    assert producer == "resolve_entry", (
        f"`outcome` 을 `{producer}` 가 만든다 — 판정을 **다섯 결과를 내는 층**에 위임하지 않는다"
    )

    # ★2치 판정 함수는 라우터에서 **아예 불리지 않아야** 한다(두 벌이 되면 갈라진다).
    calls = {c.func.id for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "verify_site_secret" not in calls, (
        "라우터가 2치 판정을 직접 부른다 — 「비멤버」·「안 보냈다」가 다시 손 분기로 내려온다"
    )
    src = ast.unparse(fn)
    assert "checkpw" not in src, (
        "라우터가 여전히 직접 bcrypt 를 비교한다 — 판정이 두 벌이 된다"
    )


# ─────────────────────────────────────────────────────────────────────────────
# C. 라우터 왕복 — CI 3.12 전용(같은 축을 위 B 가 로컬에서 덮는다)
# ─────────────────────────────────────────────────────────────────────────────

# ★실제 bcrypt 해시(평문 "correct-horse"). 가짜 문자열을 주면 `checkpw` 가 ValueError 를 내
#   테스트가 «틀린 비번은 401» 이 아니라 «해시가 깨졌다» 를 재게 된다.
_REAL_HASH = bcrypt.hashpw(b"correct-horse", bcrypt.gensalt()).decode()


class _Res:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _PwRow:
    """★SQLAlchemy Row 는 **속성 접근**을 지원한다 — 튜플로 흉내 내면 실제 코드를 못 태운다.

    실제로 그 차이가 CI 에서 드러났다(2026-09-09):
    `AttributeError: 'tuple' object has no attribute 'password_hash'`.
    로컬은 `skipif` 로 이 테스트를 건너뛰어 **CI 에서 처음 실행**됐다 —
    ★**skip 된 락은 「통과」가 아니라 「아직 모른다」다.**
    """

    def __init__(self, password_hash: str):
        self.password_hash = password_hash


class _DB:
    """비번 행의 유무로 두 모집단을 만든다."""

    def __init__(self, *, has_password: bool):
        self._has = has_password
        self.sql: list[str] = []

    async def execute(self, stmt, params=None):
        q = " ".join(str(stmt).split())
        self.sql.append(q)
        if "sales_site_passwords" in q:
            # bcrypt 가 파싱할 수 있는 **실제 해시**여야 한다(가짜 문자열이면 ValueError).
            return _Res(_PwRow(_REAL_HASH) if self._has else None)
        return _Res(None)          # 잠금 이력 없음

    async def commit(self):
        pass


@_NEEDS_311
@pytest.mark.asyncio
async def test_member_enters_when_no_password_is_set(monkeypatch) -> None:
    """★★**모집단 A** — 비번 미설정 현장에서 멤버가 **실제로 토큰을 받는다**."""
    from app.api.endpoints.sales import site_auth as mod

    site = type("S", (), {"id": uuid.uuid4(), "site_code": "s1", "site_name": "현장"})()

    async def _get_site(_db, _sid):
        return site

    async def _role(_db, _site, _user):
        return ("a1.t1", "MEMBER")

    async def _ensure(_db):
        pass

    monkeypatch.setattr(mod, "_get_site", _get_site, raising=True)
    monkeypatch.setattr(mod, "_resolve_role", _role, raising=True)
    monkeypatch.setattr(mod, "_ensure", _ensure, raising=True)

    user = type("U", (), {"id": uuid.uuid4(), "tenant_id": None})()
    out = await mod.enter_site(str(site.id), mod.EnterRequest(), db=_DB(has_password=False),
                               user=user)
    assert out["auth"] == "membership"
    assert out["site_token"], "토큰을 발급하지 않았다 — 멤버여도 진입 불가"
    assert out["role"] == "MEMBER"


@_NEEDS_311
@pytest.mark.asyncio
async def test_wrong_password_still_rejected_when_one_is_set(monkeypatch) -> None:
    """★★**모집단 B** — 비번이 설정된 현장은 **여전히 검증**한다(틀리면 401).

    이것이 없으면 위 단언이 «비번을 통째로 걷어냈다» 와 구별되지 않는다.
    """
    from fastapi import HTTPException

    from app.api.endpoints.sales import site_auth as mod

    site = type("S", (), {"id": uuid.uuid4(), "site_code": "s1", "site_name": "현장"})()

    async def _get_site(_db, _sid):
        return site

    async def _role(_db, _site, _user):
        return ("a1.t1", "MEMBER")

    async def _ensure(_db):
        pass

    monkeypatch.setattr(mod, "_get_site", _get_site, raising=True)
    monkeypatch.setattr(mod, "_resolve_role", _role, raising=True)
    monkeypatch.setattr(mod, "_ensure", _ensure, raising=True)

    user = type("U", (), {"id": uuid.uuid4(), "tenant_id": None})()
    with pytest.raises(HTTPException) as ei:
        await mod.enter_site(str(site.id), mod.EnterRequest(password="wrong"),
                             db=_DB(has_password=True), user=user)
    assert ei.value.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# D. `resolve_entry` — **다섯 결과를 한 값으로**(리뷰 C1·C2·M1 의 공통 처방)
# ═══════════════════════════════════════════════════════════════════════════

def test_non_member_is_forbidden() -> None:
    """★★**비멤버 모집단** — 이것이 없던 것이 C2 의 근본이다.

    ★★2026-09-09 리뷰 C2: 종전엔 «멤버 아님» 이 라우터 안 `if not role:` **한 줄**에만 살았고,
      테스트의 `_resolve_role` 스텁은 **항상 `("a1.t1","MEMBER")`** 를 돌려줬다 —
      **비멤버를 만드는 테스트가 0건**이었다. 그래서 `if not role:` → `if role is None:` 변이가
      (비멤버는 `""` 를 받으므로 **영원히 거짓**) `::VERDICT=SURVIVED` 였고,
      그 변이는 **인증된 아무나 아무 현장에** `role=""` 토큰으로 진입시킨다.
    """
    from app.services.sales.site_entry import resolve_entry

    for empty in (None, ""):
        assert resolve_entry(empty, None, None) == "forbidden"
        assert resolve_entry(empty, "$2b$12$" + "x" * 53, "무엇이든") == "forbidden", (
            "비멤버인데 비번만 맞으면 들여보낸다 — 멤버십 가드가 죽었다"
        )


def test_member_without_secret_enters_by_membership() -> None:
    """★★**반대편** — 멤버이고 비번 미설정이면 진입한다(라이브 11/14 현장)."""
    from app.services.sales.site_entry import resolve_entry

    assert resolve_entry("MEMBER", None, None) == "membership"
    assert resolve_entry("DEVELOPER", "", None) == "membership"


def test_missing_secret_is_not_a_failed_attempt() -> None:
    """★★**「안 보냈다」와 「틀렸다」는 다른 사건이다**(리뷰 C1).

    ★내가 이번 라운드에 만든 결함이다 — 모달이 열릴 때마다 **빈 비번**을 보내게 해 놓고
      서버는 그것을 **실패로 셌다**. `sales_site_login_attempts` 는 **시간으로 감쇠하지 않아**
      («성공하기 전까지 누적 5회») 모달을 다섯 번 여는 것만으로 계정이 잠기고,
      실패는 **설계상 조용해서** 사용자는 아무것도 못 본다.
      하필 «2차 요소를 걷어내지 않으려고 남긴» 비번 설정 현장을 정확히 때린다.
    """
    from app.services.sales.site_entry import resolve_entry

    h = bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode()
    assert resolve_entry("MEMBER", h, None) == "no_secret_supplied"
    assert resolve_entry("MEMBER", h, "") == "no_secret_supplied"
    # ★반대편 — 실제로 **틀린** 것은 여전히 `reject`(실패 카운트를 받아야 한다).
    assert resolve_entry("MEMBER", h, "wrong") == "reject"
    assert resolve_entry("MEMBER", h, "pw") == "password"


def test_five_outcomes_are_distinct() -> None:
    """★다섯 결과가 **서로 다른 값**이다 — 뭉치면 호출부가 400/401/403 을 못 가른다."""
    from app.services.sales.site_entry import ENTRY_OUTCOMES, resolve_entry

    h = bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode()
    got = {
        resolve_entry(None, None, None),
        resolve_entry("MEMBER", None, None),
        resolve_entry("MEMBER", h, "pw"),
        resolve_entry("MEMBER", h, ""),
        resolve_entry("MEMBER", h, "no"),
    }
    assert got == set(ENTRY_OUTCOMES), f"실측: {sorted(got)}"


def test_router_maps_each_outcome_to_its_own_status() -> None:
    """★배선 — 라우터가 **판정 값**으로 갈리고, 빈 비번을 **카운터 앞에서** 막는가.

    ★`no_secret_supplied` 의 400 이 실패 카운트 **뒤**에 있으면 C1 이 그대로 남는다.
    """
    import ast
    fn = _enter_fn()
    calls = {c.func.id for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "resolve_entry" in calls, "판정을 서비스 층에 위임하지 않는다"

    # ★★축은 «`fail_count` 라는 낱말» 이 아니라 **카운터를 올려 쓰는 문**이다.
    #   종전 판은 `src.find("fail_count")` 였는데 그 낱말이 **처음 나오는 자리**는
    #   잠금 여부를 **읽는** SELECT 다(카운터를 안 건드린다). 그래서 올바른 코드가
    #   «거부가 카운트 뒤에 있다» 로 신고됐다 — 위양성이고, 가드의 위양성도 결함이다.
    guard_line = write_line = None
    for n in ast.walk(fn):
        if isinstance(n, ast.If) and "no_secret_supplied" in ast.unparse(n.test):
            assert "HTTPException(400" in ast.unparse(n), (
                "빈 비번을 400 이 아닌 것으로 답한다 — 「안 보냈다」가 「틀렸다」로 섞인다"
            )
            guard_line = n.lineno if guard_line is None else min(guard_line, n.lineno)
        if (isinstance(n, ast.Constant) and isinstance(n.value, str)
                and "INSERT INTO sales_site_login_attempts" in n.value):
            write_line = n.lineno if write_line is None else min(write_line, n.lineno)
    assert guard_line is not None, "빈 비번을 가르지 않는다 — 잠금 카운터를 소진한다"
    assert write_line is not None, "실패 카운트를 **쓰는** 문을 못 찾았다 — 축이 죽었다"
    assert guard_line < write_line, (
        "빈 비번 거부가 **카운터 증가 뒤**에 있다 — 자동 시도가 계정을 잠근다"
    )

    # ★다섯 결과가 **서로 다른 상태코드**로 갈리는가(이름값을 하는 락).
    src = ast.unparse(fn)
    for outcome, status in (("forbidden", "403"), ("no_secret_supplied", "400")):
        i = src.find(outcome)
        assert i != -1, f"`{outcome}` 분기가 없다"
        assert f"HTTPException({status}" in src, f"`{outcome}` 에 {status} 이 없다"
    assert "HTTPException(401" in src, "틀린 비번의 401 이 사라졌다"


def test_site_lookup_excludes_deleted_sites() -> None:
    """★삭제된 현장은 진입 대상이 아니다(리뷰 M5).

    형제 조회 3곳은 전부 `deleted_at` 을 거르는데 `_get_site` 만 안 걸었고,
    비번 미설정 현장이 진입 가능해지면서 **삭제된 현장에 토큰 발급**이 열렸다.
    """
    import ast
    for n in ast.walk(_tree()):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_get_site":
            src = ast.unparse(n)
            assert "deleted_at" in src, "삭제된 현장을 그대로 준다"
            return
    raise AssertionError("`_get_site` 를 찾지 못했다 — 축이 죽었다")


def test_both_entry_paths_are_logged_by_one_helper() -> None:
    """★감사가 **양방향**인가 — 한쪽만 로그하면 «비번으로 들어온 사람» 을 셀 수 없다(M4)."""
    import ast
    fn = _enter_fn()
    calls = [c for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
             and c.func.id == "_log_entry"]
    assert len(calls) == 2, f"진입 로그가 {len(calls)}곳이다 — 두 경로 모두여야 한다"
    auths = {a.value for c in calls for a in c.args
             if isinstance(a, ast.Constant) and isinstance(a.value, str)}
    assert auths == {"membership", "password"}, f"실측: {auths}"


# ─────────────────────────────────────────────────────────────────────────────
# E. `password_set` — **모든** 현장에 실린다(리뷰 C1 프론트 게이팅의 입력)
# ─────────────────────────────────────────────────────────────────────────────

def test_my_sites_carries_password_set_for_every_site() -> None:
    """★목록이 «비번이 설정된 현장인가» 를 실어야 프론트가 자동 시도를 가를 수 있다.

    ★축은 «키가 어딘가 있다» 가 아니라 **«모집단 전체에 붙는다»** 다.
    `my_sites` 는 현장을 **세 갈래**로 모은다(멤버십 org · 소유 owner · 관리자 admin).
    키를 한 갈래 안에서 붙이면 나머지 두 갈래는 `undefined` 가 되고, 모달은 «모른다» 로
    떨어져 **비번이 설정된 현장에 다시 노크한다.** 그래서 `out` 전체를 도는 자리여야 한다.
    """
    import ast
    fn = None
    for n in ast.walk(_tree()):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "my_sites":
            fn = n
            break
    assert fn is not None, "`my_sites` 를 찾지 못했다 — 축이 죽었다"

    # `password_set` 을 대입하는 자리를 찾고, 그 **바깥 for 가 `out` 을 돈다**는 것까지 본다.
    def _sets_password_set(node) -> bool:
        for a in ast.walk(node):
            if isinstance(a, ast.Assign):
                for t in a.targets:
                    if (isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant)
                            and t.slice.value == "password_set"):
                        return True
        return False

    assert _sets_password_set(fn), "`my_sites` 가 `password_set` 을 싣지 않는다"

    over_out = [
        f for f in ast.walk(fn)
        if isinstance(f, ast.For) and _sets_password_set(f) and "out" in ast.unparse(f.iter)
    ]
    assert over_out, (
        "`password_set` 이 `out` 전수 루프 밖에서 붙는다 — 소유·관리자 현장이 빠진다"
    )

    # 한 번의 쿼리로 받는가(현장 수만큼 왕복하면 목록이 느려진다).
    src = ast.unparse(fn)
    assert "sales_site_passwords" in src, "비번 설정 여부를 조회하지 않는다"
    assert "ANY(:ids)" in src, "현장마다 따로 조회한다(N+1) — `IN`/`ANY` 한 번으로 받아라"


# ─────────────────────────────────────────────────────────────────────────────
# F. 변이 전수가 짚은 **행위 공백** — CI 3.12 전용 왕복(세 번째 모집단 + my_sites)
#
# ★기계 변이 55건 중 생존 20건의 대부분이 이 파일의 라우터 본문이었다(base 696b532a82e5).
#   원인은 하나다 — **로컬에서 라우터를 임포트할 수 없어** AST 로만 잠갔고,
#   AST 는 `if False:` 로 무력화된 분기와 살아 있는 분기를 **구별하지 못한다**.
#   그래서 「모양」이 아니라 **행위**로 태우는 자리를 여기에 모은다.
# ─────────────────────────────────────────────────────────────────────────────

@_NEEDS_311
@pytest.mark.asyncio
async def test_correct_password_enters_by_password(monkeypatch) -> None:
    """★★**모집단 C** — 비번이 **맞으면** 토큰이 나오고 `auth="password"` 다.

    이 모집단이 없어서 변이 전수에서 **성공 경로가 통째로 무잠금**이었다(생존 9건):
    응답 필드(`site_token`·`token_type`·`expires_in`·`role`·`role_label`·`features`) ·
    실패카운트 DELETE · `issue_site_token` 호출 · **그리고 `if outcome != "password":` 자체**.
    ★마지막 것이 핵심이다 — 그 조건이 뒤집히면 **틀린 비번이 통과**하는데,
      모집단 A(멤버십)·B(틀린 비번)만으로는 그 뒤집힘이 **양쪽 다 지나간다**.
    """
    from app.api.endpoints.sales import site_auth as mod

    site = type("S", (), {"id": uuid.uuid4(), "site_code": "s1", "site_name": "현장"})()

    async def _get_site(_db, _sid):
        return site

    async def _role(_db, _site, _user):
        return ("a1.t1", "MEMBER")

    async def _ensure(_db):
        pass

    monkeypatch.setattr(mod, "_get_site", _get_site, raising=True)
    monkeypatch.setattr(mod, "_resolve_role", _role, raising=True)
    monkeypatch.setattr(mod, "_ensure", _ensure, raising=True)

    user = type("U", (), {"id": uuid.uuid4(), "tenant_id": None})()
    db = _DB(has_password=True)
    out = await mod.enter_site(str(site.id), mod.EnterRequest(password="correct-horse"),
                               db=db, user=user)

    assert out["auth"] == "password", "맞는 비번인데 비번 경로로 기록되지 않는다"
    assert out["site_token"], "맞는 비번인데 토큰을 발급하지 않는다"
    assert out["token_type"] == "bearer"
    assert out["expires_in"] == mod._SITE_TOKEN_HOURS * 3600
    assert out["role"] == "MEMBER"
    assert out["role_label"], "역할 라벨이 비었다"
    assert isinstance(out["features"], list) and out["features"], "기능키가 비었다"

    # ★성공하면 **실패 카운트를 지운다** — 안 지우면 다음 오타 한 번에 잠긴다.
    assert any("DELETE FROM sales_site_login_attempts" in q for q in db.sql), (
        "성공 진입이 실패 카운트를 리셋하지 않는다"
    )


class _AllRes:
    """`.all()` 과 `.scalars().all()` 을 모두 받는 결과 객체."""

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class _MySitesDB:
    """`my_sites` 의 세 갈래를 **한 호출에서** 만든다(멤버십 · 소유 · 관리자).

    ★한 갈래만 만들면 «`password_set` 이 전수에 붙는가» 를 원리적으로 못 본다 —
      그것이 변이 ⑥ 이 노린 자리다.
    """

    def __init__(self, *, nodes, owned, allsites, with_pw):
        self._nodes, self._owned, self._all, self._pw = nodes, owned, allsites, with_pw
        self.sql: list[str] = []

    async def execute(self, stmt, params=None):
        q = " ".join(str(stmt).split())
        self.sql.append(q)
        if "sales_site_passwords" in q:
            return _AllRes([(sid,) for sid in self._pw])
        # ★★라우팅은 **WHERE 로** 가른다 — 「소유」와 「관리자 전체」는 둘 다
        #   `select(SalesSite)` 라 **SELECT 절이 글자 단위로 같다**(컬럼명 `organization_id`
        #   포함). SELECT 절의 낱말로 가르면 두 갈래가 **한 갈래로 뭉친다** —
        #   그러면 「세 갈래 전수」를 단언해도 실제로는 두 갈래만 태운다(공허해진다).
        if "sales_org_nodes" in q and "sales_sites" in q:
            return _AllRes(self._nodes)          # (a) 멤버십 조인
        if "ORDER BY" in q:
            return _AllRes(self._all)            # (c) 관리자 전체 — 유일하게 정렬한다
        if "organization_id =" in q:
            return _AllRes(self._owned)          # (b) 소유 테넌트
        return _AllRes([])

    async def commit(self):
        pass


@_NEEDS_311
@pytest.mark.asyncio
async def test_my_sites_marks_password_set_on_all_three_membership_kinds(monkeypatch) -> None:
    """★★`password_set` 이 **세 갈래 전부**에 붙고, **두 값**이 실제로 갈리는가.

    ★AST 락(위 E)은 «`out` 을 도는 루프 안에서 붙는다» 를 본다. 그런데 `if out:` 을
      `if False:` 로 무력화하면 그 루프는 **도달 불가**가 되는데 **AST 에는 그대로 남는다**
      — 실측 생존(변이 `조건무력화 site_auth.py:322`). 그래서 행위로 태운다.
    """
    from app.api.endpoints.sales import site_auth as mod

    tenant = uuid.uuid4()

    def _site(name):
        return type("S", (), {
            "id": uuid.uuid4(), "site_code": name, "site_name": name,
            "development_type": "APT", "status": "ACTIVE", "organization_id": tenant,
        })()

    s_org, s_own, s_all = _site("org"), _site("own"), _site("all")
    node = type("N", (), {
        "node_type": "MEMBER", "path": "a1.t1", "id": uuid.uuid4(), "site_id": s_org.id,
    })()

    async def _ensure(_db):
        pass

    monkeypatch.setattr(mod, "_ensure", _ensure, raising=True)
    user = type("U", (), {"id": uuid.uuid4(), "tenant_id": tenant, "role": "superadmin"})()

    # 비번은 **org 현장에만** 설정돼 있다 → 두 모집단이 같은 실행에서 갈려야 한다.
    db = _MySitesDB(nodes=[(node, s_org)], owned=[s_own], allsites=[s_all],
                    with_pw={str(s_org.id)})
    rows = await mod.my_sites(db=db, user=user)

    by_id = {r["site_id"]: r for r in rows}
    assert len(by_id) == 3, f"세 갈래가 다 안 나왔다: {sorted(r['membership'] for r in rows)}"
    assert {r["membership"] for r in rows} == {"org", "owner", "admin"}

    # ★전수 — 어느 갈래도 `password_set` 이 **빠지면 안 된다**.
    missing = [r["membership"] for r in rows if "password_set" not in r]
    assert not missing, f"`password_set` 이 빠진 갈래: {missing}"

    # ★두 값이 실제로 갈린다(전부 True 나 전부 False 면 프론트 게이팅이 무의미하다).
    assert by_id[str(s_org.id)]["password_set"] is True
    assert by_id[str(s_own.id)]["password_set"] is False
    assert by_id[str(s_all.id)]["password_set"] is False


def test_role_endpoint_exposes_lockout_state() -> None:
    """★잠긴 사용자를 **식별할 수단**이 있는가(리뷰 «What's Missing»).

    종전엔 `fail_count`·`locked_until` 이 **401/429 응답에만** 드러났다 — 즉 상태를 알려면
    **또 시도해야** 했고(그 시도가 카운터를 더 쓴다), 관리자는 조회할 방법이 없었다.
    ★자기 자신의 상태만 싣는다 — `user_id` 로 좁히지 않으면 남의 잠금이 새어 나간다.
    """
    import ast
    fn = None
    for n in ast.walk(_tree()):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "site_role":
            fn = n
            break
    assert fn is not None, "`site_role` 을 찾지 못했다 — 축이 죽었다"
    src = ast.unparse(fn)

    keys = {c.value for c in ast.walk(fn)
            if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    for k in ("locked_until", "fail_count", "password_set"):
        assert k in keys, f"`/role` 이 `{k}` 를 싣지 않는다"

    assert "sales_site_login_attempts" in src, "잠금 이력을 조회하지 않는다"
    # ★자기 상태만 — `user_id` 로 좁히지 않으면 남의 잠금이 새어 나간다.
    assert "user_id=:u" in src, (
        "잠금 조회가 사용자로 좁혀지지 않는다 — 남의 잠금 상태가 새어 나간다"
    )


# ─────────────────────────────────────────────────────────────────────────────
# G. 3.12 재감사가 남긴 **설명 불가 생존**을 닫는다 (2026-09-10)
#
# ★로컬 3.12 venv 로 라우터를 태울 수 있게 되자 생존이 20 → 13 으로 줄었고,
#   남은 것 중 **셋이 진짜 구멍**이었다. 셋 다 «내 단언이 그 자리를 안 본다» 였다.
# ─────────────────────────────────────────────────────────────────────────────

async def _enter(*, has_password: bool, password=None, tenant=None, role="MEMBER", site=None):
    """두 경로를 **같은 방식으로** 태우는 헬퍼 — 계약 비교를 하려면 축이 같아야 한다.

    ★`site` 를 인자로 받는다. 호출마다 새 현장을 만들면 `site_id` 가 달라져
      «두 경로의 응답이 갈렸다» 는 **내 픽스처가 만든 거짓 차이**가 된다(실측 위양성).
    """
    import pytest as _pytest

    from app.api.endpoints.sales import site_auth as mod

    if site is None:
        site = type("S", (), {"id": uuid.uuid4(), "site_code": "s1", "site_name": "현장"})()

    async def _get_site(_db, _sid):
        return site

    async def _role(_db, _site, _user):
        return ("a1.t1", role)

    async def _ensure(_db):
        pass

    mp = _pytest.MonkeyPatch()
    mp.setattr(mod, "_get_site", _get_site, raising=True)
    mp.setattr(mod, "_resolve_role", _role, raising=True)
    mp.setattr(mod, "_ensure", _ensure, raising=True)
    try:
        user = type("U", (), {"id": uuid.uuid4(), "tenant_id": tenant})()
        body = mod.EnterRequest(password=password) if password is not None else mod.EnterRequest()
        return await mod.enter_site(str(site.id), body, db=_DB(has_password=has_password),
                                    user=user)
    finally:
        mp.undo()


@_NEEDS_311
@pytest.mark.asyncio
async def test_both_entry_paths_return_the_same_response_contract() -> None:
    """★★두 경로의 응답이 **같은 키 집합**인가 — `auth` 값만 달라야 한다.

    ★변이 실측(2026-09-10 · 3.12): 멤버십 경로의 `token_type`·`expires_in`·`role_label`·
      `features` 를 **줄삭제해도 생존**했다. 성공 경로(비번)는 필드를 하나씩 단언했는데
      멤버십 경로는 `auth`·`site_token`·`role` 셋만 봤기 때문이다.
    ⇒ 축을 «필드를 손으로 나열» 이 아니라 **«두 경로의 키 집합이 같다»** 로 바꾼다.
      한쪽에서 필드가 빠지면 **양쪽 어디서 빠지든** 이 단언이 깨진다(파생형).
    """
    # ★**같은 현장**을 두 경로에 태운다 — 안 그러면 `site_id` 차이가 계약 차이로 오독된다.
    site = type("S", (), {"id": uuid.uuid4(), "site_code": "s1", "site_name": "현장"})()
    membership = await _enter(has_password=False, site=site)
    password = await _enter(has_password=True, password="correct-horse", site=site)

    assert set(membership) == set(password), (
        "두 진입 경로의 응답 계약이 갈렸다 — 화면이 한쪽에서만 동작하게 된다: "
        f"membership-only={sorted(set(membership) - set(password))} "
        f"password-only={sorted(set(password) - set(membership))}"
    )
    # ★공허 방지 — 계약이 «비었다» 로 같아지면 안 된다.
    assert len(membership) >= 8, f"응답 필드가 붕괴했다: {sorted(membership)}"

    # ★구별되는 것은 **`auth` 하나뿐**이어야 한다(그것이 이 필드의 존재 이유다).
    differing = {k for k in membership if membership[k] != password[k]}
    assert "auth" in differing, "두 경로가 `auth` 로 구별되지 않는다"
    assert differing <= {"auth", "site_token"}, (
        f"`auth`(와 토큰) 말고도 갈리는 필드가 있다: {sorted(differing - {'auth', 'site_token'})}"
    )
    assert membership["auth"] == "membership" and password["auth"] == "password"


@_NEEDS_311
@pytest.mark.asyncio
async def test_site_token_carries_the_users_tenant() -> None:
    """★발급 토큰이 **그 사용자의 테넌트**를 싣는가.

    ★변이 실측(2026-09-10): `getattr(user, "tenant_id", None)` 의 속성명을 바꿔도 **생존**했다.
      기존 테스트가 `tenant_id=None` 인 사용자만 태워서 **바뀐 값과 원래 값이 같았다** —
      두 모집단이 아니라 한 모집단이었다(픽스처가 차를 0으로 만든 전형).
    """
    from jose import jwt as _jwt

    tenant = uuid.uuid4()
    out = await _enter(has_password=False, tenant=tenant)
    claims = _jwt.get_unverified_claims(out["site_token"])
    assert claims["tenant_id"] == str(tenant), (
        "현장 토큰이 사용자의 테넌트를 싣지 않는다 — 하류가 테넌트 스코프를 잃는다"
    )
    assert claims["site_role"] == "MEMBER"
    assert claims["scope"] == "sales_site"

    # ★반대편 모집단 — 테넌트가 없으면 `None` 이다(빈 문자열·문자열 "None" 이 아니라).
    out2 = await _enter(has_password=False, tenant=None)
    assert _jwt.get_unverified_claims(out2["site_token"])["tenant_id"] is None


@_NEEDS_311
@pytest.mark.asyncio
async def test_role_endpoint_reports_lockout_at_runtime(monkeypatch) -> None:
    """★`/role` 의 잠금 상태를 **행위로** 태운다(종전엔 AST 락뿐이었다).

    ★변이 실측(2026-09-10): `locked_until = att.locked_until if att else None` 을 **줄삭제해도
      생존**했다(그러면 `NameError` 로 500 이 난다). `site_role` 을 부르는 테스트가 0건이었다.
    """
    # ★`UTC` 는 3.11+ 다 — **함수 안에서** 임포트한다(모듈 최상단이면 3.10 수집이 깨진다).
    from datetime import UTC, datetime

    from app.api.endpoints.sales import site_auth as mod

    site = type("S", (), {"id": uuid.uuid4(), "site_code": "s1", "site_name": "현장"})()
    when = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)

    class _AttRow:
        fail_count = 4
        locked_until = when

    class _RoleDB:
        def __init__(self, *, attempt):
            self._attempt = attempt

        async def execute(self, stmt, params=None):
            q = " ".join(str(stmt).split())
            if "sales_site_login_attempts" in q:
                return _Res(self._attempt)
            if "sales_site_passwords" in q:
                return _Res((1,))
            return _Res(None)

        async def commit(self):
            pass

    async def _get_site(_db, _sid):
        return site

    async def _role(_db, _site, _user):
        return ("a1.t1", "MEMBER")

    async def _ensure(_db):
        pass

    monkeypatch.setattr(mod, "_get_site", _get_site, raising=True)
    monkeypatch.setattr(mod, "_resolve_role", _role, raising=True)
    monkeypatch.setattr(mod, "_ensure", _ensure, raising=True)
    user = type("U", (), {"id": uuid.uuid4(), "tenant_id": None})()

    # 모집단 A — 잠긴 사용자: 언제 풀리는지와 몇 번 틀렸는지를 **말한다**.
    locked = await mod.site_role(str(site.id), db=_RoleDB(attempt=_AttRow()), user=user)
    assert locked["locked_until"] == when.isoformat(), "잠금 해제 시각을 말하지 않는다"
    assert locked["fail_count"] == 4
    assert locked["password_set"] is True

    # 모집단 B — 이력 없는 사용자: 잠기지 않았음을 **구별 가능하게** 말한다.
    clean = await mod.site_role(str(site.id), db=_RoleDB(attempt=None), user=user)
    assert clean["locked_until"] is None
    assert clean["fail_count"] == 0
