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
    async def test_requires_company_name(self, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "name": "Operator",
                "email": "ops@propai.ai",
                "password": "test1234",
            },
        )
        assert response.status_code == 422

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
