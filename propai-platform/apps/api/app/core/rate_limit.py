"""슬라이딩 윈도우 요청 제한(Rate Limiter).

테넌트 등급별(free/pro/enterprise) 분당 요청 제한을 적용한다.
인메모리 구현이며, Redis 연동은 Phase 2에서 추가한다.
"""

import time
from collections import defaultdict

# 테넌트 등급별 분당 요청 한도
TIER_LIMITS: dict[str, int] = {
    "free": 100,
    "pro": 1000,
    "enterprise": 999_999,
}


class SlidingWindowCounter:
    """슬라이딩 윈도우 카운터."""

    __slots__ = ("_window_sec", "_requests")

    def __init__(self, window_seconds: int = 60):
        self._window_sec = window_seconds
        self._requests: list[float] = []

    def add(self) -> None:
        self._requests.append(time.monotonic())

    def count(self) -> int:
        self._cleanup()
        return len(self._requests)

    def _cleanup(self) -> None:
        cutoff = time.monotonic() - self._window_sec
        self._requests = [t for t in self._requests if t > cutoff]


class RateLimiter:
    """인메모리 슬라이딩 윈도우 요청 제한기."""

    def __init__(self, default_limit: int = 100, window_seconds: int = 60):
        self._default_limit = default_limit
        self._window_seconds = window_seconds
        self._counters: dict[str, SlidingWindowCounter] = defaultdict(
            lambda: SlidingWindowCounter(self._window_seconds)
        )
        self._custom_limits: dict[str, int] = {}

    def set_limit(self, key: str, limit: int) -> None:
        """특정 키에 대한 커스텀 한도를 설정한다."""
        self._custom_limits[key] = limit

    def get_limit(self, key: str) -> int:
        """키의 현재 한도를 반환한다."""
        return self._custom_limits.get(key, self._default_limit)

    def check(self, key: str) -> bool:
        """요청 허용 여부를 확인한다. True=허용, False=초과."""
        counter = self._counters[key]
        limit = self.get_limit(key)
        if counter.count() >= limit:
            return False
        counter.add()
        return True

    def get_remaining(self, key: str) -> int:
        """남은 요청 수를 반환한다."""
        counter = self._counters[key]
        limit = self.get_limit(key)
        return max(0, limit - counter.count())

    def get_usage(self, key: str) -> dict:
        """키의 사용량 정보를 반환한다."""
        counter = self._counters[key]
        limit = self.get_limit(key)
        current = counter.count()
        return {
            "key": key,
            "limit": limit,
            "used": current,
            "remaining": max(0, limit - current),
            "window_seconds": self._window_seconds,
        }

    def reset(self, key: str) -> None:
        """키의 카운터를 초기화한다."""
        if key in self._counters:
            del self._counters[key]

    def check_tenant(self, tenant_id: str, tier: str = "free",
                     endpoint: str | None = None) -> bool:
        """테넌트 등급에 따른 요청 허용 여부를 확인한다."""
        limit = TIER_LIMITS.get(tier, self._default_limit)
        key = f"tenant:{tenant_id}"
        if endpoint:
            key = f"tenant:{tenant_id}:ep:{endpoint}"
        self._custom_limits.setdefault(key, limit)
        return self.check(key)

    @property
    def active_keys(self) -> int:
        """활성 키(카운터) 수."""
        return len(self._counters)


_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """전역 RateLimiter 반환."""
    return _limiter
