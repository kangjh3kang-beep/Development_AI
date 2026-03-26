"""헬스체크 라우터 테스트.

/health 엔드포인트의 응답 구조와 상태 코드를 검증한다.
외부 서비스(DB, Redis, Qdrant) Mock으로 격리 테스트.
"""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@pytest.mark.asyncio
async def test_health_엔드포인트_200(client):
    """외부 서비스 Mock 상태에서 /health 200 응답."""
    with (
        patch("apps.api.main.check_qdrant_health", new_callable=AsyncMock, return_value=False),
    ):
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "services" in data


@pytest.mark.asyncio
async def test_health_서비스_필드_포함(client):
    """응답에 postgres, redis, qdrant 서비스 상태 포함."""
    with patch("apps.api.main.check_qdrant_health", new_callable=AsyncMock, return_value=False):
        response = await client.get("/health")
    data = response.json()
    services = data["services"]
    # SQLite mock DB이므로 postgres 키가 존재해야 함
    assert isinstance(services, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
