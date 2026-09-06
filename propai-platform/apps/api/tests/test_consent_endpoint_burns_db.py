"""동의 제출 엔드포인트가 **DB 를 실제로 태우는지** 잠근다.

★2026-09-06 라이브 사고 — 이 락이 없어서 프로덕션에서 8명이 잠겼다:
    user: User = Depends(get_current_user)      ← **타입 애노테이션만** User
    if not getattr(user, "consent_pending", False): return 204
  이 파일의 `get_current_user` 는 `jwt_handler` 것이고 `CurrentUser`
  (user_id·tenant_id·role)를 준다 — **DB User 가 아니다.**
  그 필드가 없으니 `getattr(..., False)` 가 **항상 False** → 멱등 분기로 빠져
  **아무것도 안 하고 204** 를 냈다. 사용자는 «동의했다» 고 믿는데 행은 0건이고
  플래그는 그대로라 **영원히 403** 이었다.

★관대한 기본값이 두 번째 결함까지 가렸다 — `user.id` 도 없다(CurrentUser 엔 `user_id`).
  기본값이 없었다면 AttributeError 로 **시끄럽게** 터졌을 것이다.

★기존 락(test_social_signup_consent.py)은 **순수 헬퍼만** 태웠다. 그래서 전부 초록이었다.
  «함수가 옳다」와 «엔드포인트가 그 함수를 쓴다」는 다른 축이다.
"""
from __future__ import annotations

import inspect

from apps.api.routers import auth as auth_router


class TestSubmitConsentSignature:
    """★서명·본문을 구조로 본다 — 라이브 DB 없이도 이 결함은 판정 가능하다."""

    def _src(self) -> str:
        return inspect.getsource(auth_router.submit_consent)

    def _code(self) -> str:
        """★주석·독스트링을 걷어낸 **실행 줄**만.

        2026-09-06: 이 파일을 쓰면서 사고를 **주석에 예시로** 적었더니
        (`getattr(user, "consent_pending", False)`) 그 예시가 내 검사에 걸려
        **위양성**이 났다. 《주석에 적은 예시가 다음 검사의 위양성이 된다》 그대로다.
        → 파서로 걷어낸다. 문자열 모양이 아니라 **실행되는 코드**를 본다.
        """
        import ast

        tree = ast.parse(inspect.getsource(auth_router.submit_consent).lstrip())
        fn = tree.body[0]
        body = fn.body[1:] if (fn.body and isinstance(fn.body[0], ast.Expr)
                               and isinstance(getattr(fn.body[0], "value", None), ast.Constant)
                               and isinstance(fn.body[0].value.value, str)) else fn.body
        code = "\n".join(ast.unparse(n) for n in body)
        assert len(code) > 200, "실행 줄이 너무 짧다 — 판정 불가"
        return code

    def test_CurrentUser_를_받고_DB_User_를_따로_읽는다(self):
        src = self._src()          # 서명은 원문에서(데코레이터·인자 애노테이션 포함)
        code = self._code()        # 본문은 실행 줄에서
        assert "current_user: CurrentUser" in src, "CurrentUser 로 받아야 한다"
        assert "select(User).where(User.id == current_user.user_id)" in code, (
            "DB User 를 직접 읽어야 한다 — CurrentUser 에는 consent_pending 이 없다"
        )

    def test_플래그를_기본값_없이_읽는다(self):
        """★`getattr(x, "consent_pending", False)` 는 「모르면 통과」다 — 그것이 사고를 냈다."""
        code = self._code()
        assert "getattr(" not in code, (
            "관대한 기본값으로 플래그를 읽으면 필드 부재가 조용히 통과한다"
        )
        assert "row_user.consent_pending" in code, "DB 행의 필드를 직접 읽어야 한다"

    def test_동의행을_쓰고_플래그를_내린다(self):
        """★두 축 — 기록만 하고 플래그를 안 내리면 사용자가 계속 잠긴다."""
        code = self._code()
        assert "build_consent_rows(" in code
        assert "db.add(row)" in code
        assert "row_user.consent_pending = False" in code
        assert "await db.commit()" in code

    def test_CurrentUser_에는_그_필드가_없다(self):
        """★사고의 전제를 못 박는다 — 이것이 참이라 getattr 기본값이 위험했다."""
        from apps.api.auth.jwt_handler import CurrentUser

        fields = set(CurrentUser.model_fields)
        assert "consent_pending" not in fields
        assert "id" not in fields          # ★`user.id` 도 없었다
        assert "user_id" in fields         # 대조군 — 모델은 살아 있다


class TestEndpointIsWiredToApp:
    def test_라우트가_등록돼_있고_204다(self):
        from apps.api.main import app

        posts = [
            r
            for r in app.routes
            if getattr(r, "path", "").endswith("/auth/me/consents")
            and "POST" in (getattr(r, "methods", None) or set())
        ]
        assert posts, "POST /auth/me/consents 라우트가 없다 — 판정 불가"
        for r in posts:
            assert r.status_code == 204
