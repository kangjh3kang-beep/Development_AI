"""소셜 간편가입의 동의 수집 — 이메일 가입과 **같은 형식**으로 남는가.

★2026-09-06 실측: 이메일 가입은 UserConsent 3종을 버전과 함께 기록하는데
  소셜 가입(auth/oauth_common.get_or_create_oauth_user)은 consent 낱말이 **0건**이었다.
  두 곳에 손으로 적혀 있었기 때문에 한쪽만 살아남았다 → 공용 빌더 하나로 합쳤다.
  이 파일은 **그 합침이 유지되는지**를 잠근다.
"""
from __future__ import annotations

import uuid

from apps.api.auth.oauth_common import CONSENT_TYPES, build_consent_rows


class TestConsentBuilderIsTheSingleGate:
    def test_세_종류를_모두_만든다(self):
        uid = uuid.uuid4()
        rows = build_consent_rows(
            user_id=uid, agree_terms=True, agree_privacy=True,
            agree_marketing=False, policy_version="2026-06-15", ip="1.2.3.4",
        )
        # ★모집단 하한 — 종류가 줄면 「위반 0」이 공허해진다
        assert len(rows) == len(CONSENT_TYPES) >= 3
        assert {r.consent_type for r in rows} == set(CONSENT_TYPES)
        assert all(r.user_id == uid for r in rows)
        assert all(r.policy_version == "2026-06-15" for r in rows)

    def test_선택동의_거부도_명시_기록한다(self):
        """★거부(False)를 안 남기면 「묻지 않았다」와 구별되지 않는다."""
        rows = build_consent_rows(
            user_id=uuid.uuid4(), agree_terms=True, agree_privacy=True,
            agree_marketing=False, policy_version="v", ip=None,
        )
        by = {r.consent_type: r.agreed for r in rows}
        assert by["marketing"] is False          # 행이 **있고** 값이 False
        assert by["terms_of_service"] is True
        assert by["privacy_policy"] is True

    def test_두_모집단이_다른_값을_낸다(self):
        """★모두 True 인 픽스처만 쓰면 배선을 끊어도 결과가 같다."""
        allow = build_consent_rows(
            user_id=uuid.uuid4(), agree_terms=True, agree_privacy=True,
            agree_marketing=True, policy_version="v", ip=None,
        )
        deny = build_consent_rows(
            user_id=uuid.uuid4(), agree_terms=False, agree_privacy=False,
            agree_marketing=False, policy_version="v", ip=None,
        )
        assert [r.agreed for r in allow] != [r.agreed for r in deny]

    def test_정책버전은_전달된_값이_그대로_실린다(self):
        rows = build_consent_rows(
            user_id=uuid.uuid4(), agree_terms=True, agree_privacy=True,
            agree_marketing=True, policy_version="2099-12-31", ip=None,
        )
        assert {r.policy_version for r in rows} == {"2099-12-31"}


class TestBothPathsUseTheSameGate:
    """★공용화의 핵심 — 두 경로가 **같은 함수**를 통과하는가.

    소스 문자열이 아니라 **모듈 객체 동일성**으로 본다.
    (소스에 이름이 있는 것과 그것이 실제로 불리는 것은 다르다.)
    """

    def test_이메일_가입_라우터가_공용_빌더를_참조한다(self):
        from apps.api.auth import oauth_common
        from apps.api.routers import auth as auth_router

        assert auth_router.build_consent_rows is oauth_common.build_consent_rows

    def test_소셜_신규는_동의_미완으로_시작한다(self):
        """★플래그가 없으면 화면이 동의 단계를 그릴 근거가 없다."""
        import inspect

        from apps.api.auth import oauth_common

        src = inspect.getsource(oauth_common.get_or_create_oauth_user)
        assert "consent_pending=True" in src

    def test_유저모델에_플래그가_있고_기본값이_False다(self):
        """★기본 False 라야 **기존 사용자가 소급 차단되지 않는다**."""
        from apps.api.database.models.user import User

        col = User.__table__.columns["consent_pending"]
        assert col.nullable is False
        assert col.default is not None and col.default.arg is False


