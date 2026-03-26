"""CircuitBreaker 단위 테스트.

외부 API 공통 서킷브레이커의 상태 전이 로직을 검증한다.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.integrations.base_client import CircuitBreaker, CircuitState


class TestCircuitBreakerInit:
    """초기 상태 테스트."""

    def test_초기상태_CLOSED(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_초기_실패횟수_0(self):
        cb = CircuitBreaker()
        assert cb.failure_count == 0

    def test_기본_임계값_5(self):
        cb = CircuitBreaker()
        assert cb.failure_threshold == 5

    def test_기본_복구시간_60초(self):
        cb = CircuitBreaker()
        assert cb.recovery_timeout == 60.0


class TestCanExecute:
    """can_execute 메서드 테스트."""

    def test_CLOSED_실행가능(self):
        cb = CircuitBreaker()
        assert cb.can_execute() is True

    def test_OPEN_실행불가(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_OPEN_복구시간_후_HALF_OPEN(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_HALF_OPEN_제한된_호출(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01, half_open_max=2)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)
        cb.can_execute()  # → HALF_OPEN
        assert cb.half_open_calls < cb.half_open_max


class TestRecordSuccess:
    """record_success 메서드 테스트."""

    def test_CLOSED_실패횟수_리셋(self):
        cb = CircuitBreaker(failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        cb.record_success()
        assert cb.failure_count == 0

    def test_HALF_OPEN_성공후_CLOSED(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.01, half_open_max=2)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)
        cb.can_execute()  # → HALF_OPEN
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED


class TestRecordFailure:
    """record_failure 메서드 테스트."""

    def test_임계값_도달시_OPEN(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_실패횟수_누적(self):
        cb = CircuitBreaker(failure_threshold=10)
        for _i in range(5):
            cb.record_failure()
        assert cb.failure_count == 5

    def test_last_failure_time_갱신(self):
        cb = CircuitBreaker()
        before = time.time()
        cb.record_failure()
        assert cb.last_failure_time >= before


class TestCircuitStateEnum:
    """CircuitState 열거형 테스트."""

    def test_3개_상태(self):
        assert CircuitState.CLOSED == "closed"
        assert CircuitState.OPEN == "open"
        assert CircuitState.HALF_OPEN == "half_open"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
