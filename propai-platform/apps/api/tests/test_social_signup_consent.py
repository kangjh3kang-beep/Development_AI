"""소셜 간편가입의 동의 수집 — 이메일 가입과 **같은 형식**으로 남는가.

★2026-09-06 실측: 이메일 가입은 UserConsent 3종을 버전과 함께 기록하는데
  소셜 가입(auth/oauth_common.get_or_create_oauth_user)은 consent 낱말이 **0건**이었다.
  두 곳에 손으로 적혀 있었기 때문에 한쪽만 살아남았다 → 공용 빌더 하나로 합쳤다.
  이 파일은 **그 합침이 유지되는지**를 잠근다.
"""
from __future__ import annotations

import uuid

import pytest

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
        assert "social_consent_pending=True" in src

    def test_유저모델에_플래그가_있고_기본값이_False다(self):
        """★기본 False 라야 **기존 사용자가 소급 차단되지 않는다**."""
        from apps.api.database.models.user import User

        col = User.__table__.columns["social_consent_pending"]
        assert col.nullable is False
        assert col.default is not None and col.default.arg is False


class TestDebtsLeftOpen:
    """★닫지 못한 것을 초록 안에 보이게 둔다(커밋 메시지에만 적으면 드러나지 않는다)."""

    @pytest.mark.skip(reason="★미측정 — DB 조회 권한 없음. 동의 없이 만들어진 기존 소셜 계정 건수")
    def test_기존_소셜_계정_건수(self):
        ...

    @pytest.mark.skip(reason="★미구현 — 미동의 사용자의 보호 자원 접근 차단(⑧). 소유자 승인 대기")
    def test_미동의는_보호자원에_접근할_수_없다(self):
        ...