class TestRetroactiveBackfill:
    """★소급 — 「앞으로만」이 아니라 **이미 있는 미동의자**도 다시 동의해야 한다.

    2026-09-06 라이브 실측(탈퇴 제외)이 모집단을 바꿨다:
      소셜 2/2 동의 0건 · **이메일 6/11 도 동의 0건**(동의 기능 도입 2026-08-27 이전 계정)
    그래서 컬럼 이름에서 social 을 뺐고, 마이그레이션이 소급으로 채운다.
    """

    def _sql(self) -> str:
        """★소스 모양이 아니라 **실제로 실행되는 문자열**을 태운다.

        2026-09-06: ①파일 소스를 읽었더니 f-string 보간 전 `{_COL}` 을 봐서 거짓 실패
                    ②마이그레이션 모듈을 import 했더니 alembic 미설치로 **실행 불가**
        → SQL 을 alembic 에 의존하지 않는 모듈로 빼고 그것을 태운다.
        """
        from apps.api.database.consent_backfill import BACKFILL_SQL

        sql = " ".join(BACKFILL_SQL.split())
        assert len(sql) > 40, "SQL 이 너무 짧다 — 판정 불가"
        return sql

    def test_소급_UPDATE_가_존재한다(self):
        sql = self._sql()
        assert "UPDATE users" in sql
        assert "NOT EXISTS" in sql and "user_consents" in sql
        assert "consent_pending = true" in sql       # ★보간된 실제 컬럼명

    def test_탈퇴자는_소급_대상에서_제외한다(self):
        assert "deleted_at IS NULL" in self._sql()

    def test_이미_동의한_사용자는_건드리지_않는다(self):
        """★멱등 — 재실행이 동의자를 미완으로 되돌리면 안 된다."""
        assert "consent_pending = false" in self._sql()

    def test_컬럼_이름에_social_이_없다(self):
        """★모집단이 소셜만이 아니므로 이름이 거짓이면 다음 사람이 오해한다."""
        from apps.api.database.models.user import User

        assert "consent_pending" in User.__table__.columns
        assert "social_consent_pending" not in User.__table__.columns


class TestConsentGateIsEnforced:
    """★수집과 강제는 다르다 — 건너뛸 수 있으면 그 동의는 장식이다."""

    def _main_src(self) -> str:
        import inspect

        import apps.api.main as m

        return inspect.getsource(m)

    def test_게이트_미들웨어가_존재하고_403을_낸다(self):
        src = self._main_src()
        assert "_require_consent" in src
        assert "consent_required" in src
        # ★401 이 아니라 403 — 인증은 유효하고 권한 상태가 미완이다
        assert "status_code=403" in src

    def test_동의하러_갈_길이_열려_있다(self):
        """★탈출구가 없으면 동의 미완자는 **동의할 수도 없다**(자기모순)."""
        from apps.api.main import _CONSENT_EXEMPT_PREFIXES

        assert len(_CONSENT_EXEMPT_PREFIXES) >= 3          # 모집단 하한
        # 동의 제출 경로가 실제로 면제에 걸리는가 — 낱말이 아니라 **판정으로** 본다
        assert "/api/v1/auth/me/consents".startswith(_CONSENT_EXEMPT_PREFIXES)
        assert "/api/v1/auth/login".startswith(_CONSENT_EXEMPT_PREFIXES)

    def test_보호자원은_면제되지_않는다(self):
        """★음성 대조군 — 전부 면제면 게이트가 아무것도 막지 않는다."""
        from apps.api.main import _CONSENT_EXEMPT_PREFIXES

        for guarded in ("/api/v1/projects", "/api/v1/registry/bulk", "/api/v1/growth/insights"):
            assert not guarded.startswith(_CONSENT_EXEMPT_PREFIXES), guarded

    def test_면제는_접두로_판정한다(self):
        """★낱말 포함으로 판정하면 /api/v1/xxx/legal 같은 것도 열린다."""
        src = self._main_src()
        assert "path.startswith(_CONSENT_EXEMPT_PREFIXES)" in src


