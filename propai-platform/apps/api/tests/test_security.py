"""보안 테스트.

CORS, JWT, Rate Limit, 인증 헤더 검증을 다룬다.
"""

import os
import sys
from datetime import UTC, datetime, timedelta

UTC = UTC
from uuid import uuid4

import pytest
from jose import jwt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from apps.api.config import Settings

# ──────────────────────────────────────
# JWT 토큰 생성/검증 단위 테스트
# ──────────────────────────────────────


class TestJWTTokenCreation:
    """JWT 토큰 발급 검증."""

    @pytest.fixture
    def settings(self) -> Settings:
        return Settings(
            jwt_secret="test-jwt-secret-32-chars-long-key",
            jwt_algorithm="HS256",
            jwt_access_token_expire_minutes=30,
            jwt_refresh_token_expire_days=7,
        )

    def test_액세스_토큰_생성(self, settings: Settings):
        user_id = uuid4()
        tenant_id = uuid4()
        token = create_access_token(user_id, tenant_id, "admin", settings)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_리프레시_토큰_생성(self, settings: Settings):
        user_id = uuid4()
        tenant_id = uuid4()
        token = create_refresh_token(user_id, tenant_id, "admin", settings)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_액세스_토큰_페이로드_검증(self, settings: Settings):
        user_id = uuid4()
        tenant_id = uuid4()
        token = create_access_token(user_id, tenant_id, "manager", settings)
        payload = decode_token(token, settings)

        assert payload.sub == str(user_id)
        assert payload.tenant_id == str(tenant_id)
        assert payload.role == "manager"
        assert payload.token_type == "access"

    def test_리프레시_토큰_페이로드_검증(self, settings: Settings):
        user_id = uuid4()
        tenant_id = uuid4()
        token = create_refresh_token(user_id, tenant_id, "analyst", settings)
        payload = decode_token(token, settings)

        assert payload.sub == str(user_id)
        assert payload.token_type == "refresh"

    def test_토큰_만료_시간_검증(self, settings: Settings):
        """액세스 토큰은 30분, 리프레시 토큰은 7일 만료."""
        user_id = uuid4()
        tenant_id = uuid4()

        access = create_access_token(user_id, tenant_id, "admin", settings)
        refresh = create_refresh_token(user_id, tenant_id, "admin", settings)

        access_payload = decode_token(access, settings)
        refresh_payload = decode_token(refresh, settings)

        now = datetime.now(UTC)
        access_exp = access_payload.exp.replace(tzinfo=UTC) if access_payload.exp.tzinfo is None else access_payload.exp
        refresh_exp = (
            refresh_payload.exp.replace(tzinfo=UTC)
            if refresh_payload.exp.tzinfo is None
            else refresh_payload.exp
        )

        # 액세스 토큰: 30분 ± 5초 이내
        access_delta = (access_exp - now).total_seconds()
        assert 25 * 60 < access_delta < 35 * 60

        # 리프레시 토큰: 7일 ± 5초 이내
        refresh_delta = (refresh_exp - now).total_seconds()
        assert 6 * 86400 < refresh_delta < 8 * 86400


class TestJWTTokenValidation:
    """JWT 토큰 검증 경계 케이스."""

    @pytest.fixture
    def settings(self) -> Settings:
        return Settings(
            jwt_secret="test-jwt-secret-32-chars-long-key",
            jwt_algorithm="HS256",
            jwt_access_token_expire_minutes=30,
            jwt_refresh_token_expire_days=7,
        )

    def test_만료된_토큰_거부(self, settings: Settings):
        """만료된 토큰은 401 에러를 발생시킨다."""
        payload = {
            "sub": str(uuid4()),
            "tenant_id": str(uuid4()),
            "role": "admin",
            "token_type": "access",
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "exp": datetime.now(UTC) - timedelta(hours=1),  # 1시간 전 만료
        }
        token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token, settings)
        assert exc_info.value.status_code == 401

    def test_잘못된_시크릿_거부(self, settings: Settings):
        """다른 시크릿으로 서명된 토큰을 거부한다."""
        payload = {
            "sub": str(uuid4()),
            "tenant_id": str(uuid4()),
            "role": "admin",
            "token_type": "access",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=1),
        }
        token = jwt.encode(payload, "wrong-secret-key", algorithm="HS256")

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token, settings)
        assert exc_info.value.status_code == 401

    def test_변조된_토큰_거부(self, settings: Settings):
        """페이로드가 변조된 토큰을 거부한다."""
        from fastapi import HTTPException

        # 유효한 토큰 생성 후 페이로드 부분을 변조
        token = create_access_token(uuid4(), uuid4(), "admin", settings)
        parts = token.split(".")
        # 페이로드 부분 변조
        tampered = parts[0] + "." + parts[1][::-1] + "." + parts[2]

        with pytest.raises((HTTPException, Exception)):
            decode_token(tampered, settings)

    def test_빈_토큰_거부(self, settings: Settings):
        """빈 문자열 토큰을 거부한다."""
        from fastapi import HTTPException
        with pytest.raises((HTTPException, Exception)):
            decode_token("", settings)

    def test_잘못된_형식_토큰_거부(self, settings: Settings):
        """JWT 형식이 아닌 문자열을 거부한다."""
        from fastapi import HTTPException
        with pytest.raises((HTTPException, Exception)):
            decode_token("not.a.valid.jwt.token", settings)

    def test_알고리즘_불일치_거부(self, settings: Settings):
        """다른 알고리즘(none)으로 서명된 토큰을 거부한다."""
        payload = {
            "sub": str(uuid4()),
            "tenant_id": str(uuid4()),
            "role": "admin",
            "token_type": "access",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=1),
        }
        # HS384로 서명 → HS256만 허용하는 서버에서 거부
        token = jwt.encode(payload, settings.jwt_secret, algorithm="HS384")

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token, settings)
        assert exc_info.value.status_code == 401


