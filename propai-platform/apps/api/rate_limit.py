"""Rate Limiting 설정.

slowapi 기반 요청 제한.
- 기본: 100 req/min per IP
- AI 엔드포인트: 20 req/min (비용 보호)
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

# AI 엔드포인트용 엄격한 제한
ai_limiter = "20/minute"


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Rate Limit 초과 시 429 응답."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": "요청 횟수 제한을 초과했습니다. 잠시 후 다시 시도하세요.",
            "detail": str(exc.detail),
        },
    )
