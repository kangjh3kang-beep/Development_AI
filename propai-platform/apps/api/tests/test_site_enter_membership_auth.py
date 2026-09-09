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
    reason="라우터가 `datetime.UTC`(3.11+) 의존을 끌고 온다 — CI(3.12)에서 실행된다. "
           "★같은 축을 임포트 없이 보는 AST 락이 아래에 있어 이 스킵이 무잠금을 뜻하지 않는다.",
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
    calls = {c.func.id for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    # ★판정 함수 이름이 `verify_site_secret` → `resolve_entry` 로 올라갔다(리뷰 C2·M1).
    #   라우터가 부르는 것은 **다섯 결과를 내는 쪽**이어야 한다 — 참/거짓 두 값짜리를
    #   부르면 「비멤버」·「안 보냈다」가 다시 라우터 안의 손 분기로 내려온다.
    assert "resolve_entry" in calls, "판정을 서비스 층에 위임하지 않는다"
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
