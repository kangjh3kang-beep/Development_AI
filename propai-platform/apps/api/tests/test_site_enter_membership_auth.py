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
# B. 행위 — 두 모집단(CI 3.12)
# ─────────────────────────────────────────────────────────────────────────────

class _Res:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _DB:
    """비번 행의 유무로 두 모집단을 만든다."""

    def __init__(self, *, has_password: bool):
        self._has = has_password
        self.sql: list[str] = []

    async def execute(self, stmt, params=None):
        q = " ".join(str(stmt).split())
        self.sql.append(q)
        if "sales_site_passwords" in q:
            return _Res(("$2b$12$" + "x" * 53,) if self._has else None)
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
