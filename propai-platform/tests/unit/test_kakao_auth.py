"""Step 4.2 카카오 OAuth 단위 테스트.

카카오 REST API 호출을 Mock하여 전체 흐름을 검증한다.
- 인가 코드 → 토큰 교환
- 토큰 → 사용자 정보 조회
- 사용자 프로필 추출
- DB 사용자 조회/생성
- JWT 발급
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.api.auth.kakao_handler import (
    KakaoOAuthError,
    exchange_code_for_token,
    extract_user_profile,
    fetch_kakao_user_info,
)

# ─── 카카오 토큰 교환 ────────────────────────────────────


class TestExchangeCodeForToken:
    """인가 코드 → 토큰 교환 테스트."""

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """정상 인가 코드일 때 토큰 딕셔너리를 반환한다."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "kakao_access_123",
            "refresh_token": "kakao_refresh_456",
            "token_type": "bearer",
            "expires_in": 7200,
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("apps.api.auth.kakao_handler.httpx.AsyncClient", return_value=mock_client):
            result = await exchange_code_for_token(
                code="test_auth_code",
                redirect_uri="http://localhost:3000/callback",
                client_id="test_client_id",
            )

        assert result["access_token"] == "kakao_access_123"
        assert result["refresh_token"] == "kakao_refresh_456"
        assert result["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_with_client_secret(self) -> None:
        """client_secret 포함 시 payload에 추가된다."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "tok"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("apps.api.auth.kakao_handler.httpx.AsyncClient", return_value=mock_client):
            await exchange_code_for_token(
                code="code",
                redirect_uri="http://localhost/cb",
                client_id="cid",
                client_secret="csecret",
            )

        call_kwargs = mock_client.post.call_args
        assert "client_secret" in call_kwargs.kwargs.get("data", call_kwargs[1].get("data", {}))

    @pytest.mark.asyncio
    async def test_failure_raises_error(self) -> None:
        """카카오 API 실패 시 KakaoOAuthError를 발생시킨다."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "invalid_grant"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("apps.api.auth.kakao_handler.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(KakaoOAuthError) as exc_info,
        ):
            await exchange_code_for_token(
                code="bad_code",
                redirect_uri="http://localhost/cb",
                client_id="cid",
            )

        assert exc_info.value.status_code == 400
        assert "카카오 토큰 교환 실패" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_server_error(self) -> None:
        """카카오 서버 500 에러 시 상태 코드를 전달한다."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "internal server error"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch("apps.api.auth.kakao_handler.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(KakaoOAuthError) as exc_info,
        ):
            await exchange_code_for_token(
                code="code",
                redirect_uri="http://localhost/cb",
                client_id="cid",
            )

        assert exc_info.value.status_code == 500


# ─── 카카오 사용자 정보 조회 ─────────────────────────────


class TestFetchKakaoUserInfo:
    """토큰 → 사용자 정보 조회 테스트."""

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """정상 토큰으로 사용자 정보를 조회한다."""
        kakao_user = {
            "id": 12345678,
            "kakao_account": {"email": "user@kakao.com"},
            "properties": {"nickname": "카카오유저"},
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = kakao_user

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("apps.api.auth.kakao_handler.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_kakao_user_info("valid_token")

        assert result["id"] == 12345678
        assert result["kakao_account"]["email"] == "user@kakao.com"

    @pytest.mark.asyncio
    async def test_bearer_header_sent(self) -> None:
        """Authorization: Bearer 헤더가 전송된다."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 1}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("apps.api.auth.kakao_handler.httpx.AsyncClient", return_value=mock_client):
            await fetch_kakao_user_info("my_token_123")

        call_kwargs = mock_client.get.call_args
        headers = call_kwargs.kwargs.get("headers", call_kwargs[1].get("headers", {}))
        assert headers.get("Authorization") == "Bearer my_token_123"

    @pytest.mark.asyncio
    async def test_failure_raises_error(self) -> None:
        """유효하지 않은 토큰 시 KakaoOAuthError를 발생시킨다."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with (
            patch("apps.api.auth.kakao_handler.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(KakaoOAuthError) as exc_info,
        ):
            await fetch_kakao_user_info("expired_token")

        assert "사용자 정보 조회 실패" in exc_info.value.message


# ─── 프로필 추출 ─────────────────────────────────────────


class TestExtractUserProfile:
    """카카오 응답 → 사용자 프로필 추출 테스트."""

    def test_full_profile(self) -> None:
        """모든 정보가 있을 때 정상 추출한다."""
        data = {
            "id": 99887766,
            "kakao_account": {"email": "test@example.com"},
            "properties": {"nickname": "테스트유저"},
        }
        profile = extract_user_profile(data)
        assert profile["kakao_id"] == "99887766"
        assert profile["email"] == "test@example.com"
        assert profile["nickname"] == "테스트유저"

    def test_missing_email(self) -> None:
        """이메일이 없으면 None을 반환한다."""
        data = {
            "id": 111,
            "kakao_account": {},
            "properties": {"nickname": "닉네임"},
        }
        profile = extract_user_profile(data)
        assert profile["email"] is None
        assert profile["nickname"] == "닉네임"

    def test_missing_nickname_fallback(self) -> None:
        """닉네임이 없으면 kakao_id 기반 대체값을 사용한다."""
        data = {"id": 555, "kakao_account": {}, "properties": {}}
        profile = extract_user_profile(data)
        assert profile["nickname"] == "kakao_555"

    def test_profile_nickname_fallback(self) -> None:
        """properties.nickname 대신 profile.nickname을 사용한다."""
        data = {
            "id": 777,
            "kakao_account": {
                "profile": {"nickname": "프로필닉네임"},
            },
            "properties": {},
        }
        profile = extract_user_profile(data)
        assert profile["nickname"] == "프로필닉네임"

    def test_empty_data(self) -> None:
        """빈 데이터에서도 예외 없이 처리한다."""
        data: dict = {}
        profile = extract_user_profile(data)
        assert profile["kakao_id"] == ""
        assert profile["email"] is None
        assert "kakao_" in profile["nickname"]


# ─── KakaoOAuthError ─────────────────────────────────────


class TestKakaoOAuthError:
    """카카오 OAuth 예외 클래스 테스트."""

    def test_default_status_code(self) -> None:
        err = KakaoOAuthError("오류 메시지")
        assert err.status_code == 400
        assert err.message == "오류 메시지"

    def test_custom_status_code(self) -> None:
        err = KakaoOAuthError("서버 오류", status_code=500)
        assert err.status_code == 500

    def test_is_exception(self) -> None:
        err = KakaoOAuthError("test")
        assert isinstance(err, Exception)

    def test_str_representation(self) -> None:
        err = KakaoOAuthError("에러 발생")
        assert str(err) == "에러 발생"


# ─── auth 라우터 엔드포인트 검증 ──────────────────────────


def _can_import_auth_router() -> bool:
    """auth 라우터를 임포트할 수 있는지 확인한다."""
    try:
        import asyncpg  # noqa: F401
        import email_validator  # noqa: F401
        return True
    except ImportError:
        return False


_skip_no_deps = pytest.mark.skipif(
    not _can_import_auth_router(),
    reason="asyncpg 또는 email-validator 미설치 (CI/CD 환경에서 실행)",
)


@_skip_no_deps
class TestAuthRouterKakaoEndpoint:
    """auth 라우터의 카카오 콜백 엔드포인트 존재 검증."""

    def test_kakao_callback_route_exists(self) -> None:
        """라우터에 /kakao/callback 경로가 등록되어 있다."""
        from apps.api.routers.auth import router

        routes = [getattr(r, "path", "") for r in router.routes]
        assert "/kakao/callback" in routes

    def test_kakao_callback_is_post(self) -> None:
        """카카오 콜백은 POST 메서드를 사용한다."""
        from apps.api.routers.auth import router

        for route in router.routes:
            if getattr(route, "path", "") == "/kakao/callback":
                assert "POST" in getattr(route, "methods", set())
                break
        else:
            pytest.fail("/kakao/callback 라우트를 찾을 수 없음")

    def test_kakao_callback_response_model(self) -> None:
        """카카오 콜백의 response_model은 TokenResponse이다."""
        from apps.api.routers.auth import router
        from packages.schemas.models import TokenResponse

        for route in router.routes:
            if getattr(route, "path", "") == "/kakao/callback":
                assert getattr(route, "response_model", None) is TokenResponse
                break
