"""Rate Limiting 설정.

slowapi 기반 요청 제한.
- 기본: 100 req/min per IP
- AI 엔드포인트: 20 req/min (비용 보호)
"""

import time as _time
from collections import defaultdict as _defaultdict
from collections import deque as _deque

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


# ── P2-14: WebSocket 전용 레이트리미터 ──────────────────────────────
# slowapi 는 HTTP 미들웨어라 WebSocket 을 보호하지 못한다. /analyze/ws 는 연결당
# 7단계 오케스트레이터(LLM 비용)를 구동하므로 전용 in-memory 리미터를 둔다.
# 단일 워커(uvicorn --workers 1) 운영 전제라 in-process 상태로 충분하며,
# 멀티워커 확장 시 이 클래스가 redis 백엔드로 교체할 단일 지점이다.
class WsRateLimiter:
    """WebSocket 연결/실행 상한(P2-14).

    - try_connect(ip): ① IP당 동시 연결 상한 ② IP당 분당 연결시도 상한(슬라이딩 윈도).
      거부된 시도는 동시 슬롯을 소모하지 않는다. 허용 시 반드시 release(ip) 짝 호출.
    - try_run(tenant_id): 테넌트당 분당 오케스트레이터 실행 상한(비용 보호).
    시계 주입(now)으로 결정적 테스트 가능.
    """

    def __init__(self, *, max_concurrent_per_ip: int = 4, attempts_per_minute: int = 10,
                 runs_per_minute_per_tenant: int = 5, window_sec: float = 60.0,
                 now=_time.monotonic) -> None:
        self._max_concurrent = max_concurrent_per_ip
        self._max_attempts = attempts_per_minute
        self._max_runs = runs_per_minute_per_tenant
        self._window = window_sec
        self._now = now
        self._concurrent: dict[str, int] = _defaultdict(int)
        self._attempts: dict[str, _deque] = _defaultdict(_deque)
        self._runs: dict[str, _deque] = _defaultdict(_deque)

    def _prune(self, dq: _deque, cutoff: float) -> None:
        while dq and dq[0] <= cutoff:
            dq.popleft()

    def try_connect(self, ip: str) -> bool:
        now = self._now()
        dq = self._attempts[ip]
        self._prune(dq, now - self._window)
        if len(dq) >= self._max_attempts:
            return False
        if self._concurrent[ip] >= self._max_concurrent:
            return False
        dq.append(now)
        self._concurrent[ip] += 1
        return True

    def release(self, ip: str) -> None:
        if self._concurrent.get(ip, 0) > 0:
            self._concurrent[ip] -= 1

    def try_run(self, tenant_id: str) -> bool:
        now = self._now()
        dq = self._runs[tenant_id]
        self._prune(dq, now - self._window)
        if len(dq) >= self._max_runs:
            return False
        dq.append(now)
        return True


# /analyze/ws 공용 인스턴스(단일 워커 프로세스 상태)
ws_analyze_limiter = WsRateLimiter()