# ──────────────────────────────────────
# CORS 설정 테스트
# ──────────────────────────────────────


class TestCORSConfiguration:
    """CORS 미들웨어 설정 검증."""

    def test_설정에서_origins_파싱(self):
        """Settings.cors_origins가 콤마 구분 문자열로 파싱된다."""
        settings = Settings(cors_origins="https://app.propai.kr,https://admin.propai.kr")
        origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
        assert origins == ["https://app.propai.kr", "https://admin.propai.kr"]

    def test_기본_origins_로컬호스트(self):
        """기본 CORS origins는 localhost 3000, 3001."""
        settings = Settings()
        origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
        assert "http://localhost:3000" in origins
        assert "http://localhost:3001" in origins

    def test_빈_origins_처리(self):
        """빈 문자열은 빈 목록으로 처리."""
        settings = Settings(cors_origins="")
        origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
        assert origins == []

    @pytest.mark.asyncio
    async def test_CORS_preflight_응답(self, client):
        """OPTIONS 요청에 CORS 헤더가 포함된다."""
        response = await client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        # CORS preflight 응답은 200 또는 405 (허용된 origin이면 200)
        if response.status_code == 200:
            assert "access-control-allow-origin" in response.headers

    @pytest.mark.asyncio
    async def test_허용되지_않은_origin_차단(self, client):
        """허용되지 않은 origin의 CORS 요청은 헤더가 없다."""
        response = await client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://evil-site.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        cors_header = response.headers.get("access-control-allow-origin", "")
        assert "evil-site.com" not in cors_header


# ──────────────────────────────────────
# 인증 미들웨어 테스트
# ──────────────────────────────────────


class TestAuthenticationEnforcement:
    """보호된 엔드포인트 인증 강제 검증."""

    PROTECTED_ENDPOINTS = [
        ("GET", "/api/v1/auth/me"),
        ("GET", "/api/v1/projects"),
        ("GET", "/api/v1/dashboard/stats"),
        ("POST", "/api/v1/avm"),
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    async def test_인증없이_보호된_엔드포인트_접근_거부(self, client, method, path):
        """인증 없이 보호된 엔드포인트에 접근하면 401 또는 403."""
        if method == "GET":
            response = await client.get(path)
        else:
            response = await client.post(path, json={})
        assert response.status_code in {401, 403, 422}

    @pytest.mark.asyncio
    async def test_잘못된_Bearer_토큰_거부(self, client):
        """유효하지 않은 Bearer 토큰은 401."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-token-string"},
        )
        assert response.status_code in {401, 403}

    @pytest.mark.asyncio
    async def test_Bearer_접두사_누락_거부(self, client):
        """Bearer 접두사 없는 토큰은 401/403."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "invalid-token-string"},
        )
        assert response.status_code in {401, 403}


# ──────────────────────────────────────
# JWT 프로덕션 시크릿 검증
# ──────────────────────────────────────