class TestBackfillIsNotAutoApplied:
    """★소급이 **배포 부수효과로** 적용되지 않는지 잠근다.

    2026-09-06 실측: `infra/deploy-zero-downtime.sh:234` 가 트래픽 전환 **전에**
    `alembic upgrade head` 를 돌린다. 그래서 versions/ 에 소급을 두면
    머지 → 배포 → 소급이 **한 덩어리**가 되어 «확증 후 소급» 이 불가능해진다.
    소급 대상 8명에 **사용자 본인과 super_admin** 이 포함되므로 부수효과로 일어나면 안 된다.
    """

    def _versions_dir(self):
        from pathlib import Path

        return Path(__file__).resolve().parents[1] / "database" / "migrations" / "versions"

    def test_배포되는_리비전은_소급을_실행하지_않는다(self):
        p = self._versions_dir() / "v62_9_consent_pending.py"
        assert p.exists(), "컬럼 리비전이 없다 — 판정 불가"
        src = p.read_text(encoding="utf-8")
        assert "add_column" in src            # ★대조군 — 이 리비전이 하는 일은 있다
        assert "BACKFILL_SQL" not in src      # ★소급은 여기 없다

    def test_versions_안에_소급_리비전이_없다(self):
        """★파일 하나만 보지 않는다 — 디렉토리 전수로 «어디에도 없음»을 본다."""
        hits = [
            p.name
            for p in self._versions_dir().glob("*.py")
            if "BACKFILL_SQL" in p.read_text(encoding="utf-8")
        ]
        assert hits == [], f"소급이 배포 경로에 있다: {hits}"

    def test_소급_리비전이_승인_대기_자리에_보관돼_있다(self):
        """★«없다»와 «잃어버렸다»는 다르다 — 대기 파일이 실재하는지도 본다."""
        from pathlib import Path

        p = (
            Path(__file__).resolve().parents[3]
            / "_workspace" / "pending_migrations" / "v62_10_consent_backfill.py.pending"
        )
        assert p.exists(), f"소급 리비전 대기 파일이 없다: {p}"
        src = p.read_text(encoding="utf-8")
        assert "BACKFILL_SQL" in src
        assert "사용자 승인" in src


class TestAppActuallyBoots:
    """★「테스트가 통과한다」와 「앱이 뜬다」는 다른 축이다.

    2026-09-06 실측: `POST /me/consents` 에 `-> None` 을 붙였더니 이 파일의
    `from __future__ import annotations` 때문에 그것이 **문자열 "None"** 이 되고,
    FastAPI 가 response_model 로 읽어 `Status code 204 must not have a response body`
    로 **앱 기동 자체가 실패**했다 — CI 가 9 failed · **295 errors**(전 스위트 오염).
    내 단위 테스트는 앱을 안 띄우므로 **전부 초록이었다.**

    ★그리고 다른 파일의 형제(`-> None`)를 보고 맞춘 것이 오판이었다 —
      **같은 파일의 형제** `/account/withdraw` 가 이미 `Response(status_code=204)` 였다(§29).
    """

    def test_앱이_뜨고_동의_라우트가_204로_등록된다(self):
        from apps.api.main import app

        # ★대조군 — 라우트가 아예 없으면 「204 위반 0건」은 공허하다
        posts = [
            r
            for r in app.routes
            if getattr(r, "path", "").endswith("/auth/me/consents")
            and "POST" in (getattr(r, "methods", None) or set())
        ]
        assert posts, "POST /auth/me/consents 라우트가 없다 — 판정 불가"
        for r in posts:
            assert r.status_code == 204, f"{r.path} status={r.status_code}"

    def test_204_라우트는_응답모델을_갖지_않는다(self):
        """★이것이 기동을 깨뜨린 실제 조건이다 — 상태코드가 아니라 response_model.

        ★★이 락은 **로컬에서는 판별력이 없다**(2026-09-06 실측):
            로컬 fastapi 0.135.1 — `-> None` 을 response_model 로 만들지 않는다
            CI   fastapi 0.115.0 — 만든다 → 204 단언에서 **기동 실패**
          그래서 `-> None` 을 되돌리는 변이가 로컬에서 **SURVIVED** 했다.
          「CAUGHT」로 인용하지 말 것 — **판정은 CI 에서만 유효**하다.
          《같은 명령이 같은 게이트는 아니다 — 버전까지 맞춰라》(CLAUDE.md §32).
        """
        from apps.api.main import app

        bad = [
            (r.path, r.status_code)
            for r in app.routes
            if getattr(r, "status_code", None) == 204 and getattr(r, "response_model", None)
        ]
        assert bad == [], f"204 인데 response_model 을 가진 라우트: {bad}"
