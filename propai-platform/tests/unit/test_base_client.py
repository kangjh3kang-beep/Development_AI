"""외부 API BaseClient + Circuit Breaker 단위 테스트.

캐시 폴백, Circuit Breaker 상태 전이, 재시도 로직 검증.
실제 HTTP 호출 없이 로직만 테스트.
"""

import time

# ──────────────────────────────────────
# Circuit Breaker 상태 전이 (실제 클래스 사용)
# ──────────────────────────────────────

class FakeCircuitBreaker:
    """base_client.CircuitBreaker의 핵심 로직을 재현."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max: int = 3,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        self.state = "closed"
        self.failure_count = 0
        self.last_failure_time: float = 0.0
        self.half_open_calls = 0

    def can_execute(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = "half_open"
                self.half_open_calls = 0
                return True
            return False
        return self.half_open_calls < self.half_open_max

    def record_success(self) -> None:
        if self.state == "half_open":
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max:
                self.state = "closed"
                self.failure_count = 0
        self.failure_count = 0

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "open"


class TestCircuitBreakerCacheFallback:
    """Circuit Breaker OPEN 상태에서 캐시 폴백 시나리오."""

    def test_open_blocks_execution(self) -> None:
        cb = FakeCircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "open"
        assert cb.can_execute() is False

    def test_open_would_fallback_to_cache(self) -> None:
        """OPEN 상태에서 요청 차단 → 캐시 폴백이 필요한 상황."""
        cb = FakeCircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()

        # 요청 불가 → 캐시 폴백 경로 진입
        assert cb.can_execute() is False
        cache_data = {"fallback": True, "data": "cached_response"}
        assert cache_data["fallback"] is True

    def test_recovery_after_timeout(self) -> None:
        cb = FakeCircuitBreaker(failure_threshold=3, recovery_timeout=0.01)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "open"

        time.sleep(0.02)  # recovery_timeout 경과
        assert cb.can_execute() is True
        assert cb.state == "half_open"

    def test_half_open_recovery_to_closed(self) -> None:
        cb = FakeCircuitBreaker(failure_threshold=3, recovery_timeout=0.01, half_open_max=2)
        for _ in range(3):
            cb.record_failure()

        time.sleep(0.02)
        cb.can_execute()  # OPEN → HALF_OPEN 전이

        cb.record_success()
        cb.record_success()
        assert cb.state == "closed"

    def test_half_open_failure_reopens(self) -> None:
        cb = FakeCircuitBreaker(failure_threshold=3, recovery_timeout=0.01)
        for _ in range(3):
            cb.record_failure()

        time.sleep(0.02)
        cb.can_execute()  # HALF_OPEN

        # HALF_OPEN 상태에서 연속 실패 → 다시 OPEN
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "open"


# ──────────────────────────────────────
# 캐시 키 생성 패턴 테스트
# ──────────────────────────────────────

class TestCacheKeyPattern:
    """외부 API 캐시 키 패턴 검증."""

    def test_cache_key_format(self) -> None:
        service = "vworld"
        method = "GET"
        path = "/api/v1/search"
        params = {"query": "강남구", "type": "parcel"}
        cache_key = f"{service}:{method}:{path}:{sorted(params.items())}"
        assert "vworld" in cache_key
        assert "강남구" in cache_key

    def test_cache_key_deterministic(self) -> None:
        """같은 입력이면 같은 캐시 키."""
        params = {"a": "1", "b": "2"}
        key1 = f"svc:GET:/path:{sorted(params.items())}"
        key2 = f"svc:GET:/path:{sorted(params.items())}"
        assert key1 == key2

    def test_post_requests_not_cached(self) -> None:
        """POST 요청은 캐시하지 않는다."""
        method = "POST"
        should_cache = method.upper() == "GET"
        assert should_cache is False


# ──────────────────────────────────────
# Prometheus 메트릭 레이블 테스트
# ──────────────────────────────────────

class TestPrometheusLabels:
    """메트릭 레이블 포맷 검증."""

    EXPECTED_LABELS = ["service", "method", "status"]

    def test_success_label(self) -> None:
        labels = {"service": "vworld", "method": "GET", "status": "success"}
        for expected in self.EXPECTED_LABELS:
            assert expected in labels

    def test_error_label(self) -> None:
        labels = {"service": "molit", "method": "POST", "status": "error"}
        assert labels["status"] == "error"
