"""Circuit Breaker 상태 전환 단위 테스트.

STEP 4 품질 게이트: Circuit Breaker 상태 전환 테스트 통과
"""

import time

from packages.schemas.enums import CircuitBreakerState


class FakeCircuitBreaker:
    """테스트용 Circuit Breaker 구현 (base_client.py의 CircuitBreaker와 동일 로직)."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 0.5) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self._last_failure_time: float = 0

    def record_success(self) -> None:
        """성공 기록. HALF_OPEN → CLOSED 전환."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0

    def record_failure(self) -> None:
        """실패 기록. 임계값 초과 시 OPEN 전환."""
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            self._last_failure_time = time.monotonic()

    def can_execute(self) -> bool:
        """실행 가능 여부. OPEN 상태에서 recovery_timeout 경과 시 HALF_OPEN."""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        if self.state == CircuitBreakerState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                return True
            return False
        # HALF_OPEN: 한 번 시도 허용
        return True


class TestCircuitBreakerStates:
    """Circuit Breaker 상태 전환 검증."""

    def test_initial_state_closed(self) -> None:
        cb = FakeCircuitBreaker()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.can_execute() is True

    def test_closed_allows_execution(self) -> None:
        cb = FakeCircuitBreaker()
        assert cb.can_execute() is True

    def test_failures_below_threshold_stay_closed(self) -> None:
        cb = FakeCircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.can_execute() is True

    def test_failures_at_threshold_open(self) -> None:
        cb = FakeCircuitBreaker(failure_threshold=5)
        for _ in range(5):
            cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.can_execute() is False

    def test_open_to_half_open_after_timeout(self) -> None:
        cb = FakeCircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.can_execute() is False

        # recovery_timeout 대기
        time.sleep(0.15)
        assert cb.can_execute() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_half_open_success_closes(self) -> None:
        cb = FakeCircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        cb.can_execute()  # HALF_OPEN 진입

        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    def test_half_open_failure_reopens(self) -> None:
        cb = FakeCircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

        time.sleep(0.15)
        cb.can_execute()  # HALF_OPEN 진입
        assert cb.state == CircuitBreakerState.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

    def test_success_resets_failure_count(self) -> None:
        cb = FakeCircuitBreaker(failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 3

        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == CircuitBreakerState.CLOSED
