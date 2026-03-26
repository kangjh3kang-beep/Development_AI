"""챗봇 라우터 단위 테스트.

챗봇 엔드포인트 인증 요구를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


class TestChatbotEndpoints:
    """챗봇 엔드포인트 인증 테스트."""

    @pytest.mark.asyncio
    async def test_sessions_인증없이_거부(self, client):
        response = await client.get("/api/v1/chatbot/sessions")
        assert response.status_code in {401, 403}

    @pytest.mark.asyncio
    async def test_create_session_인증없이_거부(self, client):
        response = await client.post("/api/v1/chatbot/sessions", json={
            "domain": "investment",
            "model_name": "gpt-4",
        })
        assert response.status_code in {401, 403}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
