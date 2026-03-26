"""Rate Limiting 단위 테스트.

slowapi limiter 객체 및 핸들러 검증.
"""

import asyncio
import inspect
import json
from unittest.mock import MagicMock

from apps.api.rate_limit import ai_limiter, limiter, rate_limit_exceeded_handler


class TestLimiterConfig:
    """Limiter 설정 검증."""

    def test_limiter_exists(self) -> None:
        """limiter 객체가 생성되어 있다."""
        assert limiter is not None

    def test_default_limits(self) -> None:
        """기본 제한이 설정되어 있다."""
        assert limiter._default_limits is not None

    def test_ai_limiter_value(self) -> None:
        """AI 엔드포인트 제한이 20/minute이다."""
        assert ai_limiter == "20/minute"


class TestRateLimitHandler:
    """Rate Limit 초과 핸들러 검증."""

    def test_handler_is_async(self) -> None:
        """핸들러가 async 함수이다."""
        assert inspect.iscoroutinefunction(rate_limit_exceeded_handler)

    def test_handler_returns_429(self) -> None:
        """핸들러가 429 상태 코드를 반환한다."""
        request = MagicMock()
        exc = MagicMock()
        exc.detail = "100 per 1 minute"
        response = asyncio.run(rate_limit_exceeded_handler(request, exc))
        assert response.status_code == 429

    def test_handler_returns_json(self) -> None:
        """핸들러가 JSON 응답을 반환한다."""
        request = MagicMock()
        exc = MagicMock()
        exc.detail = "100 per 1 minute"
        response = asyncio.run(rate_limit_exceeded_handler(request, exc))
        body = json.loads(response.body)
        assert body["error"] == "rate_limit_exceeded"
        assert "요청 횟수 제한" in body["message"]
