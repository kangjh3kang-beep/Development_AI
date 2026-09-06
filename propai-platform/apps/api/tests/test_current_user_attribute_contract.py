"""`Depends(get_current_user)` 로 받은 것에서 **CurrentUser 에 없는 속성**을 읽지 않는지 전수로 잠근다.

★2026-09-06 라이브 사고의 **클래스 봉합**이다(단일 자리 수정이 아니라 전역 전파방지).
  `routers/auth.py` 는 `jwt_handler.get_current_user` 를 쓴다 → **CurrentUser**
  (`user_id`·`tenant_id`·`role` 뿐)를 준다. 그런데 나는
      user: User = Depends(get_current_user)          ← 타입 애노테이션만 User
      if not getattr(user, "consent_pending", False): return 204
  라고 써서, 필드가 없으니 **항상 False** → 무동작 204 → 사용자 8명이 라이브에서 잠겼다.
  ★`user.id` 도 없었다(CurrentUser 엔 `user_id`). 관대한 기본값이 **둘 다** 삼켰다.

★DB 필드가 필요하면 형제 `/auth/me`(auth.py) 처럼 **직접 읽어야** 한다:
      select(User).where(User.id == current_user.user_id)

★이 파일은 **의심 자리를 세는** 것이지 실행을 태우지 않는다 — 그래서 대조군으로
  판별력을 증명해 두었다: 버그가 살아 있던 커밋에서 이 로직이 **정확히 2건**을 잡았고
  (`user.consent_pending`·`user.id`) 고친 뒤 0건이다.
"""
from __future__ import annotations

import ast
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]

#: CurrentUser(jwt_handler) 가 실제로 가진 필드 — **정본에서 파생**한다(손으로 적지 않는다)
def _current_user_fields() -> set[str]:
    from apps.api.auth.jwt_handler import CurrentUser

    return set(CurrentUser.model_fields)


#: pydantic BaseModel 이 주는 것 — 위반이 아니다
_PYDANTIC_OK = {"model_dump", "model_fields", "model_copy", "model_validate", "dict", "json"}

_SKIP_PARTS = {".venv", "tests", "migrations", "node_modules", "__pycache__"}


def _files() -> list[Path]:
    return [
        p
        for p in API_ROOT.rglob("*.py")
        if not (_SKIP_PARTS & set(p.relative_to(API_ROOT).parts))
    ]


def _suspects() -> tuple[list[tuple[str, str, str, int]], int]:
    """(파일, 함수, 속성, 줄) 목록과 **주사한 파일 수**를 함께 돌려준다.

    ★주사 수를 함께 내는 이유: 0건이 「없다」인지 「조회기가 죽었다」인지 가르기 위해서다.
    """
    fields = _current_user_fields()
    out: list[tuple[str, str, str, int]] = []
    scanned = 0
    for p in _files():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        uses_jwt_variant = any(
            isinstance(n, ast.ImportFrom)
            and n.module
            and "jwt_handler" in n.module
            and any(a.name == "get_current_user" for a in n.names)
            for n in ast.walk(tree)
        )
        if not uses_jwt_variant:
            continue
        scanned += 1
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            names: set[str] = set()
            defaults = fn.args.defaults
            if defaults:
                for arg, default in zip(fn.args.args[-len(defaults) :], defaults, strict=True):
                    if (
                        isinstance(default, ast.Call)
                        and getattr(default.func, "id", "") == "Depends"
                        and default.args
                        and getattr(default.args[0], "id", "") == "get_current_user"
                    ):
                        names.add(arg.arg)
            if not names:
                continue
            for n in ast.walk(fn):
                if (
                    isinstance(n, ast.Attribute)
                    and isinstance(n.value, ast.Name)
                    and n.value.id in names
                    and n.attr not in fields
                    and n.attr not in _PYDANTIC_OK
                ):
                    out.append((str(p.relative_to(API_ROOT)), fn.name, f"{n.value.id}.{n.attr}", n.lineno))
    return out, scanned


class TestCurrentUserAttributeContract:
    def test_모집단이_실재한다(self):
        """★공허 진리 가드 — 주사한 파일이 0이면 「위반 0」은 조회기 사망이다."""
        _, scanned = _suspects()
        assert scanned >= 10, f"jwt_handler 판을 쓰는 파일 {scanned}개 — 너무 적다, 조회기 사망 의심"

    def test_필드_목록이_정본에서_파생된다(self):
        """★손으로 적으면 CurrentUser 가 바뀔 때 조용히 갈린다."""
        fields = _current_user_fields()
        assert {"user_id", "tenant_id", "role"} <= fields
        # ★사고의 전제 — 이것이 참이라 관대한 기본값이 위험했다
        assert "consent_pending" not in fields
        assert "id" not in fields

    def test_CurrentUser_에_없는_속성을_읽지_않는다(self):
        suspects, scanned = _suspects()
        detail = "\n".join(f"  {f}:{ln}  {fn}()  {attr}" for f, fn, attr, ln in sorted(suspects))
        assert suspects == [], (
            f"CurrentUser 에 없는 속성을 읽는 자리 {len(suspects)}건"
            f"(주사 {scanned}파일). DB 필드가 필요하면 "
            f"select(User).where(User.id == current_user.user_id) 로 직접 읽어라:\n" + detail
        )
