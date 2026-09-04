"""카카오·구글 OAuth state(CSRF) 계약 테스트.

로그인 CSRF/세션 고정 방지 — login-url이 state를 발급·반환하고 인가 URL에 포함하며,
콜백 스키마가 state를 수용하는지 검증. (state 대조는 프론트 sessionStorage에서 수행.)
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


class TestOAuthStateLoginUrl:
    @pytest.mark.asyncio
    async def test_kakao_login_url_returns_state(self, client, monkeypatch):
        monkeypatch.setenv("KAKAO_REST_API_KEY", "test-kakao-rest-key-1234")
        r = await client.get(
            "/api/v1/auth/kakao/login-url?redirect_uri=https://4t8t.net/ko/kakao/callback"
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("state"), "state 미발급"
        assert len(data["state"]) >= 16
        assert "state=" in data["url"]  # 인가 URL에 state 포함(CSRF 왕복)

    @pytest.mark.asyncio
    async def test_google_login_url_returns_state(self, client, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client-id-1234")
        r = await client.get(
            "/api/v1/auth/google/login-url?redirect_uri=https://4t8t.net/ko/google/callback"
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("state"), "state 미발급"
        assert len(data["state"]) >= 16
        assert "state=" in data["url"]

    @pytest.mark.asyncio
    async def test_kakao_state_is_unique_per_request(self, client, monkeypatch):
        monkeypatch.setenv("KAKAO_REST_API_KEY", "test-kakao-rest-key-1234")
        s1 = (await client.get("/api/v1/auth/kakao/login-url")).json()["state"]
        s2 = (await client.get("/api/v1/auth/kakao/login-url")).json()["state"]
        assert s1 != s2  # 매 요청 유일(예측 불가)

    @pytest.mark.asyncio
    async def test_callback_schemas_accept_state(self):
        """콜백 요청 스키마가 state 필드를 명시 수용(계약 정합)."""
        from apps.api.routers.auth import GoogleCallbackRequest, KakaoCallbackRequest

        assert "state" in KakaoCallbackRequest.model_fields
        assert "state" in GoogleCallbackRequest.model_fields
        # state 없이도(구버전 호환) 유효, 있으면 보존
        assert KakaoCallbackRequest(code="c").state is None
        assert GoogleCallbackRequest(code="c", state="s").state == "s"
