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
                 sweep_threshold: int = 4096, now=_time.monotonic) -> None:
        self._max_concurrent = max_concurrent_per_ip
        self._max_attempts = attempts_per_minute
        self._max_runs = runs_per_minute_per_tenant
        self._window = window_sec
        # ★키 무한증가 방지 상한: 추적 키(IP+테넌트)가 이 수를 넘으면 만료·빈 키를 sweep.
        #  고유 IP 대량 유입(또는 소켓레벨 위조)으로 dict 키가 영구 잔존→단일워커 OOM 되는
        #  'DoS 방지기의 역 DoS' 벡터를 막는다. 정상 경로는 release()가 즉시 정리한다.
        self._sweep_threshold = sweep_threshold
        self._now = now
        self._concurrent: dict[str, int] = _defaultdict(int)
        self._attempts: dict[str, _deque] = _defaultdict(_deque)
        self._runs: dict[str, _deque] = _defaultdict(_deque)

    def _prune(self, dq: _deque, cutoff: float) -> None:
        while dq and dq[0] <= cutoff:
            dq.popleft()

    def _sweep(self) -> None:
        """만료·빈 키 제거(메모리 무한증가 방지). 키 수가 상한 초과 시에만 수행(비용 억제)."""
        cutoff = self._now() - self._window
        for ip in list(self._attempts.keys()):
            dq = self._attempts.get(ip)
            if dq is not None:
                self._prune(dq, cutoff)
            if (not dq) and self._concurrent.get(ip, 0) == 0:
                self._attempts.pop(ip, None)
                self._concurrent.pop(ip, None)
        for tid in list(self._runs.keys()):
            dq = self._runs.get(tid)
            if dq is not None:
                self._prune(dq, cutoff)
            if not dq:
                self._runs.pop(tid, None)

    def _maybe_sweep(self) -> None:
        if (len(self._attempts) + len(self._runs)) > self._sweep_threshold:
            self._sweep()

    def try_connect(self, ip: str) -> bool:
        now = self._now()
        self._maybe_sweep()
        dq = self._attempts[ip]
        self._prune(dq, now - self._window)
        if len(dq) >= self._max_attempts:
            return False
        if self._concurrent[ip] >= self._max_concurrent:
            # 거부: 방금 defaultdict 접근으로 생긴 빈 키가 남지 않게 정리(누수 방지).
            if not dq:
                self._attempts.pop(ip, None)
                if self._concurrent.get(ip, 0) == 0:
                    self._concurrent.pop(ip, None)
            return False
        dq.append(now)
        self._concurrent[ip] += 1
        return True

    def release(self, ip: str) -> None:
        c = self._concurrent.get(ip, 0)
        if c > 0:
            self._concurrent[ip] = c - 1
        # 동시연결이 0으로 떨어지면 키를 정리한다(빈 attempts 윈도도 함께).
        if self._concurrent.get(ip, 0) == 0:
            self._concurrent.pop(ip, None)
            dq = self._attempts.get(ip)
            if dq is not None and not dq:
                self._attempts.pop(ip, None)

    def try_run(self, tenant_id: str) -> bool:
        now = self._now()
        self._maybe_sweep()
        dq = self._runs[tenant_id]
        self._prune(dq, now - self._window)
        if len(dq) >= self._max_runs:
            return False
        dq.append(now)
        return True


# /analyze/ws 공용 인스턴스(단일 워커 프로세스 상태)
ws_analyze_limiter = WsRateLimiter()


def ws_client_ip(xff_header: str | None, fallback_host: str | None,
                 trust_xff: bool | None = None) -> str:
    """WS 클라이언트 IP 판별(P2-14) — 리버스프록시 배포 대응.

    기본은 직결 소켓 IP(fallback_host). 신뢰 프록시(nginx 등이 X-Forwarded-For 를
    '덮어쓰는' 구성) 뒤 배포에서만 WS_TRUST_XFF=true 환경변수로 XFF 첫 홉을 쓴다.
    ★기본 미신뢰인 이유: 직결 노출 서버에서 XFF 를 무조건 믿으면 공격자가 헤더를
    임의 변경해 IP당 상한을 회피(스푸핑)한다 — 신뢰는 배포 구성의 명시적 선언으로만.
    (프록시 뒤에서 미신뢰로 두면 전 클라이언트가 프록시 IP 버킷을 공유해 과차단될 수
    있으니, 오라클 nginx 프런트 배포에선 WS_TRUST_XFF=true 를 함께 설정할 것.)
    """
    import os as _os
    if trust_xff is None:
        trust_xff = (_os.getenv("WS_TRUST_XFF", "").strip().lower() in ("1", "true", "yes"))
    if trust_xff and xff_header:
        first = xff_header.split(",")[0].strip()
        if first:
            return first
    return fallback_host or "unknown"
