"""Router validation tests for authentication endpoints."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


class TestLoginValidation:
    @pytest.mark.asyncio
    async def test_requires_email(self, client):
        response = await client.post(
            "/api/v1/auth/login",
            json={"password": "test1234"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_requires_password(self, client):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_rejects_invalid_email_format(self, client):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "not-an-email", "password": "test1234"},
        )
        assert response.status_code == 422

class TestRegisterValidation:
    @pytest.mark.asyncio
    async def test_requires_name(self, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": "PropAI Labs",
                "email": "ops@propai.ai",
                "password": "test1234",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_company_name_is_optional(self, client):
        """회사명은 선택값 — 개인(무구독) 회원 가입 허용 스펙.

        RegisterRequest.company_name 은 default="" 로 선택값이므로, 회사명을
        뺀 페이로드는 422(검증 거부)로 거부되면 안 된다.

        검증(Pydantic)은 라우터 핸들러/DB 접근보다 먼저 수행된다. 따라서
        페이로드가 검증을 통과하면 요청은 DB 계층까지 진행한다. DB 없는 CI
        환경에서는 핸들러가 DB 연결에서 ConnectionRefusedError 를 던지며, 이
        예외는 ASGI 전송 계층까지 전파될 수 있다. 그 예외에 도달했다는 것
        자체가 '검증을 통과했다'(=422 가 아니다)는 증거다.
        """
        try:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "name": "Operator",
                    "email": "ops@propai.ai",
                    "password": "test1234",
                },
            )
        except Exception as exc:  # DB 미가동 환경: 검증 통과 후 DB 접근에서 발생
            # 검증 단계(422)는 핸들러 진입 전이라 예외를 던지지 않는다.
            # 여기 도달했다 = 핸들러까지 진입 = company_name 없이도 검증 통과.
            assert "ConnectionRefused" in repr(exc) or "Connect call failed" in str(exc), (
                f"검증 이후 DB 접근 외의 예기치 못한 예외: {exc!r}"
            )
            return

        # DB 가 있는 환경: 검증 거부(422)만 아니면 스펙 충족(회사명 선택값).
        assert response.status_code != 422

    @pytest.mark.asyncio
    async def test_requires_minimum_password_length(self, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "name": "Operator",
                "company_name": "PropAI Labs",
                "email": "ops@propai.ai",
                "password": "short",
            },
        )
        assert response.status_code == 422

class TestRefreshValidation:
    @pytest.mark.asyncio
    async def test_requires_refresh_token(self, client):
        response = await client.post("/api/v1/auth/refresh", json={})
        assert response.status_code == 422


class TestMeEndpoint:
    @pytest.mark.asyncio
    async def test_requires_authentication(self, client):
        response = await client.get("/api/v1/auth/me")
        assert response.status_code in {401, 403}