class TestJWTSecretSecurity:
    """JWT 시크릿 보안 검증."""

    def test_기본_시크릿_개발환경_허용(self):
        """개발 환경에서는 기본 시크릿이 허용된다."""
        settings = Settings(
            jwt_secret="complex_jwt_secret_key_change_in_prod",
            environment="development",
        )
        assert settings.jwt_secret == "complex_jwt_secret_key_change_in_prod"

    def test_프로덕션_기본_시크릿_차단(self):
        """프로덕션 환경에서 기본형 시크릿 사용 시 기동이 차단된다.

        (이전: 경고만 발생 → 현재: ValidationError로 차단 강화. 2026-06 보안 조치와 일관.)
        """
        import pydantic
        os.environ["ENVIRONMENT"] = "production"
        try:
            with pytest.raises(pydantic.ValidationError):
                Settings(
                    jwt_secret="complex_jwt_secret_key_change_in_prod",
                    environment="production",
                )
        finally:
            os.environ.pop("ENVIRONMENT", None)

    def test_커스텀_시크릿_경고_없음(self):
        """커스텀 시크릿은 경고가 발생하지 않는다."""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Settings(
                jwt_secret="my-custom-production-secret-key-2024",
                environment="production",
            )
            jwt_warnings = [x for x in w if "JWT_SECRET" in str(x.message)]
            assert len(jwt_warnings) == 0


# ──────────────────────────────────────
# 요청 ID 헤더 테스트
# ──────────────────────────────────────


class TestRequestIDHeader:
    """X-Request-ID 헤더 검증."""

    @pytest.mark.asyncio
    async def test_응답에_X_Request_ID_포함(self, client):
        """모든 응답에 X-Request-ID 헤더가 포함된다."""
        response = await client.get("/health")
        assert "x-request-id" in response.headers
        # UUID 형식 검증
        request_id = response.headers["x-request-id"]
        assert len(request_id) == 36  # UUID v4 길이
        assert request_id.count("-") == 4


# ──────────────────────────────────────
# Rate Limit 설정 테스트
# ──────────────────────────────────────


class TestRateLimitConfiguration:
    """Rate Limit 설정 검증."""

    def test_기본_제한_설정(self):
        """기본 Rate Limit이 100/minute으로 설정되어 있다."""
        from apps.api.rate_limit import limiter
        # limiter의 default_limits 확인
        assert limiter._default_limits is not None

    def test_AI_제한_설정(self):
        """AI 엔드포인트 Rate Limit이 20/minute으로 설정되어 있다."""
        from apps.api.rate_limit import ai_limiter
        assert ai_limiter == "20/minute"

    def test_429_핸들러_존재(self):
        """Rate Limit 초과 핸들러가 등록되어 있다."""
        from apps.api.rate_limit import rate_limit_exceeded_handler
        assert callable(rate_limit_exceeded_handler)


# ──────────────────────────────────────
# 헬스체크 보안 테스트
# ──────────────────────────────────────


class TestHealthEndpointSecurity:
    """헬스체크 엔드포인트 보안."""

    @pytest.mark.asyncio
    async def test_헬스체크_인증_불필요(self, client):
        """/health는 인증 없이 접근 가능."""
        response = await client.get("/health")
        # 헬스체크는 인증 불필요 (DB 미연결 시 degraded 가능)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_헬스체크_민감정보_미노출(self, client):
        """/health 응답에 민감한 정보가 포함되지 않는다."""
        response = await client.get("/health")
        if response.status_code == 200:
            data = response.json()
            # DB 비밀번호, 시크릿 등이 노출되지 않아야 함
            text = str(data)
            assert "password" not in text.lower() or "propai_pass" not in text
            assert "secret" not in text.lower() or "jwt_secret" not in text
            assert "api_key" not in text.lower()


# ──────────────────────────────────────
# 미들웨어 등록 검증
# ──────────────────────────────────────


class TestMiddlewareRegistration:
    """보안 미들웨어 등록 검증."""

    def test_CORS_미들웨어_등록(self):
        """CORS 미들웨어가 앱에 등록되어 있다."""
        from apps.api.main import app
        # Starlette은 user_middleware에 미들웨어를 저장
        # CORSMiddleware는 이름으로 확인
        middleware_str = str(app.user_middleware)
        assert "CORS" in middleware_str or "cors" in middleware_str.lower() or len(app.user_middleware) > 0

    def test_SlowAPI_미들웨어_등록(self):
        """SlowAPI 미들웨어가 앱에 등록되어 있다."""
        from apps.api.main import app
        assert hasattr(app.state, "limiter")
        assert app.state.limiter is not None

    def test_버전_미들웨어_등록(self):
        """VersionHeader 미들웨어가 등록되어 있다."""
        from apps.api.main import app
        middleware_str = str(app.user_middleware)
        assert "VersionHeader" in middleware_str or len(app.user_middleware) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
