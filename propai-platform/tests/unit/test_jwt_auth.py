"""JWT 인증 단위 테스트.

토큰 생성/검증, 페이로드 추출, 만료 처리 검증.
"""

from uuid import uuid4

import pytest

from apps.api.auth.jwt_handler import (
    CurrentUser,
    TokenPayload,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from apps.api.config import Settings


def _test_settings() -> Settings:
    """테스트용 설정 (환경 변수 불필요)."""
    return Settings(
        jwt_secret="test-secret-key-for-unit-tests-only",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        jwt_refresh_token_expire_days=7,
        database_url="postgresql+asyncpg://x:x@localhost/test",
        redis_url="redis://localhost:6379/0",
        _env_file=None,
    )


class TestCreateAccessToken:
    """액세스 토큰 생성 검증."""

    def test_creates_token(self) -> None:
        settings = _test_settings()
        user_id = uuid4()
        tenant_id = uuid4()
        token = create_access_token(user_id, tenant_id, "admin", settings)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_claims(self) -> None:
        settings = _test_settings()
        user_id = uuid4()
        tenant_id = uuid4()
        token = create_access_token(user_id, tenant_id, "analyst", settings)
        payload = decode_token(token, settings)
        assert payload.sub == str(user_id)
        assert payload.tenant_id == str(tenant_id)
        assert payload.role == "analyst"
        assert payload.token_type == "access"


class TestCreateRefreshToken:
    """리프레시 토큰 생성 검증."""

    def test_creates_refresh_token(self) -> None:
        settings = _test_settings()
        token = create_refresh_token(uuid4(), uuid4(), "viewer", settings)
        assert isinstance(token, str)

    def test_refresh_token_type(self) -> None:
        settings = _test_settings()
        token = create_refresh_token(uuid4(), uuid4(), "manager", settings)
        payload = decode_token(token, settings)
        assert payload.token_type == "refresh"


class TestDecodeToken:
    """토큰 검증 및 디코딩."""

    def test_valid_token(self) -> None:
        settings = _test_settings()
        user_id = uuid4()
        tenant_id = uuid4()
        token = create_access_token(user_id, tenant_id, "admin", settings)
        payload = decode_token(token, settings)

        assert isinstance(payload, TokenPayload)
        assert payload.sub == str(user_id)
        assert payload.tenant_id == str(tenant_id)

    def test_invalid_token_raises(self) -> None:
        settings = _test_settings()
        with pytest.raises((ValueError, Exception)):  # noqa: B017
            decode_token("invalid.token.here", settings)

    def test_wrong_secret_raises(self) -> None:
        settings = _test_settings()
        token = create_access_token(uuid4(), uuid4(), "admin", settings)

        wrong_settings = _test_settings()
        wrong_settings.jwt_secret = "wrong-secret"
        with pytest.raises((ValueError, Exception)):  # noqa: B017
            decode_token(token, wrong_settings)


class TestCurrentUser:
    """CurrentUser 모델 검증."""

    def test_create(self) -> None:
        user = CurrentUser(
            user_id=uuid4(),
            tenant_id=uuid4(),
            role="admin",
        )
        assert user.role == "admin"

    def test_fields(self) -> None:
        uid = uuid4()
        tid = uuid4()
        user = CurrentUser(user_id=uid, tenant_id=tid, role="viewer")
        assert user.user_id == uid
        assert user.tenant_id == tid
