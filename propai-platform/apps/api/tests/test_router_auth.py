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

        (이전 테스트는 필수값 시절의 422를 기대했으나 스펙이 변경됨.
        DB 없는 테스트 환경이라 성공 코드 대신 '검증 거부가 아님'만 확인.)
        """
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "name": "Operator",
                "email": "ops@propai.ai",
                "password": "test1234",
            },
        )
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
